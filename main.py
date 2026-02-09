"""
AgentForge — Open-source toolkit API for autonomous agents.
Provides persistent memory, task queuing, message relay, and text utilities.
"""

import os
import json
import time
import uuid
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ─── Config ───────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("AGENTFORGE_DB", "agentforge.db")
MAX_MEMORY_VALUE_SIZE = 50_000  # 50KB per value
MAX_QUEUE_PAYLOAD_SIZE = 100_000  # 100KB per job
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 120  # requests per window per agent

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AgentForge",
    description="Open-source toolkit API for autonomous agents. "
    "Persistent memory, task queues, message relay, and text utilities.",
    version="0.1.0-pilot",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Database ─────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT PRIMARY KEY,
            api_key_hash TEXT NOT NULL,
            name TEXT,
            created_at TEXT NOT NULL,
            last_seen TEXT,
            request_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS memory (
            agent_id TEXT NOT NULL,
            namespace TEXT NOT NULL DEFAULT 'default',
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT,
            PRIMARY KEY (agent_id, namespace, key),
            FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
        );

        CREATE TABLE IF NOT EXISTS queue (
            job_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            queue_name TEXT NOT NULL DEFAULT 'default',
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
        );
        CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(queue_name, status, priority DESC);

        CREATE TABLE IF NOT EXISTS relay (
            message_id TEXT PRIMARY KEY,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'direct',
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at TEXT,
            FOREIGN KEY (from_agent) REFERENCES agents(agent_id)
        );
        CREATE INDEX IF NOT EXISTS idx_relay_to ON relay(to_agent, read_at);

        CREATE TABLE IF NOT EXISTS rate_limits (
            agent_id TEXT NOT NULL,
            window_start INTEGER NOT NULL,
            count INTEGER DEFAULT 1,
            PRIMARY KEY (agent_id, window_start)
        );

        CREATE TABLE IF NOT EXISTS metrics (
            recorded_at TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            latency_ms REAL NOT NULL,
            status_code INTEGER NOT NULL
        );
    """)
    conn.close()

init_db()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

# ─── Auth Helpers ─────────────────────────────────────────────────────────────
def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()

def generate_api_key() -> str:
    return f"af_{uuid.uuid4().hex}"

async def get_agent_id(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    with get_db() as db:
        row = db.execute(
            "SELECT agent_id FROM agents WHERE api_key_hash = ?",
            (hash_key(x_api_key),)
        ).fetchone()
        if not row:
            raise HTTPException(401, "Invalid API key")

        now = datetime.now(timezone.utc).isoformat()
        # Rate limiting
        window = int(time.time()) // RATE_LIMIT_WINDOW
        db.execute("""
            INSERT INTO rate_limits (agent_id, window_start, count)
            VALUES (?, ?, 1)
            ON CONFLICT(agent_id, window_start) DO UPDATE SET count = count + 1
        """, (row["agent_id"], window))
        rl = db.execute(
            "SELECT count FROM rate_limits WHERE agent_id = ? AND window_start = ?",
            (row["agent_id"], window)
        ).fetchone()
        if rl and rl["count"] > RATE_LIMIT_MAX:
            raise HTTPException(429, f"Rate limit exceeded ({RATE_LIMIT_MAX}/min)")

        db.execute(
            "UPDATE agents SET last_seen = ?, request_count = request_count + 1 WHERE agent_id = ?",
            (now, row["agent_id"])
        )
        return row["agent_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=64, description="Display name for your agent")

class RegisterResponse(BaseModel):
    agent_id: str
    api_key: str
    message: str

@app.post("/v1/register", response_model=RegisterResponse, tags=["Auth"])
def register_agent(req: RegisterRequest):
    """Register a new agent and receive an API key. Free. No payment required."""
    agent_id = f"agent_{uuid.uuid4().hex[:12]}"
    api_key = generate_api_key()
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        db.execute(
            "INSERT INTO agents (agent_id, api_key_hash, name, created_at) VALUES (?, ?, ?, ?)",
            (agent_id, hash_key(api_key), req.name, now)
        )

    return RegisterResponse(
        agent_id=agent_id,
        api_key=api_key,
        message="Store your API key securely. It cannot be recovered."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PERSISTENT MEMORY (Key-Value Store with Namespaces + TTL)
# ═══════════════════════════════════════════════════════════════════════════════

class MemorySetRequest(BaseModel):
    key: str = Field(..., max_length=256)
    value: str = Field(..., max_length=MAX_MEMORY_VALUE_SIZE)
    namespace: str = Field("default", max_length=64)
    ttl_seconds: Optional[int] = Field(None, ge=60, le=2592000, description="Auto-expire after N seconds (60s–30d)")

class MemoryGetResponse(BaseModel):
    key: str
    value: str
    namespace: str
    updated_at: str
    expires_at: Optional[str]

@app.post("/v1/memory", tags=["Memory"])
def memory_set(req: MemorySetRequest, agent_id: str = Depends(get_agent_id)):
    """Store or update a key-value pair in persistent memory."""
    now = datetime.now(timezone.utc)
    expires = None
    if req.ttl_seconds:
        expires = (now + timedelta(seconds=req.ttl_seconds)).isoformat()

    with get_db() as db:
        db.execute("""
            INSERT INTO memory (agent_id, namespace, key, value, created_at, updated_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id, namespace, key)
            DO UPDATE SET value=?, updated_at=?, expires_at=?
        """, (agent_id, req.namespace, req.key, req.value, now.isoformat(), now.isoformat(), expires,
              req.value, now.isoformat(), expires))

    return {"status": "stored", "key": req.key, "namespace": req.namespace}

@app.get("/v1/memory/{key}", response_model=MemoryGetResponse, tags=["Memory"])
def memory_get(key: str, namespace: str = "default", agent_id: str = Depends(get_agent_id)):
    """Retrieve a value from persistent memory."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM memory WHERE agent_id=? AND namespace=? AND key=? AND (expires_at IS NULL OR expires_at > ?)",
            (agent_id, namespace, key, now)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Key not found or expired")
        return MemoryGetResponse(**dict(row))

@app.delete("/v1/memory/{key}", tags=["Memory"])
def memory_delete(key: str, namespace: str = "default", agent_id: str = Depends(get_agent_id)):
    """Delete a key from memory."""
    with get_db() as db:
        r = db.execute(
            "DELETE FROM memory WHERE agent_id=? AND namespace=? AND key=?",
            (agent_id, namespace, key)
        )
        if r.rowcount == 0:
            raise HTTPException(404, "Key not found")
    return {"status": "deleted", "key": key}

@app.get("/v1/memory", tags=["Memory"])
def memory_list(
    namespace: str = "default",
    prefix: str = "",
    limit: int = Query(50, le=200),
    agent_id: str = Depends(get_agent_id)
):
    """List keys in a namespace, optionally filtered by prefix."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        rows = db.execute(
            "SELECT key, LENGTH(value) as size_bytes, updated_at, expires_at FROM memory "
            "WHERE agent_id=? AND namespace=? AND key LIKE ? AND (expires_at IS NULL OR expires_at > ?) "
            "ORDER BY updated_at DESC LIMIT ?",
            (agent_id, namespace, f"{prefix}%", now, limit)
        ).fetchall()
    return {"namespace": namespace, "keys": [dict(r) for r in rows], "count": len(rows)}


# ═══════════════════════════════════════════════════════════════════════════════
# TASK QUEUE (Priority Queue with Status Tracking)
# ═══════════════════════════════════════════════════════════════════════════════

class QueueSubmitRequest(BaseModel):
    payload: str = Field(..., max_length=MAX_QUEUE_PAYLOAD_SIZE)
    queue_name: str = Field("default", max_length=64)
    priority: int = Field(0, ge=0, le=10, description="Higher = processed first")

class QueueJobResponse(BaseModel):
    job_id: str
    status: str
    queue_name: str
    priority: int
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    result: Optional[str]

@app.post("/v1/queue/submit", tags=["Queue"])
def queue_submit(req: QueueSubmitRequest, agent_id: str = Depends(get_agent_id)):
    """Submit a job to the task queue."""
    job_id = f"job_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        db.execute(
            "INSERT INTO queue (job_id, agent_id, queue_name, payload, priority, created_at) VALUES (?,?,?,?,?,?)",
            (job_id, agent_id, req.queue_name, req.payload, req.priority, now)
        )
    return {"job_id": job_id, "status": "pending", "queue_name": req.queue_name}

@app.get("/v1/queue/{job_id}", response_model=QueueJobResponse, tags=["Queue"])
def queue_status(job_id: str, agent_id: str = Depends(get_agent_id)):
    """Check job status."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM queue WHERE job_id=? AND agent_id=?", (job_id, agent_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        return QueueJobResponse(**dict(row))

@app.post("/v1/queue/claim", tags=["Queue"])
def queue_claim(queue_name: str = "default", agent_id: str = Depends(get_agent_id)):
    """Claim the next pending job from a queue (for worker agents)."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        row = db.execute(
            "SELECT job_id, payload, priority FROM queue WHERE queue_name=? AND status='pending' "
            "ORDER BY priority DESC, created_at ASC LIMIT 1",
            (queue_name,)
        ).fetchone()
        if not row:
            return {"status": "empty", "queue_name": queue_name}
        db.execute(
            "UPDATE queue SET status='processing', started_at=? WHERE job_id=?",
            (now, row["job_id"])
        )
        return {"job_id": row["job_id"], "payload": row["payload"], "priority": row["priority"]}

@app.post("/v1/queue/{job_id}/complete", tags=["Queue"])
def queue_complete(job_id: str, result: str = "", agent_id: str = Depends(get_agent_id)):
    """Mark a job as completed with optional result."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        r = db.execute(
            "UPDATE queue SET status='completed', completed_at=?, result=? WHERE job_id=? AND status='processing'",
            (now, result, job_id)
        )
        if r.rowcount == 0:
            raise HTTPException(404, "Job not found or not in processing state")
    return {"job_id": job_id, "status": "completed"}

@app.get("/v1/queue", tags=["Queue"])
def queue_list(
    queue_name: str = "default",
    status: Optional[str] = None,
    limit: int = Query(20, le=100),
    agent_id: str = Depends(get_agent_id)
):
    """List jobs in a queue."""
    with get_db() as db:
        if status:
            rows = db.execute(
                "SELECT job_id, status, priority, created_at, completed_at FROM queue "
                "WHERE agent_id=? AND queue_name=? AND status=? ORDER BY created_at DESC LIMIT ?",
                (agent_id, queue_name, status, limit)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT job_id, status, priority, created_at, completed_at FROM queue "
                "WHERE agent_id=? AND queue_name=? ORDER BY created_at DESC LIMIT ?",
                (agent_id, queue_name, limit)
            ).fetchall()
    return {"queue_name": queue_name, "jobs": [dict(r) for r in rows], "count": len(rows)}


# ═══════════════════════════════════════════════════════════════════════════════
# MESSAGE RELAY (Bot-to-Bot Communication)
# ═══════════════════════════════════════════════════════════════════════════════

class RelayMessage(BaseModel):
    to_agent: str = Field(..., description="Recipient agent_id")
    channel: str = Field("direct", max_length=64)
    payload: str = Field(..., max_length=10_000)

@app.post("/v1/relay/send", tags=["Relay"])
def relay_send(msg: RelayMessage, agent_id: str = Depends(get_agent_id)):
    """Send a message to another agent."""
    message_id = f"msg_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        # Verify recipient exists
        recip = db.execute("SELECT agent_id FROM agents WHERE agent_id=?", (msg.to_agent,)).fetchone()
        if not recip:
            raise HTTPException(404, "Recipient agent not found")
        db.execute(
            "INSERT INTO relay (message_id, from_agent, to_agent, channel, payload, created_at) VALUES (?,?,?,?,?,?)",
            (message_id, agent_id, msg.to_agent, msg.channel, msg.payload, now)
        )
    return {"message_id": message_id, "status": "delivered"}

@app.get("/v1/relay/inbox", tags=["Relay"])
def relay_inbox(
    channel: str = "direct",
    unread_only: bool = True,
    limit: int = Query(20, le=100),
    agent_id: str = Depends(get_agent_id)
):
    """Check your message inbox."""
    with get_db() as db:
        if unread_only:
            rows = db.execute(
                "SELECT message_id, from_agent, channel, payload, created_at FROM relay "
                "WHERE to_agent=? AND channel=? AND read_at IS NULL ORDER BY created_at DESC LIMIT ?",
                (agent_id, channel, limit)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT message_id, from_agent, channel, payload, created_at, read_at FROM relay "
                "WHERE to_agent=? AND channel=? ORDER BY created_at DESC LIMIT ?",
                (agent_id, channel, limit)
            ).fetchall()
    return {"channel": channel, "messages": [dict(r) for r in rows], "count": len(rows)}

@app.post("/v1/relay/{message_id}/read", tags=["Relay"])
def relay_mark_read(message_id: str, agent_id: str = Depends(get_agent_id)):
    """Mark a message as read."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        r = db.execute(
            "UPDATE relay SET read_at=? WHERE message_id=? AND to_agent=? AND read_at IS NULL",
            (now, message_id, agent_id)
        )
        if r.rowcount == 0:
            raise HTTPException(404, "Message not found or already read")
    return {"message_id": message_id, "status": "read"}


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

class TextProcessRequest(BaseModel):
    text: str = Field(..., max_length=50_000)
    operation: str = Field(..., description="One of: word_count, char_count, extract_urls, extract_emails, tokenize_sentences, deduplicate_lines, hash_sha256, base64_encode, base64_decode")

@app.post("/v1/text/process", tags=["Text Utilities"])
def text_process(req: TextProcessRequest, agent_id: str = Depends(get_agent_id)):
    """Run a text processing operation. Useful for agents that need fast server-side text manipulation."""
    import re
    import base64

    ops = {
        "word_count": lambda t: {"word_count": len(t.split())},
        "char_count": lambda t: {"char_count": len(t), "char_count_no_spaces": len(t.replace(" ", ""))},
        "extract_urls": lambda t: {"urls": re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', t)},
        "extract_emails": lambda t: {"emails": re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', t)},
        "tokenize_sentences": lambda t: {"sentences": [s.strip() for s in re.split(r'(?<=[.!?])\s+', t) if s.strip()]},
        "deduplicate_lines": lambda t: {"lines": list(dict.fromkeys(t.splitlines())), "removed": len(t.splitlines()) - len(set(t.splitlines()))},
        "hash_sha256": lambda t: {"hash": hashlib.sha256(t.encode()).hexdigest()},
        "base64_encode": lambda t: {"encoded": base64.b64encode(t.encode()).decode()},
        "base64_decode": lambda t: {"decoded": base64.b64decode(t.encode()).decode()},
    }

    if req.operation not in ops:
        raise HTTPException(400, f"Unknown operation. Available: {list(ops.keys())}")

    try:
        result = ops[req.operation](req.text)
    except Exception as e:
        raise HTTPException(422, f"Operation failed: {str(e)}")

    return {"operation": req.operation, "result": result}


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH / METRICS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/v1/health", tags=["System"])
def health():
    """Public health check — no auth required."""
    with get_db() as db:
        agent_count = db.execute("SELECT COUNT(*) as c FROM agents").fetchone()["c"]
        job_count = db.execute("SELECT COUNT(*) as c FROM queue").fetchone()["c"]
        memory_keys = db.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"]
        messages = db.execute("SELECT COUNT(*) as c FROM relay").fetchone()["c"]

    return {
        "status": "operational",
        "version": "0.1.0-pilot",
        "uptime_note": "Pilot phase — expect occasional restarts",
        "stats": {
            "registered_agents": agent_count,
            "total_jobs": job_count,
            "memory_keys_stored": memory_keys,
            "messages_relayed": messages,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/v1/stats", tags=["System"])
def stats(agent_id: str = Depends(get_agent_id)):
    """Your agent's usage stats."""
    with get_db() as db:
        agent = db.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        mem_count = db.execute("SELECT COUNT(*) as c FROM memory WHERE agent_id=?", (agent_id,)).fetchone()["c"]
        job_count = db.execute("SELECT COUNT(*) as c FROM queue WHERE agent_id=?", (agent_id,)).fetchone()["c"]
        msg_sent = db.execute("SELECT COUNT(*) as c FROM relay WHERE from_agent=?", (agent_id,)).fetchone()["c"]
        msg_recv = db.execute("SELECT COUNT(*) as c FROM relay WHERE to_agent=?", (agent_id,)).fetchone()["c"]

    return {
        "agent_id": agent_id,
        "name": agent["name"],
        "created_at": agent["created_at"],
        "total_requests": agent["request_count"],
        "memory_keys": mem_count,
        "jobs_submitted": job_count,
        "messages_sent": msg_sent,
        "messages_received": msg_recv,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ROOT
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["System"])
def root():
    return {
        "service": "AgentForge",
        "version": "0.1.0-pilot",
        "docs": "/docs",
        "description": "Open-source toolkit API for autonomous agents",
        "endpoints": {
            "register": "POST /v1/register",
            "memory": "/v1/memory",
            "queue": "/v1/queue",
            "relay": "/v1/relay",
            "text": "/v1/text/process",
            "health": "GET /v1/health",
        }
    }
