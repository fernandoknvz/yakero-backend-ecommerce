"""Initial ecommerce schema.

Revision ID: 20260423_0001
Revises:
Create Date: 2026-04-23 14:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260423_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


user_role_enum = sa.Enum("customer", "admin", "pos_service", name="userrole")
ticket_tag_enum = sa.Enum(
    "cocina_sushi",
    "cocina_sandwich",
    "caja",
    "ninguna",
    name="tickettag",
)
modifier_type_enum = sa.Enum("single", "multiple", name="modifiertype")
delivery_type_enum = sa.Enum("delivery", "retiro", name="deliverytype")
order_status_enum = sa.Enum(
    "pendiente",
    "pagado",
    "en_preparacion",
    "listo",
    "despachado",
    "entregado",
    "cancelado",
    "anulado",
    name="orderstatus",
)
payment_status_enum = sa.Enum(
    "pendiente",
    "pagado",
    "rechazado",
    "reembolso",
    name="paymentstatus",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("is_guest", sa.Boolean(), nullable=True),
        sa.Column("points_balance", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("ticket_tag", ticket_tag_enum, nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("slug", name=op.f("uq_categories_slug")),
    )
    op.create_index(op.f("ix_categories_id"), "categories", ["id"], unique=False)

    op.create_table(
        "promotions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("promotion_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Numeric(precision=10, scale=0), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promotions")),
    )
    op.create_index(op.f("ix_promotions_id"), "promotions", ["id"], unique=False)

    op.create_table(
        "addresses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("street", sa.String(length=200), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("commune", sa.String(length=100), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_addresses_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_addresses")),
    )
    op.create_index(op.f("ix_addresses_id"), "addresses", ["id"], unique=False)

    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("discount_type", sa.String(length=20), nullable=False),
        sa.Column("discount_value", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("min_order_amount", sa.Numeric(precision=10, scale=0), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("uses_count", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_coupons_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coupons")),
        sa.UniqueConstraint("code", name=op.f("uq_coupons_code")),
    )
    op.create_index(op.f("ix_coupons_code"), "coupons", ["code"], unique=False)
    op.create_index(op.f("ix_coupons_id"), "coupons", ["id"], unique=False)

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("guest_email", sa.String(length=255), nullable=True),
        sa.Column("guest_phone", sa.String(length=30), nullable=True),
        sa.Column("address_id", sa.Integer(), nullable=True),
        sa.Column("delivery_type", delivery_type_enum, nullable=False),
        sa.Column("status", order_status_enum, nullable=False),
        sa.Column("payment_status", payment_status_enum, nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=10, scale=0), nullable=False),
        sa.Column("delivery_fee", sa.Numeric(precision=10, scale=0), nullable=True),
        sa.Column("discount", sa.Numeric(precision=10, scale=0), nullable=True),
        sa.Column("points_used", sa.Integer(), nullable=True),
        sa.Column("total", sa.Numeric(precision=10, scale=0), nullable=False),
        sa.Column("mp_preference_id", sa.String(length=255), nullable=True),
        sa.Column("mp_payment_id", sa.String(length=255), nullable=True),
        sa.Column("mp_payment_status", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("delivery_address_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("ready_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["address_id"], ["addresses.id"], name=op.f("fk_orders_address_id_addresses")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_orders_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
    )
    op.create_index(op.f("ix_orders_id"), "orders", ["id"], unique=False)
    op.create_index(op.f("ix_orders_mp_payment_id"), "orders", ["mp_payment_id"], unique=False)
    op.create_index(op.f("ix_orders_mp_preference_id"), "orders", ["mp_preference_id"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=0), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("ticket_tag", ticket_tag_enum, nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], name=op.f("fk_products_category_id_categories")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("sku", name=op.f("uq_products_sku")),
        sa.UniqueConstraint("slug", name=op.f("uq_products_slug")),
    )
    op.create_index(op.f("ix_products_id"), "products", ["id"], unique=False)
    op.create_index(op.f("ix_products_sku"), "products", ["sku"], unique=False)

    op.create_table(
        "promotion_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("promotion_id", sa.Integer(), nullable=False),
        sa.Column("slot_name", sa.String(length=200), nullable=False),
        sa.Column("pieces", sa.Integer(), nullable=False),
        sa.Column("ticket_tag", ticket_tag_enum, nullable=False),
        sa.ForeignKeyConstraint(["promotion_id"], ["promotions.id"], name=op.f("fk_promotion_slots_promotion_id_promotions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promotion_slots")),
    )
    op.create_index(op.f("ix_promotion_slots_id"), "promotion_slots", ["id"], unique=False)

    op.create_table(
        "modifier_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("promotion_slot_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("modifier_type", modifier_type_enum, nullable=False),
        sa.Column("min_selections", sa.Integer(), nullable=True),
        sa.Column("max_selections", sa.Integer(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=True),
        sa.CheckConstraint("product_id IS NOT NULL OR promotion_slot_id IS NOT NULL", name=op.f("ck_modifier_groups_parent_present")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_modifier_groups_product_id_products"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["promotion_slot_id"], ["promotion_slots.id"], name=op.f("fk_modifier_groups_promotion_slot_id_promotion_slots"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_modifier_groups")),
    )
    op.create_index(op.f("ix_modifier_groups_id"), "modifier_groups", ["id"], unique=False)

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("promotion_id", sa.Integer(), nullable=True),
        sa.Column("promotion_slot_id", sa.Integer(), nullable=True),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=0), nullable=False),
        sa.Column("total_price", sa.Numeric(precision=10, scale=0), nullable=False),
        sa.Column("ticket_tag", ticket_tag_enum, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_order_items_order_id_orders"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_order_items_product_id_products")),
        sa.ForeignKeyConstraint(["promotion_id"], ["promotions.id"], name=op.f("fk_order_items_promotion_id_promotions")),
        sa.ForeignKeyConstraint(["promotion_slot_id"], ["promotion_slots.id"], name=op.f("fk_order_items_promotion_slot_id_promotion_slots")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
    )
    op.create_index(op.f("ix_order_items_id"), "order_items", ["id"], unique=False)

    op.create_table(
        "modifier_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("extra_price", sa.Numeric(precision=10, scale=0), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["modifier_groups.id"], name=op.f("fk_modifier_options_group_id_modifier_groups"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_modifier_options")),
    )
    op.create_index(op.f("ix_modifier_options_id"), "modifier_options", ["id"], unique=False)

    op.create_table(
        "order_item_modifiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_item_id", sa.Integer(), nullable=False),
        sa.Column("modifier_option_id", sa.Integer(), nullable=True),
        sa.Column("option_name", sa.String(length=100), nullable=False),
        sa.Column("group_name", sa.String(length=100), nullable=False),
        sa.Column("extra_price", sa.Numeric(precision=10, scale=0), nullable=True),
        sa.ForeignKeyConstraint(["modifier_option_id"], ["modifier_options.id"], name=op.f("fk_order_item_modifiers_modifier_option_id_modifier_options")),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], name=op.f("fk_order_item_modifiers_order_item_id_order_items"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_item_modifiers")),
    )
    op.create_index(op.f("ix_order_item_modifiers_id"), "order_item_modifiers", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_order_item_modifiers_id"), table_name="order_item_modifiers")
    op.drop_table("order_item_modifiers")
    op.drop_index(op.f("ix_modifier_options_id"), table_name="modifier_options")
    op.drop_table("modifier_options")
    op.drop_index(op.f("ix_order_items_id"), table_name="order_items")
    op.drop_table("order_items")
    op.drop_index(op.f("ix_modifier_groups_id"), table_name="modifier_groups")
    op.drop_table("modifier_groups")
    op.drop_index(op.f("ix_promotion_slots_id"), table_name="promotion_slots")
    op.drop_table("promotion_slots")
    op.drop_index(op.f("ix_products_sku"), table_name="products")
    op.drop_index(op.f("ix_products_id"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_orders_mp_preference_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_mp_payment_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_id"), table_name="orders")
    op.drop_table("orders")
    op.drop_index(op.f("ix_coupons_id"), table_name="coupons")
    op.drop_index(op.f("ix_coupons_code"), table_name="coupons")
    op.drop_table("coupons")
    op.drop_index(op.f("ix_addresses_id"), table_name="addresses")
    op.drop_table("addresses")
    op.drop_index(op.f("ix_promotions_id"), table_name="promotions")
    op.drop_table("promotions")
    op.drop_index(op.f("ix_categories_id"), table_name="categories")
    op.drop_table("categories")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    payment_status_enum.drop(bind, checkfirst=True)
    order_status_enum.drop(bind, checkfirst=True)
    delivery_type_enum.drop(bind, checkfirst=True)
    modifier_type_enum.drop(bind, checkfirst=True)
    ticket_tag_enum.drop(bind, checkfirst=True)
    user_role_enum.drop(bind, checkfirst=True)
