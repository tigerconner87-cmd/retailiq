"""Add AI Agent Fleet tables.

Revision ID: 0003
Revises: 0002
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("agent_type", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="1"),
        sa.Column("configuration", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "agent_activities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id"), nullable=False, index=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("agent_activities")
    op.drop_table("agents")
