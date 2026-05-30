"""Add subcategory to products.

Revision ID: 20260530_0006
Revises: 20260528_0005
Create Date: 2026-05-30 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260530_0006"
down_revision: Union[str, None] = "20260528_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("subcategory", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "subcategory")
