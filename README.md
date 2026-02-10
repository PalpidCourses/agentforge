# AgentForge - Aretaslab Fork

> Fork de [AgentForge](https://github.com/D0NMEGA/agentforge) para coordinación interna de Aretaslab.

## 📋 Estado

- **Estado:** Revisión en curso
- **Creado:** 2026-02-10
- **Última actualización:** 2026-02-10

## 🎯 Objetivo

Proporcionar infraestructura de coordinación para los 9 agentes de Aretaslab:

- Memoria persistente
- Colas de tareas
- Mensajería entre agentes
- Scheduling
- Webhooks

## ⚠️ Revisión de Seguridad

Ver [SEGURIDAD-REVISION.md](./SEGURIDAD-REVISION.md) para detalles completos.

### Problemas Identificados

| # | Problema | Prioridad |
|---|-----------|------------|
| 1 | No HTTPS obligatorio | 🔴 Crítica |
| 2 | Registro sin rate limiting | 🔴 Alta |
| 3 | TTL sin límite máximo | 🟡 Media |
| 4 | Webhooks sin validación | 🟡 Media |
| 5 | Agent ID no validado | 🟡 Media |

## 🚀 Despliegue

### Desarrollo Local

```bash
# Clonar repositorio
git clone https://github.com/PalpidCourses/agentforge.git
cd agentforge

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar servidor (desarrollo)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Producción (Docker)

```bash
docker compose up -d --build

# Escalar horizontalmente
docker compose up -d --scale app=4
```

## 📦 Requisitos

- Python 3.10+
- Uvicorn
- PostgreSQL (para production)
- Docker (opcional)

## 📚 Documentación

- [AgentForge Original](https://github.com/D0NMEGA/agentforge)
- [Documentación API](http://82.180.139.113/docs)
- [Revisión de Seguridad](./SEGURIDAD-REVISION.md)

## 👥 Aretaslab

Fork mantenido por Aretaslab para uso interno.

- **Sitio web:** https://aretaslab.com
- **GitHub:** https://github.com/aretaslabtech

---

Licencia: Heredada del proyecto original
