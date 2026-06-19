"""Add POS sync fields to orders.

Revision ID: 20260619_0007
Revises: 20260530_0006
Create Date: 2026-06-19 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260619_0007"
down_revision: Union[str, None] = "20260530_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _add_column_if_missing(inspector: sa.Inspector, column_name: str, column: sa.Column) -> None:
    if not _column_exists(inspector, "orders", column_name):
        op.add_column("orders", column)


def _create_index_if_missing(inspector: sa.Inspector, index_name: str, columns: list[str]) -> None:
    if not _index_exists(inspector, "orders", index_name):
        op.create_index(index_name, "orders", columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _add_column_if_missing(inspector, "pos_sale_id", sa.Column("pos_sale_id", sa.String(length=100), nullable=True))
    _add_column_if_missing(inspector, "pos_sync_status", sa.Column("pos_sync_status", sa.String(length=30), nullable=True))
    _add_column_if_missing(inspector, "pos_sync_error", sa.Column("pos_sync_error", sa.Text(), nullable=True))
    _add_column_if_missing(inspector, "pos_sync_response", sa.Column("pos_sync_response", sa.JSON(), nullable=True))
    _add_column_if_missing(inspector, "pos_synced_at", sa.Column("pos_synced_at", sa.DateTime(), nullable=True))

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, op.f("ix_orders_pos_sale_id"), ["pos_sale_id"])
    _create_index_if_missing(inspector, op.f("ix_orders_pos_sync_status"), ["pos_sync_status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _index_exists(inspector, "orders", op.f("ix_orders_pos_sync_status")):
        op.drop_index(op.f("ix_orders_pos_sync_status"), table_name="orders")
    if _index_exists(inspector, "orders", op.f("ix_orders_pos_sale_id")):
        op.drop_index(op.f("ix_orders_pos_sale_id"), table_name="orders")
    for column_name in ("pos_synced_at", "pos_sync_response", "pos_sync_error", "pos_sync_status", "pos_sale_id"):
        inspector = sa.inspect(bind)
        if _column_exists(inspector, "orders", column_name):
            op.drop_column("orders", column_name)
