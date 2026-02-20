"""Add agent_tasks table for task board.

Revision ID: 0004
Revises: 0003
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("agent_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("priority", sa.String(20), server_default="medium"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("result", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("agent_tasks")
