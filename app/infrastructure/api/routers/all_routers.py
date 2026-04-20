"""
Routers FastAPI — todos los endpoints del ecommerce Yakero.
Cada router está separado por dominio funcional.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.session import get_db
from ...database.repositories.sql_repositories import (
    SQLUserRepository, SQLOrderRepository, SQLProductRepository,
    SQLAddressRepository, SQLCouponRepository,
)
from ...payment.mercadopago_service import MercadoPagoService
from ....application.use_cases.auth.auth_use_cases import RegisterUserUseCase, LoginUserUseCase
from ....application.use_cases.orders.create_order import CreateOrderUseCase
from ....application.use_cases.orders.order_use_cases import (
    UpdateOrderStatusUseCase, GetOrderUseCase,
    GetUserOrdersUseCase, ConfirmPaymentUseCase,
)
from ....application.use_cases.services.delivery_service import DeliveryFeeService
from ....application.use_cases.services.points_service import PointsService
from ....application.dtos.schemas import (
    RegisterInput, LoginInput, TokenResponse,
    UserOut, UserUpdateInput,
    AddressInput, AddressOut,
    ProductOut, CategoryOut, PromotionOut,
    CreateOrderInput, OrderOut, PosStatusUpdateInput, PosOrderOut,
    CouponValidateInput, CouponOut,
    DeliveryFeeInput, DeliveryFeeOut,
)
from ....domain.exceptions import (
    DomainError, NotFoundError, UnauthorizedError, ValidationError,
)
from ....auth import (
    create_access_token, get_current_user, get_optional_user,
    require_admin, require_pos,
)
from ....domain.models.entities import User

# ── error handler ──────────────────────────────────────────────────────────────

def domain_error_to_http(e: DomainError) -> HTTPException:
    mapping = {
        "NOT_FOUND": 404,
        "UNAUTHORIZED": 401,
        "VALIDATION_ERROR": 422,
        "INVALID_TRANSITION": 409,
        "COUPON_ERROR": 400,
        "INSUFFICIENT_POINTS": 400,
        "MODIFIER_REQUIRED": 422,
        "PAYMENT_ERROR": 502,
    }
    return HTTPException(
        status_code=mapping.get(e.code, 400),
        detail={"code": e.code, "message": e.message},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
auth_router = APIRouter(prefix="/auth", tags=["Autenticación"])


@auth_router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterInput, db: AsyncSession = Depends(get_db)):
    try:
        user = await RegisterUserUseCase(SQLUserRepository(db)).execute(data)
        token = create_access_token(user.id, user.role)
        return TokenResponse(access_token=token, user_id=user.id, role=user.role)
    except DomainError as e:
        raise domain_error_to_http(e)


@auth_router.post("/login", response_model=TokenResponse)
async def login(data: LoginInput, db: AsyncSession = Depends(get_db)):
    try:
        user = await LoginUserUseCase(SQLUserRepository(db)).execute(data)
        token = create_access_token(user.id, user.role)
        return TokenResponse(access_token=token, user_id=user.id, role=user.role)
    except DomainError as e:
        raise domain_error_to_http(e)


@auth_router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCTS ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
products_router = APIRouter(prefix="/products", tags=["Productos"])


@products_router.get("/", response_model=list[ProductOut])
async def list_products(
    category_id: Optional[int] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    repo = SQLProductRepository(db)
    if q:
        return await repo.search(q)
    if category_id:
        return await repo.get_by_category(category_id)
    return await repo.get_all_active()


@products_router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await SQLProductRepository(db).get_by_id(product_id)
    if not product:
        raise HTTPException(404, "Producto no encontrado")
    return product


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORIES ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
categories_router = APIRouter(prefix="/categories", tags=["Categorías"])


@categories_router.get("/menu", response_model=list[CategoryOut])
async def full_menu(db: AsyncSession = Depends(get_db)):
    """
    Devuelve todas las categorías con sus productos y modificadores.
    Este es el endpoint principal que el frontend consume al cargar.
    """
    from ...database.models.orm_models import CategoryORM, ProductORM
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from ...database.repositories.sql_repositories import _map_product

    result = await db.execute(
        select(CategoryORM)
        .where(CategoryORM.is_active == True)
        .options(
            selectinload(CategoryORM.products).selectinload(
                ProductORM.modifier_groups
            )
        )
        .order_by(CategoryORM.sort_order)
    )
    categories = result.scalars().all()

    out = []
    for cat in categories:
        products = [_map_product(p) for p in cat.products if p.is_available]
        out.append(CategoryOut(
            id=cat.id, name=cat.name, slug=cat.slug,
            ticket_tag=cat.ticket_tag, image_url=cat.image_url,
            sort_order=cat.sort_order, products=products,
        ))
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# PROMOTIONS ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
promotions_router = APIRouter(prefix="/promotions", tags=["Promociones"])


@promotions_router.get("/", response_model=list[PromotionOut])
async def list_promotions(db: AsyncSession = Depends(get_db)):
    from ...database.models.orm_models import PromotionORM, PromotionSlotORM
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from datetime import datetime

    now = datetime.utcnow()
    result = await db.execute(
        select(PromotionORM)
        .where(
            PromotionORM.is_active == True,
            (PromotionORM.ends_at == None) | (PromotionORM.ends_at > now),
        )
        .options(
            selectinload(PromotionORM.slots).selectinload(PromotionSlotORM.modifier_groups)
        )
    )
    return result.scalars().all()


# ═══════════════════════════════════════════════════════════════════════════════
# ORDERS ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
orders_router = APIRouter(prefix="/orders", tags=["Pedidos"])


@orders_router.post("/", response_model=OrderOut, status_code=201)
async def create_order(
    data: CreateOrderInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    # Validación guest
    if not current_user and not data.guest_email:
        raise HTTPException(422, "Se requiere guest_email para pedidos sin cuenta.")

    user_repo = SQLUserRepository(db)
    delivery_svc = DeliveryFeeService()
    points_svc = PointsService(user_repo)

    try:
        order = await CreateOrderUseCase(
            order_repo=SQLOrderRepository(db),
            product_repo=SQLProductRepository(db),
            promotion_repo=None,   # se completa en la versión final
            user_repo=user_repo,
            address_repo=SQLAddressRepository(db),
            coupon_repo=SQLCouponRepository(db),
            delivery_service=delivery_svc,
            points_service=points_svc,
        ).execute(data, user_id=current_user.id if current_user else None)

        # Crear preferencia MercadoPago
        mp = MercadoPagoService()
        pref_id = await mp.create_preference(order, back_urls={})

        # Guardar preference_id en el pedido
        await SQLOrderRepository(db).update_payment(order.id, "", "")
        from sqlalchemy import update as sql_update
        from ...database.models.orm_models import OrderORM
        await db.execute(
            sql_update(OrderORM)
            .where(OrderORM.id == order.id)
            .values(mp_preference_id=pref_id)
        )

        order.mp_preference_id = pref_id
        return order

    except DomainError as e:
        raise domain_error_to_http(e)


@orders_router.get("/my", response_model=list[OrderOut])
async def my_orders(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await GetUserOrdersUseCase(SQLOrderRepository(db)).execute(
        current_user.id, skip, limit
    )


@orders_router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    try:
        return await GetOrderUseCase(SQLOrderRepository(db)).execute(
            order_id, user_id=current_user.id if current_user else None
        )
    except DomainError as e:
        raise domain_error_to_http(e)


# ═══════════════════════════════════════════════════════════════════════════════
# USERS ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
users_router = APIRouter(prefix="/users", tags=["Usuarios"])


@users_router.get("/me/addresses", response_model=list[AddressOut])
async def my_addresses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await SQLAddressRepository(db).get_by_user(current_user.id)


@users_router.post("/me/addresses", response_model=AddressOut, status_code=201)
async def add_address(
    data: AddressInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ....domain.models.entities import Address
    addr = Address(
        id=None, user_id=current_user.id, **data.model_dump()
    )
    saved = await SQLAddressRepository(db).create(addr)
    if data.is_default:
        await SQLAddressRepository(db).set_default(current_user.id, saved.id)
    return saved


@users_router.delete("/me/addresses/{address_id}", status_code=204)
async def delete_address(
    address_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    addr = await SQLAddressRepository(db).get_by_id(address_id)
    if not addr or addr.user_id != current_user.id:
        raise HTTPException(404, "Dirección no encontrada")
    await SQLAddressRepository(db).delete(address_id)


@users_router.patch("/me", response_model=UserOut)
async def update_profile(
    data: UserUpdateInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.first_name:
        current_user.first_name = data.first_name
    if data.last_name:
        current_user.last_name = data.last_name
    if data.phone:
        current_user.phone = data.phone
    return await SQLUserRepository(db).update(current_user)


# ═══════════════════════════════════════════════════════════════════════════════
# DELIVERY FEE ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
delivery_router = APIRouter(prefix="/delivery", tags=["Delivery"])


@delivery_router.post("/fee", response_model=DeliveryFeeOut)
async def calculate_delivery_fee(data: DeliveryFeeInput):
    svc = DeliveryFeeService()
    distance, fee, available = await svc.get_info(data.latitude, data.longitude)
    return DeliveryFeeOut(distance_km=distance, fee=fee, is_available=available)


# ═══════════════════════════════════════════════════════════════════════════════
# COUPONS ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
coupons_router = APIRouter(prefix="/coupons", tags=["Cupones"])


@coupons_router.post("/validate", response_model=CouponOut)
async def validate_coupon(
    data: CouponValidateInput,
    db: AsyncSession = Depends(get_db),
):
    from decimal import Decimal
    coupon = await SQLCouponRepository(db).get_by_code(data.coupon_code)
    if not coupon or not coupon.is_active:
        raise HTTPException(400, "Cupón inválido o expirado")
    if coupon.max_uses and coupon.uses_count >= coupon.max_uses:
        raise HTTPException(400, "Cupón sin usos disponibles")
    if data.order_subtotal < coupon.min_order_amount:
        raise HTTPException(
            400, f"Monto mínimo para este cupón: ${coupon.min_order_amount}"
        )
    if coupon.discount_type == "percent":
        calc = (data.order_subtotal * coupon.discount_value / 100).quantize(Decimal("1"))
    else:
        calc = min(coupon.discount_value, data.order_subtotal)
    return CouponOut(
        code=coupon.code,
        discount_type=coupon.discount_type,
        discount_value=coupon.discount_value,
        calculated_discount=calc,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# WEBHOOK ROUTER  (MercadoPago)
# ═══════════════════════════════════════════════════════════════════════════════
webhooks_router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@webhooks_router.post("/mercadopago")
async def mp_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    MercadoPago envía notificaciones a este endpoint.
    Se verifica la firma antes de procesar.
    Idempotente: procesar el mismo payment_id dos veces no tiene efecto.
    """
    body = await request.body()

    mp = MercadoPagoService()
    if x_signature and not mp.verify_webhook_signature(body.decode(), x_signature):
        raise HTTPException(401, "Firma de webhook inválida")

    payload = await request.json()
    topic = payload.get("type") or payload.get("topic")

    if topic != "payment":
        return JSONResponse({"status": "ignored"})

    payment_id = str(payload.get("data", {}).get("id") or payload.get("id", ""))
    if not payment_id:
        return JSONResponse({"status": "no payment id"})

    # Obtener datos del pago desde MP
    from ....config import settings
    import mercadopago
    sdk = mercadopago.SDK(settings.mp_access_token)
    payment_info = sdk.payment().get(payment_id)
    payment_data = payment_info.get("response", {})

    preference_id = payment_data.get("order", {}).get("id") or \
                    payment_data.get("preference_id", "")
    mp_status = payment_data.get("status", "")

    await ConfirmPaymentUseCase(SQLOrderRepository(db)).execute(
        preference_id=preference_id,
        mp_payment_id=payment_id,
        mp_status=mp_status,
    )

    return JSONResponse({"status": "processed"})


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL POS ROUTER  (token de servicio requerido)
# ═══════════════════════════════════════════════════════════════════════════════
internal_router = APIRouter(prefix="/internal", tags=["POS Interno"])


@internal_router.get("/orders/pending", response_model=list[PosOrderOut])
async def get_pending_orders(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_pos),
):
    """
    El POS consulta este endpoint para obtener pedidos pagados pendientes de preparación.
    Devuelve los ítems agrupados por estación (ticket_tag) para facilitar la impresión.
    """
    orders = await SQLOrderRepository(db).get_pending_for_pos()
    result = []
    for order in orders:
        by_station = {}
        for tag, items in order.items_by_ticket_tag().items():
            by_station[tag.value] = items
        result.append(PosOrderOut(
            id=order.id,
            status=order.status,
            delivery_type=order.delivery_type,
            created_at=order.created_at,
            notes=order.notes,
            items_by_station=by_station,
        ))
    return result


@internal_router.patch("/orders/{order_id}/status", response_model=OrderOut)
async def pos_update_status(
    order_id: int,
    data: PosStatusUpdateInput,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_pos),
):
    """
    El POS llama este endpoint para actualizar el estado del pedido.
    Ejemplo: cuando un pedido pasa a 'listo' o 'entregado'.
    """
    try:
        return await UpdateOrderStatusUseCase(SQLOrderRepository(db)).execute(
            order_id, data
        )
    except DomainError as e:
        raise domain_error_to_http(e)
