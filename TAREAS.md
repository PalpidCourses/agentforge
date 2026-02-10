# Primeras Tareas - Aretaslab AgentForge

## 🎯 Objetivo

Configurar y mejorar AgentForge para uso de Aretaslab.

---

## 📋 Tareas

### Prioridad 🔴 Crítica

- [ ] **SEC-1:** Implementar HTTPS obligatorio (self-signed cert válido para desarrollo)
- [ ] **SEC-2:** Añadir rate limiting al registro de agentes
- [ ] **INFRA-1:** Self-hostar con HTTPS propio (no IP pública)

### Prioridad 🟡 Alta

- [ ] **SDK-1:** Añadir validación de URLs de webhook
- [ ] **SDK-2:** Implementar límite máximo de TTL (30 días)
- [ ] **SDK-3:** Validar agent_id antes de enviar mensajes

### Prioridad 🟢 Media

- [ ] **DOC-1:** Documentar procedimiento de despliegue HTTPS
- [ ] **DOC-2:** Crear guía de primeros pasos para cada agente
- [ ] **DOC-3:** Escribir ejemplos de uso de cada servicio

### Prioridad 🔵 Baja

- [ ] **UX-1:** Mejorar mensajes de error con contexto específico
- [ ] **TEST-1:** Añadir tests unitarios básicos
- [ ] **TEST-2:** Documentar tests de integración

---

## 🔧 Configuración

**Repositorio:** https://github.com/PalpidCourses/agentforge
**Review de seguridad:** [SEGURIDAD-REVISION.md](./SEGURIDAD-REVISION.md)

---

## 📝 Notas

- Marc y Àlex: revisar antes de usar en producción
- Preguntar por HTTPS propio para self-hosting
- Documentar todo en GitHub antes de desplegar
