from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...domain.models.enums import ModifierType, TicketTag, UserRole
from ...application.use_cases.auth.auth_use_cases import pwd_context
from .models.orm_models import (
    AddressORM,
    CategoryORM,
    CouponORM,
    ModifierGroupORM,
    ModifierOptionORM,
    ProductORM,
    UserORM,
)


DEMO_USER_EMAIL = "feradmin@example.com"
DEMO_USER_PASSWORD = "Admin123456"
DEMO_USER_PHONE = "+56911112222"
DEMO_COUPON_CODE = "DEV10"


@dataclass(frozen=True)
class CategorySeed:
    slug: str
    name: str
    sort_order: int
    ticket_tag: TicketTag
    image_url: str | None = None


@dataclass(frozen=True)
class ProductSeed:
    slug: str
    category_slug: str
    sku: str
    name: str
    description: str
    price: Decimal
    ticket_tag: TicketTag
    sort_order: int
    image_url: str | None = None


@dataclass(frozen=True)
class ModifierGroupSeed:
    product_slug: str
    name: str
    modifier_type: ModifierType
    min_selections: int
    max_selections: int
    is_required: bool


@dataclass(frozen=True)
class ModifierOptionSeed:
    product_slug: str
    group_name: str
    name: str
    extra_price: Decimal
    is_available: bool = True


@dataclass(frozen=True)
class SeedSummary:
    active_categories: int
    total_products: int
    active_products: int
    demo_user_email: str
    demo_coupon_code: str


CATEGORY_SEEDS = [
    CategorySeed("rolls", "Rolls", 1, TicketTag.COCINA_SUSHI),
    CategorySeed("especial-rolls", "Especial Rolls", 2, TicketTag.COCINA_SUSHI),
    CategorySeed("hand-rolls", "Hand Rolls", 3, TicketTag.COCINA_SUSHI),
    CategorySeed("gohan", "Gohan", 4, TicketTag.COCINA_SUSHI),
    CategorySeed("gyosas", "Gyosas", 5, TicketTag.COCINA_SUSHI),
    CategorySeed("comida-casera", "Comida Casera", 6, TicketTag.COCINA_SANDWICH),
    CategorySeed("postres", "Postres", 7, TicketTag.CAJA),
    CategorySeed("bebidas", "Bebidas", 8, TicketTag.CAJA),
]

PRODUCT_SEEDS = [
    ProductSeed(
        slug="yakero-roll-acevichado",
        category_slug="rolls",
        sku="ROLL-ACEVICHADO",
        name="Yakero Roll Acevichado",
        description="Roll de la casa con topping acevichado y configuracion de proteina.",
        price=Decimal("6990"),
        ticket_tag=TicketTag.COCINA_SUSHI,
        sort_order=1,
        image_url="https://images.yakero.local/roll-acevichado.jpg",
    ),
    ProductSeed(
        slug="dragon-roll",
        category_slug="especial-rolls",
        sku="ROLL-DRAGON",
        name="Dragon Roll",
        description="Roll especial con palta y salsa tare.",
        price=Decimal("7990"),
        ticket_tag=TicketTag.COCINA_SUSHI,
        sort_order=1,
        image_url="https://images.yakero.local/dragon-roll.jpg",
    ),
    ProductSeed(
        slug="hand-roll-salmon-queso",
        category_slug="hand-rolls",
        sku="HAND-SALMON-QUESO",
        name="Hand Roll Salmon Queso",
        description="Hand roll fresco con salmon y queso crema.",
        price=Decimal("4990"),
        ticket_tag=TicketTag.COCINA_SUSHI,
        sort_order=1,
        image_url="https://images.yakero.local/hand-roll-salmon.jpg",
    ),
    ProductSeed(
        slug="gohan-pollo-teriyaki",
        category_slug="gohan",
        sku="GOHAN-POLLO-TERIYAKI",
        name="Gohan Pollo Teriyaki",
        description="Base de arroz gohan con pollo teriyaki y toppings.",
        price=Decimal("7490"),
        ticket_tag=TicketTag.COCINA_SUSHI,
        sort_order=1,
        image_url="https://images.yakero.local/gohan-pollo.jpg",
    ),
    ProductSeed(
        slug="gyosas-camaron",
        category_slug="gyosas",
        sku="GYOZA-CAMARON",
        name="Gyosas de Camaron",
        description="Porcion de gyosas rellenas de camaron.",
        price=Decimal("4590"),
        ticket_tag=TicketTag.COCINA_SUSHI,
        sort_order=1,
        image_url="https://images.yakero.local/gyosas-camaron.jpg",
    ),
    ProductSeed(
        slug="lasagna-casera",
        category_slug="comida-casera",
        sku="CASERA-LASAGNA",
        name="Lasagna Casera",
        description="Lasagna horneada con salsa bolognesa.",
        price=Decimal("8990"),
        ticket_tag=TicketTag.COCINA_SANDWICH,
        sort_order=1,
        image_url="https://images.yakero.local/lasagna.jpg",
    ),
    ProductSeed(
        slug="cheesecake-frutilla",
        category_slug="postres",
        sku="POSTRE-CHEESECAKE",
        name="Cheesecake Frutilla",
        description="Porcion individual de cheesecake con salsa de frutilla.",
        price=Decimal("3990"),
        ticket_tag=TicketTag.CAJA,
        sort_order=1,
        image_url="https://images.yakero.local/cheesecake.jpg",
    ),
    ProductSeed(
        slug="limonada-jengibre",
        category_slug="bebidas",
        sku="BEBIDA-LIMONADA-JENGIBRE",
        name="Limonada Jengibre",
        description="Limonada natural con jengibre y menta.",
        price=Decimal("2990"),
        ticket_tag=TicketTag.CAJA,
        sort_order=1,
        image_url="https://images.yakero.local/limonada-jengibre.jpg",
    ),
]

MODIFIER_GROUP_SEEDS = [
    ModifierGroupSeed(
        product_slug="yakero-roll-acevichado",
        name="Proteina",
        modifier_type=ModifierType.SINGLE,
        min_selections=1,
        max_selections=1,
        is_required=True,
    ),
    ModifierGroupSeed(
        product_slug="yakero-roll-acevichado",
        name="Salsas",
        modifier_type=ModifierType.MULTIPLE,
        min_selections=0,
        max_selections=2,
        is_required=False,
    ),
]

MODIFIER_OPTION_SEEDS = [
    ModifierOptionSeed("yakero-roll-acevichado", "Proteina", "Salmon", Decimal("0")),
    ModifierOptionSeed("yakero-roll-acevichado", "Proteina", "Camarin", Decimal("500")),
    ModifierOptionSeed("yakero-roll-acevichado", "Proteina", "Pollo", Decimal("0")),
    ModifierOptionSeed("yakero-roll-acevichado", "Salsas", "Teriyaki", Decimal("250")),
    ModifierOptionSeed("yakero-roll-acevichado", "Salsas", "Spicy Mayo", Decimal("300")),
]


def _assert_local_safe() -> None:
    if settings.is_production:
        raise RuntimeError("El seed dev esta deshabilitado en produccion.")


async def _ensure_categories(session: AsyncSession) -> dict[str, CategoryORM]:
    categories_by_slug: dict[str, CategoryORM] = {}
    for seed in CATEGORY_SEEDS:
        result = await session.execute(select(CategoryORM).where(CategoryORM.slug == seed.slug))
        category = result.scalar_one_or_none()
        if category is None:
            category = CategoryORM(
                slug=seed.slug,
                name=seed.name,
                sort_order=seed.sort_order,
                ticket_tag=seed.ticket_tag,
                image_url=seed.image_url,
                is_active=True,
            )
            session.add(category)
        else:
            category.name = seed.name
            category.sort_order = seed.sort_order
            category.ticket_tag = seed.ticket_tag
            category.image_url = seed.image_url
            category.is_active = True
        await session.flush()
        categories_by_slug[seed.slug] = category
    return categories_by_slug


async def _ensure_products(
    session: AsyncSession,
    categories_by_slug: dict[str, CategoryORM],
) -> dict[str, ProductORM]:
    products_by_slug: dict[str, ProductORM] = {}
    for seed in PRODUCT_SEEDS:
        category = categories_by_slug[seed.category_slug]
        result = await session.execute(select(ProductORM).where(ProductORM.slug == seed.slug))
        product = result.scalar_one_or_none()
        if product is None:
            product = ProductORM(
                slug=seed.slug,
                sku=seed.sku,
                name=seed.name,
                description=seed.description,
                price=seed.price,
                image_url=seed.image_url,
                ticket_tag=seed.ticket_tag,
                is_available=True,
                sort_order=seed.sort_order,
                category_id=category.id,
            )
            session.add(product)
        else:
            product.category_id = category.id
            product.sku = seed.sku
            product.name = seed.name
            product.description = seed.description
            product.price = seed.price
            product.image_url = seed.image_url
            product.ticket_tag = seed.ticket_tag
            product.is_available = True
            product.sort_order = seed.sort_order
        await session.flush()
        products_by_slug[seed.slug] = product
    return products_by_slug


async def _ensure_modifier_groups(
    session: AsyncSession,
    products_by_slug: dict[str, ProductORM],
) -> dict[tuple[str, str], ModifierGroupORM]:
    groups: dict[tuple[str, str], ModifierGroupORM] = {}
    for seed in MODIFIER_GROUP_SEEDS:
        product = products_by_slug[seed.product_slug]
        result = await session.execute(
            select(ModifierGroupORM).where(
                ModifierGroupORM.product_id == product.id,
                ModifierGroupORM.name == seed.name,
            )
        )
        group = result.scalar_one_or_none()
        if group is None:
            group = ModifierGroupORM(
                product_id=product.id,
                promotion_slot_id=None,
                name=seed.name,
                modifier_type=seed.modifier_type,
                min_selections=seed.min_selections,
                max_selections=seed.max_selections,
                is_required=seed.is_required,
            )
            session.add(group)
        else:
            group.modifier_type = seed.modifier_type
            group.min_selections = seed.min_selections
            group.max_selections = seed.max_selections
            group.is_required = seed.is_required
        await session.flush()
        groups[(seed.product_slug, seed.name)] = group
    return groups


async def _ensure_modifier_options(
    session: AsyncSession,
    groups: dict[tuple[str, str], ModifierGroupORM],
) -> None:
    for seed in MODIFIER_OPTION_SEEDS:
        group = groups[(seed.product_slug, seed.group_name)]
        result = await session.execute(
            select(ModifierOptionORM).where(
                ModifierOptionORM.group_id == group.id,
                ModifierOptionORM.name == seed.name,
            )
        )
        option = result.scalar_one_or_none()
        if option is None:
            option = ModifierOptionORM(
                group_id=group.id,
                name=seed.name,
                extra_price=seed.extra_price,
                is_available=seed.is_available,
            )
            session.add(option)
        else:
            option.extra_price = seed.extra_price
            option.is_available = seed.is_available
        await session.flush()


async def _ensure_demo_user(session: AsyncSession) -> UserORM:
    result = await session.execute(select(UserORM).where(UserORM.email == DEMO_USER_EMAIL))
    user = result.scalar_one_or_none()
    desired_hash = None
    if user is None:
        desired_hash = pwd_context.hash(DEMO_USER_PASSWORD)
        user = UserORM(
            email=DEMO_USER_EMAIL,
            password_hash=desired_hash,
            first_name="Fernando",
            last_name="Admin",
            phone=DEMO_USER_PHONE,
            role=UserRole.ADMIN,
            is_active=True,
            is_guest=False,
            points_balance=0,
            created_at=datetime.now(UTC),
        )
        session.add(user)
    else:
        if not pwd_context.verify(DEMO_USER_PASSWORD, user.password_hash):
            desired_hash = pwd_context.hash(DEMO_USER_PASSWORD)
        if desired_hash is not None:
            user.password_hash = desired_hash
        user.first_name = "Fernando"
        user.last_name = "Admin"
        user.phone = DEMO_USER_PHONE
        user.role = UserRole.ADMIN
        user.is_active = True
        user.is_guest = False
    await session.flush()
    return user


async def _ensure_demo_address(session: AsyncSession, user: UserORM) -> None:
    result = await session.execute(
        select(AddressORM).where(
            AddressORM.user_id == user.id,
            AddressORM.label == "Casa Demo",
        )
    )
    address = result.scalar_one_or_none()
    if address is None:
        address = AddressORM(
            user_id=user.id,
            label="Casa Demo",
            street="Av. Providencia",
            number="1234",
            commune="Providencia",
            city="Santiago",
            latitude=-33.4258,
            longitude=-70.6152,
            notes="Depto 101",
            is_default=True,
        )
        session.add(address)
    else:
        address.street = "Av. Providencia"
        address.number = "1234"
        address.commune = "Providencia"
        address.city = "Santiago"
        address.latitude = -33.4258
        address.longitude = -70.6152
        address.notes = "Depto 101"
        address.is_default = True
    await session.flush()


async def _ensure_demo_coupon(session: AsyncSession) -> None:
    result = await session.execute(select(CouponORM).where(CouponORM.code == DEMO_COUPON_CODE))
    coupon = result.scalar_one_or_none()
    if coupon is None:
        coupon = CouponORM(
            code=DEMO_COUPON_CODE,
            discount_type="percent",
            discount_value=Decimal("10"),
            min_order_amount=Decimal("5000"),
            max_uses=None,
            uses_count=0,
            user_id=None,
            expires_at=None,
            is_active=True,
        )
        session.add(coupon)
    else:
        coupon.discount_type = "percent"
        coupon.discount_value = Decimal("10")
        coupon.min_order_amount = Decimal("5000")
        coupon.max_uses = None
        coupon.is_active = True
    await session.flush()


async def _normalize_enum_storage(session: AsyncSession) -> None:
    updates = [
        ("users", "role", {"CUSTOMER": "customer", "ADMIN": "admin", "POS_SERVICE": "pos_service"}),
        (
            "categories",
            "ticket_tag",
            {
                "COCINA_SUSHI": "cocina_sushi",
                "COCINA_SANDWICH": "cocina_sandwich",
                "CAJA": "caja",
                "NONE": "ninguna",
            },
        ),
        (
            "products",
            "ticket_tag",
            {
                "COCINA_SUSHI": "cocina_sushi",
                "COCINA_SANDWICH": "cocina_sandwich",
                "CAJA": "caja",
                "NONE": "ninguna",
            },
        ),
        (
            "promotion_slots",
            "ticket_tag",
            {
                "COCINA_SUSHI": "cocina_sushi",
                "COCINA_SANDWICH": "cocina_sandwich",
                "CAJA": "caja",
                "NONE": "ninguna",
            },
        ),
        (
            "modifier_groups",
            "modifier_type",
            {
                "SINGLE": "single",
                "MULTIPLE": "multiple",
            },
        ),
        (
            "orders",
            "delivery_type",
            {
                "DELIVERY": "delivery",
                "PICKUP": "retiro",
            },
        ),
        (
            "orders",
            "status",
            {
                "PENDING": "pendiente",
                "PAID": "pagado",
                "PREPARING": "en_preparacion",
                "READY": "listo",
                "DISPATCHED": "despachado",
                "DELIVERED": "entregado",
                "CANCELLED": "cancelado",
                "VOIDED": "anulado",
            },
        ),
        (
            "orders",
            "payment_status",
            {
                "PENDING": "pendiente",
                "PAID": "pagado",
                "REJECTED": "rechazado",
                "REFUNDED": "reembolso",
            },
        ),
    ]
    for table, column, mapping in updates:
        for source, target in mapping.items():
            await session.execute(
                text(f"update {table} set {column} = :target where {column} = :source"),
                {"source": source, "target": target},
            )
    await session.flush()


async def seed_dev_data(session: AsyncSession) -> SeedSummary:
    _assert_local_safe()
    await _normalize_enum_storage(session)
    categories_by_slug = await _ensure_categories(session)
    products_by_slug = await _ensure_products(session, categories_by_slug)
    groups = await _ensure_modifier_groups(session, products_by_slug)
    await _ensure_modifier_options(session, groups)
    user = await _ensure_demo_user(session)
    await _ensure_demo_address(session, user)
    await _ensure_demo_coupon(session)

    active_categories = await session.scalar(
        select(func.count()).select_from(CategoryORM).where(CategoryORM.is_active == True)
    )
    total_products = await session.scalar(select(func.count()).select_from(ProductORM))
    active_products = await session.scalar(
        select(func.count()).select_from(ProductORM).where(ProductORM.is_available == True)
    )

    return SeedSummary(
        active_categories=int(active_categories or 0),
        total_products=int(total_products or 0),
        active_products=int(active_products or 0),
        demo_user_email=DEMO_USER_EMAIL,
        demo_coupon_code=DEMO_COUPON_CODE,
    )
