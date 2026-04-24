"""Add payment_provider to orders.

Revision ID: 20260424_0003
Revises: 20260424_0002
Create Date: 2026-04-24 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260424_0003"
down_revision: Union[str, None] = "20260424_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_provider", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "payment_provider")
