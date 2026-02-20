"""Add social accounts and posted content tracking

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add social media fields to shops table
    op.add_column("shops", sa.Column("instagram_handle", sa.String(255), server_default=""))
    op.add_column("shops", sa.Column("facebook_url", sa.String(500), server_default=""))
    op.add_column("shops", sa.Column("tiktok_handle", sa.String(255), server_default=""))
    op.add_column("shops", sa.Column("email_list_size", sa.Integer, server_default="0"))

    # Create posted_contents table
    op.create_table(
        "posted_contents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("content_text", sa.Text, nullable=False),
        sa.Column("platform", sa.String(50)),
        sa.Column("hashtags", sa.Text, server_default=""),
        sa.Column("posted_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("posted_contents")
    op.drop_column("shops", "email_list_size")
    op.drop_column("shops", "tiktok_handle")
    op.drop_column("shops", "facebook_url")
    op.drop_column("shops", "instagram_handle")
