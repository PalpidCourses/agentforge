# Configuración del Túnel Cloudflare para AgentForge

## Problema Detectado

**Síntoma:** Error 502 Bad Gateway al acceder desde fuera

**Causa:** Hay 2 túneles de Cloudflare apuntando a la IP interna `10.0.0.1:18789`:

1. `pixel.davidpalazon.net` → `10.0.0.1:18789` (VIEJO)
2. `nono.aretaslab.tech` → `10.0.0.1:18789` (NUEVO)

Esto crea un conflicto en Cloudflare.

---

## Solución Paso a Paso

### Paso 1: Acceder al Panel de Cloudflare

1. Abre: https://dash.cloudflare.com/
2. Inicia sesión con tu cuenta
3. Navega a: **Zero Trust → Tunnels**

---

### Paso 2: Eliminar el Túnel Viejo

1. Busca el túnel: `pixel.davidpalazon.net`
2. Haz clic en el botón de **3 puntos** (⋮)
3. Selecciona **Delete tunnel** del menú
4. Confirma la eliminación

**Esto debe eliminar el conflicto de IP.**

---

### Paso 3: Configurar el Túnel Nuevo

1. Busca el túnel: `nono.aretaslab.tech`
2. Haz clic en **Edit**
3. Configura lo siguiente:

**Servicio:** HTTP (no HTTPS/TLS)
**Public hostname:** `nono.aretaslab.tech`
**URL:** `http://localhost:80`
**Network:** (deja en el valor por defecto)

4. Haz clic en **Save**

---

### Paso 4: Verificar

1. Copia el comando Quick Tunnels que aparece en la pantalla
2. Ejecútalo en tu terminal
3. Verifica que aparezca el indicador **"Status: Healthy"** con un checkmark verde

---

### Paso 5: Probar el Acceso

Abre en tu navegador: **http://nono.aretaslab.tech**

Si ves la página de bienvenida de AgentForge, ¡funciona! ✅

---

## Notas Importantes

⚠️ **NO uses la IP interna** (`10.0.0.1:18789` o similar)
⚠️ **El campo URL debe ser `http://localhost:80`**
⚠️ **El campo Service debe ser HTTP**

Si usas HTTPS en lugar de HTTP, AgentForge puede no funcionar correctamente porque espera conexiones HTTP directas.

---

## Solución de Problemas

### Si el Túnel dice "Unhealthy":

1. Verifica que Docker esté corriendo:
   ```bash
   cd /home/ubuntu/development/agentforge
   sudo docker compose ps
   ```

2. Verifica que AgentForge esté escuchando en puerto 8000:
   ```bash
   curl -s http://localhost:8000/v1/health
   ```

3. Reinicia AgentForge:
   ```bash
   cd /home/ubuntu/development/agentforge
   sudo docker compose restart
   ```

### Si sigues recibiendo Error 502:

1. Verifica que NO haya otros túneles activos
2. Borra el caché del navegador
3. Intenta en modo incógnito
4. Espera 1-2 minutos para que la configuración de Cloudflare se propague

---

## Comandos Útiles

```bash
# Ver estado de Docker
sudo docker compose ps

# Ver logs de AgentForge
sudo docker logs agentforge-app-1

# Ver logs de Nginx
sudo docker logs agentforge-nginx-1

# Reiniciar AgentForge
sudo docker compose restart

# Parar AgentForge
sudo docker compose down

# Iniciar AgentForge
sudo docker compose up -d

# Ver si AgentForge está respondiendo en puerto 80
curl -s http://localhost

# Ver health check
curl -s http://localhost/v1/health | python3 -m json.tool
```

---

## Diagnóstico Actual

**Estado local:** ✅ AgentForge funcionando (puertos 80 y 8000)
**Estado túnel:** ⚠️ Conflictos detectados (2 túneles apuntando a IP interna)

**URL de prueba:** http://nono.aretaslab.tech

**Próximo paso:** David debe eliminar el túnel viejo (`pixel.davidpalazon.net`) en el panel de Cloudflare y asegurarse que el nuevo (`nono.aretaslab.tech`) tenga la configuración correcta.

---

**Fecha:** 2026-02-10
**Autor:** Nono 🧙
