# Revisión de Seguridad - AgentForge
**Autor:** Nono (Aretaslab)
**Fecha:** 2026-02-10
**Versión revisada:** main (agentforge/agentforge)

## Resumen Ejecutivo

AgentForge es una infraestructura sólida con 17 servicios funcionales, pero tiene **5 problemas de seguridad crítica** que deben corregirse antes de uso en producción.

---

## 🔴 Problemas Críticos

### 1. No HTTPS Obligatorio

**Ubicación:** `agentforge.py` línea 12
```python
DEFAULT_BASE = "http://82.180.139.113"  # ⚠️ HTTP, no HTTPS
```

**Riesgo:**
- Interceptación de datos en tránsito (MITM attacks)
- Credenciales y mensajes expuestos en texto plano
- Violación de requisitos de producción modernos

**Recomendación:**
```python
DEFAULT_BASE = os.getenv("AGENTFORGE_BASE_URL", "https://api.agentforge.example.com")
```
Y documentar que se debe desplegar con certificado SSL/TLS válido.

---

### 2. Registro sin Rate Limiting

**Ubicación:** `agentforge.py` método `register()`
```python
@staticmethod
def register(name=None, base_url=None):
    url = f"{base_url or AgentForge.DEFAULT_BASE}/v1/register"
    r = requests.post(url, json={"name": name})  # ⚠️ Cualquiera puede registrar
    r.raise_for_status()
```

**Riesgos:**
- **Bot spam** - Cualquiera puede registrar miles de bots sin autenticación
- **Agotamiento de recursos** - Sin límites, un atacante puede DDOSear el registro
- **Sybil attacks** - Atacantes pueden registrar muchos bots y coordinar ataques

**Recomendación:**
```python
@staticmethod
def register(name=None, base_url=None, email=None, captcha_token=None):
    url = f"{base_url or AgentForge.DEFAULT_BASE}/v1/register"

    # Validación básica
    if not name or len(name) < 3 or len(name) > 50:
        raise ValueError("Nombre inválido")

    # Rate limiting (configurable)
    # Opcional: verificar CAPTCHA
    payload = {"name": name}
    if email:
        payload["email"] = email
    if captcha_token:
        payload["captcha"] = captcha_token

    r = requests.post(url, json=payload)
    r.raise_for_status()
```

---

### 3. Faltan Límites de TTL Máximo

**Ubicación:** `agentforge.py` método `memory_set()`
```python
def memory_set(self, key, value, namespace="default", ttl_seconds=None):
    body = {"key": key, "value": value, "namespace": namespace}
    if ttl_seconds:
        body["ttl_seconds"] = ttl_seconds  # ⚠️ Sin límite máximo
    return self._post("/v1/memory", json=body)
```

**Riesgos:**
- **Storage exhaustion** - Un atacante podría llenar el storage con TTLs enormes
- **DoS por memoria** - Bot malicioso puede bloquear el sistema

**Recomendación:**
```python
MAX_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 días máximo

def memory_set(self, key, value, namespace="default", ttl_seconds=None):
    body = {"key": key, "value": value, "namespace": namespace}

    # Validar TTL
    if ttl_seconds is not None:
        if ttl_seconds < 0:
            raise ValueError("TTL debe ser positivo")
        if ttl_seconds > MAX_TTL_SECONDS:
            raise ValueError(f"TTL máximo es {MAX_TTL_SECONDS} segundos (30 días)")

    if ttl_seconds:
        body["ttl_seconds"] = ttl_seconds

    return self._post("/v1/memory", json=body)
```

---

### 4. Webhooks sin Validación de URL

**Ubicación:** `agentforge.py` método `webhook_create()`
```python
def webhook_create(self, url, event_types, secret=None):
    body = {"url": url, "event_types": event_types}  # ⚠️ No valida URL
    if secret:
        body["secret"] = secret
    return self._post("/v1/webhooks", json=body)
```

**Riesgos:**
- **SSRF (Server-Side Request Forgery)** - El servidor podría hacer peticiones arbitrarias
- **Webhook poisoning** - Un atacante podría registrar webhooks maliciosos
- **Phishing** - URLs engañosas podrían pasar como válidas

**Recomendación:**
```python
import re

def _validate_webhook_url(url):
    """Valida que la URL del webhook es segura."""
    # Solo permitir HTTPS
    if not url.startswith("https://"):
        raise ValueError("Webhook URL debe usar HTTPS")

    # Prevenir SSRF
    parsed = urlparse(url)
    if parsed.hostname in ['localhost', '127.0.0.1']:
        raise ValueError("No se permiten webhooks a localhost")

    # Lista de dominios permitidos (opcional, para producción)
    # allowed_domains = os.getenv("AGENTFORGE_ALLOWED_DOMAINS", "").split(",")
    # if parsed.hostname not in allowed_domains:
    #     raise ValueError(f"Dominio {parsed.hostname} no está permitido")

    return True

def webhook_create(self, url, event_types, secret=None):
    _validate_webhook_url(url)

    body = {"url": url, "event_types": event_types}
    if secret:
        body["secret"] = secret
    return self._post("/v1/webhooks", json=body)
```

---

### 5. Falta Validación de Agent ID en Mensajería

**Ubicación:** `agentforge.py` método `send_message()`
```python
def send_message(self, to_agent, payload, channel="default"):
    return self._post("/v1/relay/send", json={
        "to_agent": to_agent,  # ⚠️ No valida si existe
        "channel": channel,
        "payload": payload,
    })
```

**Riesgos:**
- **Envíos a agentes inexistentes** sin feedback
- **Fuga de información** - Perfil de bots no validado
- **Orphaned messages** - Mensajes perdidos sin destinatario

**Recomendación:**
```python
def _validate_agent_id(agent_id):
    """Valida formato y longitud del agent_id."""
    if not agent_id or not isinstance(agent_id, str):
        raise ValueError("agent_id debe ser un string")

    # Validar formato: agent_ seguido de UUID v4 o base62
    if not re.match(r'^agent_[a-zA-Z0-9\-_]+$', agent_id):
        raise ValueError("Formato de agent_id inválido")

    return True

def send_message(self, to_agent, payload, channel="default"):
    _validate_agent_id(to_agent)

    return self._post("/v1/relay/send", json={
        "to_agent": to_agent,
        "channel": channel,
        "payload": payload,
    })
```

---

## 🟡 Mejoras Recomendadas

### 6. Manejo de Errores Más Informativo

**Estado actual:**
```python
r.raise_for_status()  # ⚠️ Excepción genérica sin contexto
```

**Recomendación:**
```python
class AgentForgeError(Exception):
    """Base exception para errores de AgentForge."""
    pass

class AuthenticationError(AgentForgeError):
    """Fallo de autenticación."""
    pass

class RateLimitError(AgentForgeError):
    """Rate limit excedido."""
    pass

class AgentNotFoundError(AgentForgeError):
    """Agente no encontrado."""
    pass

# Ejemplo de uso con contexto
try:
    af = AgentForge(api_key="af_key")
    af.memory_set("key", "value")
except AuthenticationError as e:
    logger.error(f"Error de autenticación: {e}")
except RateLimitError as e:
    logger.warning(f"Rate limit: {e}")
```

---

### 7. Advertencia de IP Pública en Documentación

**Estado actual:** El README muestra la IP pública `http://82.180.139.113` sin advertencias.

**Recomendación:**
```markdown
## ⚠️ Seguridad

Para **uso en producción**, AgentForge debe desplegarse con:

1. **HTTPS obligatorio** - Certificado TLS/SSL válido
2. **Dominio personalizado** - Evitar IPs públicas
3. **Firewall** - Limitar acceso por IP
4. **VPN/SSH tunnel** - Para acceso sin exposición pública
```

---

## ✅ Lo Que Está Bien

1. **AES-128 Fernet** para storage ✅
2. **HMAC-SHA256** para webhooks ✅
3. **Rate limiting documentado** (120 req/min) ✅
4. **Aislamiento de namespaces** ✅
5. **Escalado horizontal con Docker** ✅

---

## 📋 Resumen de Recomendaciones

| Prioridad | Problema | Esfuerzo | Impacto |
|-----------|-----------|-----------|----------|
| 🔴 Alta | Falta HTTPS en configuración | Bajo | Crítico |
| 🔴 Alta | Registro sin rate limiting | Medio | Alto |
| 🟡 Media | TTL sin límite máximo | Bajo | Medio |
| 🟡 Media | Webhooks sin validación | Medio | Alto |
| 🟡 Media | Agent ID no validado | Bajo | Medio |
| 🟢 Baja | Mejorar mensajes de error | Medio | Bajo |

---

## Sobre Esta Revisión

**Propósito:** Proveer feedback constructivo al proyecto AgentForge.

**Enfoque:** Seguridad, robustez y preparación para producción.

**Contacto:** Nono - Aretaslab (nono@aretaslab.com)

---

**Licencia:** Esta revisión se comparte bajo los mismos términos que el proyecto original (MIT o según corresponda).
