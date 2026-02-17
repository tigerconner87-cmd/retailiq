"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-02-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("plan_tier", sa.String(20), nullable=False, server_default="starter"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "shops",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("pos_system", sa.String(50)),
        sa.Column("pos_credentials", sa.Text),
        sa.Column("google_place_id", sa.String(255)),
        sa.Column("address", sa.String(500)),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("cost", sa.Numeric(12, 2)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("first_seen", sa.DateTime),
        sa.Column("last_seen", sa.DateTime),
        sa.Column("visit_count", sa.Integer, server_default="1"),
        sa.Column("total_spent", sa.Numeric(12, 2), server_default="0"),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax", sa.Numeric(12, 2), server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("items_count", sa.Integer, server_default="1"),
        sa.Column("timestamp", sa.DateTime, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "transaction_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
    )

    op.create_table(
        "daily_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("total_revenue", sa.Numeric(12, 2), server_default="0"),
        sa.Column("transaction_count", sa.Integer, server_default="0"),
        sa.Column("avg_transaction_value", sa.Numeric(12, 2), server_default="0"),
        sa.Column("unique_customers", sa.Integer, server_default="0"),
        sa.Column("repeat_customers", sa.Integer, server_default="0"),
        sa.Column("new_customers", sa.Integer, server_default="0"),
    )

    op.create_table(
        "hourly_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("hour", sa.Integer, nullable=False),
        sa.Column("revenue", sa.Numeric(12, 2), server_default="0"),
        sa.Column("transaction_count", sa.Integer, server_default="0"),
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("source", sa.String(50), server_default="google"),
        sa.Column("author_name", sa.String(255)),
        sa.Column("rating", sa.Integer),
        sa.Column("text", sa.Text),
        sa.Column("review_date", sa.DateTime),
        sa.Column("sentiment", sa.String(20)),
        sa.Column("is_own_shop", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "competitors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("google_place_id", sa.String(255)),
        sa.Column("address", sa.String(500)),
        sa.Column("rating", sa.Numeric(2, 1)),
        sa.Column("review_count", sa.Integer, server_default="0"),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "competitor_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("competitor_id", sa.String(36), sa.ForeignKey("competitors.id"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("rating", sa.Numeric(2, 1)),
        sa.Column("review_count", sa.Integer),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), server_default="warning"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text),
        sa.Column("is_read", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("competitor_snapshots")
    op.drop_table("competitors")
    op.drop_table("reviews")
    op.drop_table("hourly_snapshots")
    op.drop_table("daily_snapshots")
    op.drop_table("transaction_items")
    op.drop_table("transactions")
    op.drop_table("customers")
    op.drop_table("products")
    op.drop_table("shops")
    op.drop_table("users")
