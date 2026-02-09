# AgentForge — Hostinger VPS Deployment

## 1. SSH into your VPS

```bash
ssh root@YOUR_VPS_IP
```

## 2. Install dependencies

```bash
apt update && apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx
```

## 3. Upload the project

Option A — from your local machine (run this locally, not on VPS):
```bash
scp -r agentforge/ root@YOUR_VPS_IP:/opt/agentforge
```

Option B — clone from GitHub (if you push it first):
```bash
git clone https://github.com/YOUR_USERNAME/agentforge.git /opt/agentforge
```

## 4. Set up Python environment

```bash
cd /opt/agentforge
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 5. Test it works

```bash
source venv/bin/activate
uvicorn api.main:app --host 127.0.0.1 --port 8000
# In another terminal: curl http://127.0.0.1:8000/v1/health
# You should see {"status":"operational",...}
# Ctrl+C to stop
```

## 6. Create systemd service (auto-start on boot)

```bash
cat > /etc/systemd/system/agentforge.service << 'EOF'
[Unit]
Description=AgentForge API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/agentforge
Environment=PATH=/opt/agentforge/venv/bin:/usr/bin
ExecStart=/opt/agentforge/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable agentforge
systemctl start agentforge
systemctl status agentforge
```

## 7. Set up Nginx reverse proxy

Replace `yourdomain.com` with your actual domain (or use your VPS IP).

```bash
cat > /etc/nginx/sites-available/agentforge << 'EOF'
server {
    listen 80;
    server_name yourdomain.com;

    # Landing page
    location / {
        root /opt/agentforge;
        try_files /landing.html =404;
    }

    # API
    location /v1/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }

    # Swagger docs
    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
EOF

ln -sf /etc/nginx/sites-available/agentforge /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
```

## 8. (Optional) Add HTTPS with Let's Encrypt

Only if you have a domain pointed to your VPS:

```bash
certbot --nginx -d yourdomain.com
```

## 9. Verify everything works

```bash
# From anywhere:
curl http://YOUR_VPS_IP/v1/health

# Register an agent:
curl -X POST http://YOUR_VPS_IP/v1/register \
  -H "Content-Type: application/json" \
  -d '{"name": "first-bot"}'
```

## Quick reference commands

```bash
# Check status
systemctl status agentforge

# View logs
journalctl -u agentforge -f

# Restart after code changes
systemctl restart agentforge

# Check nginx logs
tail -f /var/log/nginx/access.log
```

## Firewall (if needed)

```bash
ufw allow 80
ufw allow 443
ufw allow 22
ufw enable
```
