# Yakero Ecommerce Backend

Backend REST para ecommerce Yakero construido con FastAPI, SQLAlchemy async, MySQL y Alembic.

## Stack

- FastAPI + Pydantic v2
- SQLAlchemy 2 async + asyncmy
- MySQL 8
- Alembic
- JWT con python-jose + passlib/bcrypt
- MercadoPago SDK

## Arquitectura

El proyecto sigue una separacion por capas:

```text
app/
  domain/          Entidades, enums, excepciones e interfaces
  application/     Casos de uso, DTOs y servicios de aplicacion
  infrastructure/  API, base de datos, repositorios SQL y pagos
  config.py        Settings centralizados
  auth.py          JWT y dependencias de seguridad
  main.py          FastAPI app, middlewares y routers
```

Convencion esperada para crecer:

- `domain` no debe depender de FastAPI, SQLAlchemy ni SDKs externos.
- `application` orquesta casos de uso y depende de interfaces del dominio.
- `infrastructure` implementa detalles concretos: routers, ORM, repos SQL, pagos.
- Nuevos modulos grandes como carrito, checkout y pagos deben entrar primero como casos de uso y contratos antes de exponer endpoints.

Routers HTTP ya quedaron particionados por responsabilidad:

- `api/routers/auth.py`
- `api/routers/catalog.py`
- `api/routers/orders.py`
- `api/routers/users.py`
- `api/routers/operations.py`
- `api/routers/webhooks.py`
- `api/routers/internal.py`
- `api/routers/health.py`

## Arranque local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
docker compose up db -d
alembic upgrade head
uvicorn app.main:app --reload
```

La base Docker expone MySQL en `localhost:3310`. Si usas otro MySQL local, ajusta `DATABASE_URL`.

## Variables importantes

- `ENVIRONMENT`: `development`, `staging` o `production`.
- `DEBUG`: habilita `/docs` y `/redoc` cuando es `true`.
- `DATABASE_URL`: URL async de MySQL usando `mysql+asyncmy`.
- `JWT_SECRET`: obligatorio fuerte para staging/produccion.
- `ALLOWED_ORIGINS`: lista separada por comas o JSON array.
- `MP_ACCESS_TOKEN`: requerido para crear preferencias reales de MercadoPago.
- `STORE_LAT` / `STORE_LON`: origen para calculo de delivery.

## Endpoints principales

- `GET /health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/categories/menu`
- `GET /api/v1/products/`
- `GET /api/v1/promotions/`
- `POST /api/v1/orders/`
- `GET /api/v1/orders/my`
- `GET /api/v1/orders/{order_id}`
- `POST /api/v1/delivery/fee`
- `POST /api/v1/coupons/validate`
- `POST /webhooks/mercadopago`
- `GET /api/v1/internal/orders/pending`
- `PATCH /api/v1/internal/orders/{order_id}/status`

## Migraciones

Alembic esta configurado para leer metadata desde `app.infrastructure.database.models.orm_models.Base`.

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Si tu base local ya fue creada previamente con `schema.sql` o con SQL manual y aun no tiene versionado Alembic, alinea la linea base una sola vez:

```bash
alembic stamp head
```

El archivo `migrations/schema.sql` se conserva solo como respaldo historico/manual. La fuente principal para evolucionar el esquema ahora es Alembic y la migracion inicial vive en `migrations/versions/20260423_0001_initial_schema.py`.

## Tests

```bash
pytest -q
```

## Notas de hardening

- No usar `JWT_SECRET` de ejemplo fuera de desarrollo.
- Mantener `DEBUG=false` en staging/produccion.
- Configurar CORS con dominios explicitos.
- El webhook de MercadoPago debe validarse con secreto real.
- Evitar agregar logica ORM directa en routers nuevos; preferir repositorios y casos de uso.
