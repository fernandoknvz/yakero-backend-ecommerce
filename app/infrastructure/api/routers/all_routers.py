"""Compat shim for older imports.

Routers were split into focused modules. New code should import from
`app.infrastructure.api.routers` or the specific module directly.
"""

from . import (
    auth_router,
    categories_router,
    coupons_router,
    delivery_router,
    internal_router,
    orders_router,
    payments_router,
    products_router,
    promotions_router,
    users_router,
    webhooks_router,
)

__all__ = [
    "auth_router",
    "products_router",
    "categories_router",
    "promotions_router",
    "orders_router",
    "payments_router",
    "users_router",
    "delivery_router",
    "coupons_router",
    "webhooks_router",
    "internal_router",
]
