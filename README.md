# Yakero Ecommerce — Backend

API REST construida con **FastAPI** + **SQLAlchemy (async)** + **MySQL**.  
Arquitectura limpia: `domain` → `application` → `infrastructure`.

---

## Stack

| Capa | Tecnología |
|---|---|
| Framework | FastAPI 0.115 |
| ORM | SQLAlchemy 2 (async) |
| Driver MySQL | asyncmy |
| Migraciones | Alembic |
| Auth | JWT (python-jose) + bcrypt |
| Pagos | MercadoPago SDK |
| Validación | Pydantic v2 |

---

## Levantar en desarrollo

```bash
# 1. Clonar y entrar al directorio
git clone https://github.com/yakero/yakero-backend.git
cd yakero-backend

# 2. Crear entorno virtual
python -m venv .venv && source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales reales

# 5. Levantar base de datos (Docker)
docker-compose up db -d

# 6. Ejecutar migraciones
alembic upgrade head

# 7. (Opcional) Cargar schema base con categorías seed
mysql -u yakero_user -p yakero_ecommerce < migrations/schema.sql

# 8. Levantar API
uvicorn app.main:app --reload
```

Documentación interactiva disponible en: **http://localhost:8000/docs** (solo con `DEBUG=true`)

---

## Estructura de carpetas

```
app/
├── domain/              # Entidades puras, interfaces de repositorio, excepciones
│   ├── models/          # entities.py, enums.py
│   ├── repositories/    # interfaces.py (contratos abstractos)
│   └── exceptions.py
├── application/         # Casos de uso, DTOs, servicios de dominio
│   ├── use_cases/
│   │   ├── auth/
│   │   ├── orders/
│   │   └── services/    # delivery_service.py, points_service.py
│   └── dtos/            # schemas.py (Pydantic)
├── infrastructure/      # Implementaciones concretas
│   ├── database/
│   │   ├── models/      # orm_models.py (SQLAlchemy)
│   │   ├── repositories/ # sql_repositories.py
│   │   └── session.py
│   ├── api/
│   │   └── routers/     # all_routers.py
│   └── payment/         # mercadopago_service.py
├── auth.py              # JWT helpers, dependencias FastAPI
├── config.py            # Settings con pydantic-settings
└── main.py              # FastAPI app + registro de routers
```

---

## Endpoints principales

### Autenticación
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Registro de usuario |
| POST | `/api/v1/auth/login` | Login → JWT |
| GET  | `/api/v1/auth/me` | Perfil del usuario autenticado |

### Catálogo
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/v1/categories/menu` | Menú completo (categorías + productos + modificadores) |
| GET | `/api/v1/products/` | Listado con filtros (`?category_id=`, `?q=`) |
| GET | `/api/v1/promotions/` | Promociones activas con slots configurables |

### Pedidos
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/v1/orders/` | Crear pedido (auth o guest) |
| GET  | `/api/v1/orders/my` | Historial del usuario autenticado |
| GET  | `/api/v1/orders/{id}` | Detalle de pedido |

### Utilidades
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/v1/delivery/fee` | Calcular costo de envío por coordenadas |
| POST | `/api/v1/coupons/validate` | Validar cupón antes del checkout |

### Webhooks
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/webhooks/mercadopago` | Notificaciones de pago (idempotente) |

### Integración POS (token `pos_service`)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET   | `/api/v1/internal/orders/pending` | Pedidos pagados listos para preparación |
| PATCH | `/api/v1/internal/orders/{id}/status` | Actualizar estado desde el POS |

---

## Flujo de pago MercadoPago

```
Cliente → POST /orders → preferencia MP creada → redirect a MP
         ↓
    Cliente paga en MP
         ↓
    MP → POST /webhooks/mercadopago (con payment_id)
         ↓
    ConfirmPaymentUseCase (idempotente)
         ↓
    order.status = PAID
         ↓
    POS → GET /internal/orders/pending → imprime comanda
```

---

## Integración POS — Estrategia

El POS (Django) se comunica con el ecommerce vía **API interna autenticada** con un token de tipo `pos_service`:

1. El POS hace polling a `GET /internal/orders/pending` para obtener pedidos nuevos
2. La respuesta incluye `items_by_station` agrupado por `ticket_tag` → impresión directa
3. Al cambiar estado (listo/entregado), el POS llama `PATCH /internal/orders/{id}/status`
4. El frontend del ecommerce puede hacer polling a `GET /orders/{id}` para mostrar seguimiento

---

## Tests

```bash
pytest tests/ -v
```

---

## Variables de entorno críticas

Ver `.env.example`. Las más importantes:

- `DATABASE_URL`: conexión MySQL con driver `asyncmy`
- `JWT_SECRET`: generar con `openssl rand -hex 32`
- `MP_ACCESS_TOKEN`: credencial de MercadoPago (producción o sandbox)
- `STORE_LAT` / `STORE_LON`: coordenadas del local para cálculo de delivery
