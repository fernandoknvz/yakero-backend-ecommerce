# Deploy Docker Produccion

Guia operativa para desplegar el backend ecommerce Yakero en VPS o Portainer.

## Archivos

- `Dockerfile`: imagen productiva multi-stage, usuario no root, `uvicorn` sin reload.
- `.dockerignore`: evita copiar `.env`, `.git`, virtualenvs, caches y logs al build context.
- `docker-compose.prod.yml`: stack standalone con `api`, `db` MySQL y servicio opcional `api-migrate`.
- `.env.example`: plantilla sin secretos reales.

## Checklist Produccion

- `ENVIRONMENT=production`
- `DEBUG=false`
- `TESTING=false`
- `JWT_SECRET` fuerte generado con `openssl rand -hex 32`
- `ALLOWED_ORIGINS` sin wildcard y solo dominios reales
- `API_BASE_URL` / `BACKEND_PUBLIC_URL` publicos con HTTPS
- `FRONTEND_PUBLIC_URL` / `APP_BASE_URL` publicos con HTTPS
- `MP_ENV=production`
- `MP_ACCESS_TOKEN` productivo, no `TEST-`
- `MP_WEBHOOK_SECRET` configurado
- Passwords MySQL reales y distintos de los ejemplos
- Puerto `API_PORT` publicado solo si corresponde; idealmente detras de reverse proxy HTTPS
- Backup del volumen MySQL configurado antes de operar ventas reales

## Build

```bash
cp .env.example .env
# Editar .env con valores reales antes de continuar.
docker compose -f docker-compose.prod.yml build
```

Para validar la sintaxis sin cargar secretos locales:

```bash
ENV_FILE=.env.example docker compose --env-file .env.example -f docker-compose.prod.yml config
```

En PowerShell:

```powershell
$env:ENV_FILE=".env.example"; docker compose --env-file .env.example -f docker-compose.prod.yml config
```

## Levantar Servicios

```bash
docker compose -f docker-compose.prod.yml up -d db api
```

Verificar health:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost:8000/health
```

## Migraciones

Las migraciones no corren dentro del `CMD` principal de la API. Ejecutarlas de forma explicita:

```bash
docker compose -f docker-compose.prod.yml --profile tools run --rm api-migrate
```

Alternativa con API ya arriba:

```bash
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

Antes de migrar en produccion:

- Revisar `alembic history`.
- Tener backup reciente de MySQL.
- Ejecutar primero en staging con copia representativa.

## Logs

```bash
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f db
```

## Rollback Basico

1. Detener API nueva:

```bash
docker compose -f docker-compose.prod.yml stop api
```

2. Volver a levantar la imagen/tag anterior desde Portainer o desde compose si se usa tag versionado.

3. Si hubo migraciones, validar si son reversibles. No ejecutar downgrade automaticamente en produccion sin revisar datos.

4. Confirmar:

```bash
curl http://localhost:8000/health
docker compose -f docker-compose.prod.yml logs --tail=100 api
```

## Validar Que `.env` No Entre En La Imagen

`.dockerignore` excluye `.env` y `.env.*`. Para revisar manualmente:

```bash
docker build -t yakero-backend:check .
docker run --rm yakero-backend:check sh -c "test ! -f /app/.env && echo ok"
```

## Portainer

1. Crear stack con `docker-compose.prod.yml`.
2. Cargar variables desde `.env` en el stack o como env vars seguras de Portainer. Si usas otro nombre de archivo, define `ENV_FILE`.
3. Desplegar `db` y `api`.
4. Ejecutar migraciones con el servicio `api-migrate` usando profile `tools` o desde consola del contenedor `api`.
5. Configurar reverse proxy HTTPS hacia `api:8000`.

## Notas

- `docker-compose.yml` queda orientado a desarrollo local.
- `docker-compose.prod.yml` es el archivo recomendado para VPS/Portainer.
- No guardar secretos reales en Git.
- No usar `--reload` en produccion.
