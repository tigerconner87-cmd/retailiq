"""Add enterprise features: new tables and columns for v2.0

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-18

New tables: shop_settings, expenses, revenue_goals, recommendations,
            marketing_campaigns, competitor_reviews

New columns on: users, shops, products, customers, transactions,
                daily_snapshots, reviews, competitors, alerts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_safe(table: str, column: sa.Column):
    """Add a column only if it doesn't already exist (idempotent)."""
    try:
        op.add_column(table, column)
    except Exception:
        pass


def upgrade() -> None:
    # ── New columns on users ─────────────────────────────────────────────
    op.add_column("users", sa.Column("onboarding_completed", sa.Boolean, server_default=sa.text("false")))
    op.add_column("users", sa.Column("onboarding_step", sa.Integer, server_default="0"))

    # ── New columns on shops ─────────────────────────────────────────────
    op.add_column("shops", sa.Column("category", sa.String(100), server_default="retail"))
    op.add_column("shops", sa.Column("store_size_sqft", sa.Integer, nullable=True))
    op.add_column("shops", sa.Column("staff_count", sa.Integer, server_default="1"))

    # ── New columns on products ──────────────────────────────────────────
    op.add_column("products", sa.Column("sku", sa.String(100), nullable=True))
    op.add_column("products", sa.Column("stock_quantity", sa.Integer, nullable=True))

    # ── New columns on customers ─────────────────────────────────────────
    op.add_column("customers", sa.Column("email", sa.String(255), nullable=True))
    op.add_column("customers", sa.Column("segment", sa.String(20), server_default="regular"))
    op.add_column("customers", sa.Column("avg_order_value", sa.Numeric(12, 2), server_default="0"))
    op.add_column("customers", sa.Column("avg_days_between_visits", sa.Float, nullable=True))

    # ── New columns on transactions ──────────────────────────────────────
    op.add_column("transactions", sa.Column("discount", sa.Numeric(12, 2), server_default="0"))
    op.add_column("transactions", sa.Column("payment_method", sa.String(50), server_default="card"))

    # ── New columns on daily_snapshots ───────────────────────────────────
    op.add_column("daily_snapshots", sa.Column("total_cost", sa.Numeric(12, 2), server_default="0"))
    op.add_column("daily_snapshots", sa.Column("items_sold", sa.Integer, server_default="0"))

    # ── New columns on reviews ───────────────────────────────────────────
    op.add_column("reviews", sa.Column("response_text", sa.Text, nullable=True))
    op.add_column("reviews", sa.Column("responded_at", sa.DateTime, nullable=True))

    # ── New columns on competitors ───────────────────────────────────────
    op.add_column("competitors", sa.Column("category", sa.String(100), nullable=True))

    # ── New columns on alerts ────────────────────────────────────────────
    op.add_column("alerts", sa.Column("category", sa.String(50), server_default="general"))
    op.add_column("alerts", sa.Column("is_snoozed", sa.Boolean, server_default=sa.text("false")))
    op.add_column("alerts", sa.Column("snoozed_until", sa.DateTime, nullable=True))

    # ── New table: shop_settings ─────────────────────────────────────────
    op.create_table(
        "shop_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False, unique=True),
        sa.Column("business_hours", sa.JSON, nullable=True),
        sa.Column("monthly_rent", sa.Numeric(12, 2), server_default="0"),
        sa.Column("avg_cogs_percentage", sa.Float, server_default="40.0"),
        sa.Column("staff_hourly_rate", sa.Numeric(12, 2), server_default="15"),
        sa.Column("tax_rate", sa.Float, server_default="8.25"),
        sa.Column("email_frequency", sa.String(20), server_default="weekly"),
        sa.Column("alert_revenue", sa.Boolean, server_default=sa.text("true")),
        sa.Column("alert_customers", sa.Boolean, server_default=sa.text("true")),
        sa.Column("alert_reviews", sa.Boolean, server_default=sa.text("true")),
        sa.Column("alert_competitors", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ── New table: expenses ──────────────────────────────────────────────
    op.create_table(
        "expenses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_monthly", sa.Boolean, server_default=sa.text("true")),
        sa.Column("month", sa.String(7), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ── New table: revenue_goals ─────────────────────────────────────────
    op.create_table(
        "revenue_goals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("target_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ── New table: recommendations ───────────────────────────────────────
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(20), server_default="medium"),
        sa.Column("estimated_impact", sa.String(255), nullable=True),
        sa.Column("action_steps", sa.JSON, nullable=True),
        sa.Column("emoji", sa.String(10), server_default="1f4a1"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
    )

    # ── New table: marketing_campaigns ───────────────────────────────────
    op.create_table(
        "marketing_campaigns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_id", sa.String(36), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(50), nullable=True),
        sa.Column("spend", sa.Numeric(12, 2), server_default="0"),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("revenue_attributed", sa.Numeric(12, 2), server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ── New table: competitor_reviews ────────────────────────────────────
    op.create_table(
        "competitor_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("competitor_id", sa.String(36), sa.ForeignKey("competitors.id"), nullable=False),
        sa.Column("author_name", sa.String(255), nullable=True),
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("review_date", sa.DateTime, nullable=True),
        sa.Column("sentiment", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    # Drop new tables
    op.drop_table("competitor_reviews")
    op.drop_table("marketing_campaigns")
    op.drop_table("recommendations")
    op.drop_table("revenue_goals")
    op.drop_table("expenses")
    op.drop_table("shop_settings")

    # Drop new columns on existing tables
    op.drop_column("alerts", "snoozed_until")
    op.drop_column("alerts", "is_snoozed")
    op.drop_column("alerts", "category")
    op.drop_column("competitors", "category")
    op.drop_column("reviews", "responded_at")
    op.drop_column("reviews", "response_text")
    op.drop_column("daily_snapshots", "items_sold")
    op.drop_column("daily_snapshots", "total_cost")
    op.drop_column("transactions", "payment_method")
    op.drop_column("transactions", "discount")
    op.drop_column("customers", "avg_days_between_visits")
    op.drop_column("customers", "avg_order_value")
    op.drop_column("customers", "segment")
    op.drop_column("customers", "email")
    op.drop_column("products", "stock_quantity")
    op.drop_column("products", "sku")
    op.drop_column("shops", "staff_count")
    op.drop_column("shops", "store_size_sqft")
    op.drop_column("shops", "category")
    op.drop_column("users", "onboarding_step")
    op.drop_column("users", "onboarding_completed")
