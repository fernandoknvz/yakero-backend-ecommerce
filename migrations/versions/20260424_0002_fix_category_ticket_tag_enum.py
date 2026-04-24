"""Normalize categories.ticket_tag enum values.

Revision ID: 20260424_0002
Revises: 20260423_0001
Create Date: 2026-04-24 10:20:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260424_0002"
down_revision: Union[str, None] = "20260423_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE categories
        MODIFY COLUMN ticket_tag VARCHAR(32) NOT NULL
        """
    )
    op.execute("UPDATE categories SET ticket_tag = 'cocina_sushi' WHERE ticket_tag = 'COCINA_SUSHI'")
    op.execute("UPDATE categories SET ticket_tag = 'cocina_sandwich' WHERE ticket_tag = 'COCINA_SANDWICH'")
    op.execute("UPDATE categories SET ticket_tag = 'caja' WHERE ticket_tag = 'CAJA'")
    op.execute("UPDATE categories SET ticket_tag = 'ninguna' WHERE ticket_tag = 'NONE'")
    op.execute(
        """
        ALTER TABLE categories
        MODIFY COLUMN ticket_tag ENUM(
            'cocina_sushi',
            'cocina_sandwich',
            'caja',
            'ninguna'
        ) NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE categories
        MODIFY COLUMN ticket_tag VARCHAR(32) NOT NULL
        """
    )
    op.execute("UPDATE categories SET ticket_tag = 'COCINA_SUSHI' WHERE ticket_tag = 'cocina_sushi'")
    op.execute("UPDATE categories SET ticket_tag = 'COCINA_SANDWICH' WHERE ticket_tag = 'cocina_sandwich'")
    op.execute("UPDATE categories SET ticket_tag = 'CAJA' WHERE ticket_tag = 'caja'")
    op.execute("UPDATE categories SET ticket_tag = 'NONE' WHERE ticket_tag = 'ninguna'")
    op.execute(
        """
        ALTER TABLE categories
        MODIFY COLUMN ticket_tag ENUM(
            'COCINA_SUSHI',
            'COCINA_SANDWICH',
            'CAJA',
            'NONE'
        ) NOT NULL
        """
    )
