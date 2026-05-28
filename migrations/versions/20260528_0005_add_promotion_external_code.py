"""Add external code to promotions.

Revision ID: 20260528_0005
Revises: 20260425_0004
Create Date: 2026-05-28 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260528_0005"
down_revision: Union[str, None] = "20260425_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("promotions", sa.Column("external_code", sa.String(length=100), nullable=True))
    op.create_index(op.f("ix_promotions_external_code"), "promotions", ["external_code"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_promotions_external_code"), table_name="promotions")
    op.drop_column("promotions", "external_code")
