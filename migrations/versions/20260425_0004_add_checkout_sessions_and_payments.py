"""Add checkout sessions and payments.

Revision ID: 20260425_0004
Revises: 20260424_0003
Create Date: 2026-04-25 21:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260425_0004"
down_revision: Union[str, None] = "20260424_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _add_order_column_if_missing(
    inspector: sa.Inspector,
    column_name: str,
    column: sa.Column,
) -> None:
    if not _column_exists(inspector, "orders", column_name):
        op.add_column("orders", column)


def _create_index_if_missing(
    inspector: sa.Inspector,
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if _table_exists(inspector, table_name) and not _index_exists(inspector, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _add_order_column_if_missing(
        inspector,
        "payment_provider",
        sa.Column("payment_provider", sa.String(length=50), nullable=True),
    )
    _add_order_column_if_missing(
        inspector,
        "mp_preference_id",
        sa.Column("mp_preference_id", sa.String(length=255), nullable=True),
    )
    _add_order_column_if_missing(
        inspector,
        "mp_payment_id",
        sa.Column("mp_payment_id", sa.String(length=255), nullable=True),
    )
    _add_order_column_if_missing(
        inspector,
        "mp_payment_status",
        sa.Column("mp_payment_status", sa.String(length=50), nullable=True),
    )
    _add_order_column_if_missing(
        inspector,
        "paid_at",
        sa.Column("paid_at", sa.DateTime(), nullable=True),
    )
    if _table_exists(inspector, "checkout_sessions") and not _column_exists(inspector, "checkout_sessions", "customer_data"):
        op.add_column("checkout_sessions", sa.Column("customer_data", sa.JSON(), nullable=True))

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "ix_orders_mp_preference_id", "orders", ["mp_preference_id"])
    _create_index_if_missing(inspector, "ix_orders_mp_payment_id", "orders", ["mp_payment_id"])

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "checkout_sessions"):
        op.create_table(
            "checkout_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_token", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("guest_email", sa.String(length=255), nullable=True),
            sa.Column("guest_phone", sa.String(length=30), nullable=True),
            sa.Column("address_id", sa.Integer(), nullable=True),
            sa.Column("delivery_type", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("payment_provider", sa.String(length=50), nullable=False, server_default="mercadopago"),
            sa.Column("mp_preference_id", sa.String(length=255), nullable=True),
            sa.Column("mp_init_point", sa.Text(), nullable=True),
            sa.Column("mp_sandbox_init_point", sa.Text(), nullable=True),
            sa.Column("cart_snapshot", sa.JSON(), nullable=False),
            sa.Column("customer_data", sa.JSON(), nullable=True),
            sa.Column("pricing_snapshot", sa.JSON(), nullable=True),
            sa.Column("delivery_address_snapshot", sa.JSON(), nullable=True),
            sa.Column("coupon_code", sa.String(length=50), nullable=True),
            sa.Column("subtotal", sa.Numeric(precision=10, scale=0), nullable=False),
            sa.Column("delivery_fee", sa.Numeric(precision=10, scale=0), nullable=False, server_default="0"),
            sa.Column("discount", sa.Numeric(precision=10, scale=0), nullable=False, server_default="0"),
            sa.Column("points_used", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total", sa.Numeric(precision=10, scale=0), nullable=False),
            sa.Column("created_order_id", sa.Integer(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_checkout_sessions")),
            sa.UniqueConstraint("session_token", name=op.f("uq_checkout_sessions_session_token")),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "ix_checkout_sessions_user_id", "checkout_sessions", ["user_id"])
    _create_index_if_missing(inspector, "ix_checkout_sessions_status", "checkout_sessions", ["status"])
    _create_index_if_missing(inspector, "ix_checkout_sessions_mp_preference_id", "checkout_sessions", ["mp_preference_id"])
    _create_index_if_missing(inspector, "ix_checkout_sessions_created_order_id", "checkout_sessions", ["created_order_id"])

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "payments"):
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("checkout_session_id", sa.Integer(), nullable=True),
            sa.Column("order_id", sa.Integer(), nullable=True),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
            sa.Column("provider_preference_id", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("provider_status", sa.String(length=50), nullable=True),
            sa.Column("amount", sa.Numeric(precision=10, scale=0), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="CLP"),
            sa.Column("raw_payload", sa.JSON(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
            sa.UniqueConstraint("provider", "provider_payment_id", name=op.f("uq_payments_provider_provider_payment_id")),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "ix_payments_checkout_session_id", "payments", ["checkout_session_id"])
    _create_index_if_missing(inspector, "ix_payments_order_id", "payments", ["order_id"])
    _create_index_if_missing(inspector, "ix_payments_provider_preference_id", "payments", ["provider_preference_id"])
    _create_index_if_missing(inspector, "ix_payments_status", "payments", ["status"])


def downgrade() -> None:
    # Intentionally no-op: production tables/columns created by this migration
    # may contain payment audit data and must not be dropped automatically.
    pass
