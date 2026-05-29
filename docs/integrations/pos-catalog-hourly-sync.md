# Sincronizacion Horaria Catalogo POS DEV

Guia operativa para automatizar la sincronizacion POS DEV -> Ecommerce DEV cada 1 hora usando Render Cron Job.

## Recomendacion

Usar un Render Cron Job que llame al endpoint interno del ecommerce:

```text
POST /api/v1/internal/pos/catalog-sync
```

No se recomienda crear un scheduler interno en FastAPI para esta fase. El repo no tiene Celery, APScheduler, cron interno ni `render.yaml`, y Render Cron Job deja la ejecucion horaria fuera del proceso web.

## Frecuencia

```text
Cada 1 hora
```

Expresion cron sugerida:

```text
0 * * * *
```

## Endpoint

Ecommerce DEV:

```text
https://yakero-backend-ecommerce-dev.onrender.com/api/v1/internal/pos/catalog-sync
```

Metodo:

```text
POST
```

Header requerido:

```text
X-Internal-Token: <INTERNAL_BOOTSTRAP_TOKEN>
```

## Variables Necesarias

En Ecommerce DEV:

```text
INTERNAL_BOOTSTRAP_TOKEN=<token interno ecommerce>
POS_API_BASE_URL=https://posdev.tehagolaweb.cl
POS_INTERNAL_TOKEN=<token POS>
```

Para el Cron Job, usar `INTERNAL_BOOTSTRAP_TOKEN` como token de llamada al ecommerce.

No usar `POS_INTERNAL_TOKEN` como token del Cron Job. Ese token solo corresponde a llamadas Ecommerce -> POS.

## Comando Manual

PowerShell:

```powershell
curl.exe -i -X POST -H "X-Internal-Token: <INTERNAL_BOOTSTRAP_TOKEN>" "https://yakero-backend-ecommerce-dev.onrender.com/api/v1/internal/pos/catalog-sync"
```

Shell:

```bash
curl -fsS -X POST \
  -H "X-Internal-Token: ${INTERNAL_BOOTSTRAP_TOKEN}" \
  "https://yakero-backend-ecommerce-dev.onrender.com/api/v1/internal/pos/catalog-sync"
```

## Render Cron Job Manual

Como el repo no tiene `render.yaml`, configurar manualmente en Render:

1. Crear un nuevo `Cron Job`.
2. Usar frecuencia horaria: `0 * * * *`.
3. Configurar `INTERNAL_BOOTSTRAP_TOKEN` como variable secreta del Cron Job.
4. Usar un comando que ejecute el `POST` contra Ecommerce DEV.

Comando sugerido si el entorno del Cron Job tiene `curl`:

```bash
curl -fsS -X POST -H "X-Internal-Token: ${INTERNAL_BOOTSTRAP_TOKEN}" "https://yakero-backend-ecommerce-dev.onrender.com/api/v1/internal/pos/catalog-sync"
```

Alternativa sin depender de `curl`, usando Python:

```bash
python -c "import os, urllib.request; req = urllib.request.Request('https://yakero-backend-ecommerce-dev.onrender.com/api/v1/internal/pos/catalog-sync', method='POST', headers={'X-Internal-Token': os.environ['INTERNAL_BOOTSTRAP_TOKEN']}); print(urllib.request.urlopen(req, timeout=120).read().decode())"
```

## Resultado Esperado

Respuesta exitosa:

```json
{
  "ok": true,
  "source": "pos",
  "products": {
    "received": 183,
    "created": 0,
    "updated": 183,
    "deactivated": 0
  },
  "promotions": {
    "received": 6,
    "created": 0,
    "updated": 6,
    "deactivated": 0
  },
  "branches": {
    "received": 0,
    "created": 0,
    "updated": 0,
    "deactivated": 0
  },
  "categories_created": 0,
  "categories_updated": 4,
  "skipped": 0,
  "errors": []
}
```

Los valores `created`, `updated` y `deactivated` pueden variar segun cambios en el POS.

## Auditoria Posterior

Despues de una ejecucion, revisar:

```text
GET /api/v1/internal/pos/catalog-audit
```

PowerShell:

```powershell
curl.exe -i -H "X-Internal-Token: <INTERNAL_BOOTSTRAP_TOKEN>" "https://yakero-backend-ecommerce-dev.onrender.com/api/v1/internal/pos/catalog-audit"
```

Para identificar productos o promociones con problemas puntuales:

```text
GET /api/v1/internal/pos/catalog-audit/details
```

## Observabilidad

El endpoint `catalog-sync` registra:

- Inicio del sync.
- Final exitoso con conteos de productos, promociones, branches, categorias, skipped y errores.
- Error controlado del POS con mensaje sanitizado.

## Seguridad

- No exponer tokens en logs.
- No usar `POS_INTERNAL_TOKEN` como token del Cron Job.
- No dejar `POST /api/v1/internal/pos/catalog-sync` accesible sin `X-Internal-Token`.
- Guardar `INTERNAL_BOOTSTRAP_TOKEN` como secreto en Render.
- Rotar tokens si fueron compartidos en tickets, capturas, logs o comandos pegados en canales publicos.

