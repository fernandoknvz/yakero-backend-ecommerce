from .auth import router as auth_router
from .catalog import categories_router, products_router, promotions_router
from .health import router as health_router
from .internal import router as internal_router
from .operations import coupons_router, delivery_router
from .orders import router as orders_router
from .payments import router as payments_router
from .users import router as users_router
from .webhooks import router as webhooks_router


VERSIONED_ROUTERS = [
    auth_router,
    products_router,
    categories_router,
    promotions_router,
    orders_router,
    payments_router,
    users_router,
    delivery_router,
    coupons_router,
    internal_router,
]

PUBLIC_ROUTERS = [
    health_router,
    webhooks_router,
]
