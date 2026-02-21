import uuid
from datetime import datetime, date

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, Numeric, String, Text, JSON,
)
from sqlalchemy.orm import relationship

from app.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


# ── User ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=new_id)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    plan_tier = Column(String(20), nullable=False, default="starter")
    is_active = Column(Boolean, default=True)
    onboarding_completed = Column(Boolean, default=False)
    onboarding_step = Column(Integer, default=0)
    trial_start_date = Column(DateTime)
    trial_end_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    shops = relationship("Shop", back_populates="owner", cascade="all, delete-orphan")


# ── Shop ──────────────────────────────────────────────────────────────────────

class Shop(Base):
    __tablename__ = "shops"

    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    pos_system = Column(String(50))
    pos_credentials = Column(Text)
    google_place_id = Column(String(255))
    address = Column(String(500))
    city = Column(String(255))
    category = Column(String(100), default="retail")
    store_size_sqft = Column(Integer)
    staff_count = Column(Integer, default=1)
    latitude = Column(Float)
    longitude = Column(Float)
    instagram_handle = Column(String(255), default="")
    facebook_url = Column(String(500), default="")
    tiktok_handle = Column(String(255), default="")
    email_list_size = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="shops")
    transactions = relationship("Transaction", back_populates="shop", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="shop", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="shop", cascade="all, delete-orphan")
    daily_snapshots = relationship("DailySnapshot", back_populates="shop", cascade="all, delete-orphan")
    hourly_snapshots = relationship("HourlySnapshot", back_populates="shop", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="shop", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="shop", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="shop", cascade="all, delete-orphan")
    settings = relationship("ShopSettings", back_populates="shop", uselist=False, cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="shop", cascade="all, delete-orphan")
    revenue_goals = relationship("RevenueGoal", back_populates="shop", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="shop", cascade="all, delete-orphan")
    marketing_campaigns = relationship("MarketingCampaign", back_populates="shop", cascade="all, delete-orphan")
    marketing_responses = relationship("MarketingResponse", back_populates="shop", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="shop", cascade="all, delete-orphan")
    product_goals = relationship("ProductGoal", back_populates="shop", cascade="all, delete-orphan")
    strategy_notes = relationship("StrategyNote", back_populates="shop", cascade="all, delete-orphan")
    posted_contents = relationship("PostedContent", back_populates="shop", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="shop", cascade="all, delete-orphan")


# ── Shop Settings ─────────────────────────────────────────────────────────────

class ShopSettings(Base):
    __tablename__ = "shop_settings"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, unique=True)
    business_hours = Column(JSON, default=lambda: {
        "mon": {"open": "09:00", "close": "18:00"},
        "tue": {"open": "09:00", "close": "18:00"},
        "wed": {"open": "09:00", "close": "18:00"},
        "thu": {"open": "09:00", "close": "18:00"},
        "fri": {"open": "09:00", "close": "20:00"},
        "sat": {"open": "10:00", "close": "20:00"},
        "sun": {"open": "11:00", "close": "17:00"},
    })
    monthly_rent = Column(Numeric(12, 2), default=0)
    avg_cogs_percentage = Column(Float, default=40.0)
    staff_hourly_rate = Column(Numeric(12, 2), default=15)
    tax_rate = Column(Float, default=8.25)
    email_frequency = Column(String(20), default="weekly")
    alert_revenue = Column(Boolean, default=True)
    alert_customers = Column(Boolean, default=True)
    alert_reviews = Column(Boolean, default=True)
    alert_competitors = Column(Boolean, default=True)
    google_api_key = Column(String(255), default="")
    anthropic_api_key = Column(String(255), default="")
    ai_enabled = Column(Boolean, default=True)
    ai_personality = Column(String(50), default="professional")
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="settings")


# ── Expense ───────────────────────────────────────────────────────────────────

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    category = Column(String(50), nullable=False)  # rent, labor, inventory, marketing, utilities, other
    name = Column(String(255), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    is_monthly = Column(Boolean, default=True)
    month = Column(String(7))  # YYYY-MM or null for recurring
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="expenses")


# ── Revenue Goal ──────────────────────────────────────────────────────────────

class RevenueGoal(Base):
    __tablename__ = "revenue_goals"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    month = Column(String(7), nullable=False)  # YYYY-MM
    target_amount = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="revenue_goals")


# ── Recommendation ────────────────────────────────────────────────────────────

class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)  # revenue, customers, products, marketing, operations, competitors
    priority = Column(String(20), default="medium")  # critical, high, medium, low
    estimated_impact = Column(String(255))
    action_steps = Column(JSON)
    emoji = Column(String(10), default="1f4a1")
    status = Column(String(20), default="active")  # active, done, dismissed
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)

    shop = relationship("Shop", back_populates="recommendations")


# ── Marketing Campaign ────────────────────────────────────────────────────────

class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    name = Column(String(255), nullable=False)
    channel = Column(String(50))  # social, email, print, in-store, other
    spend = Column(Numeric(12, 2), default=0)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    revenue_attributed = Column(Numeric(12, 2), default=0)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="marketing_campaigns")


# ── Product ───────────────────────────────────────────────────────────────────

class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    external_id = Column(String(255))
    name = Column(String(255), nullable=False)
    category = Column(String(100))
    price = Column(Numeric(12, 2), nullable=False)
    cost = Column(Numeric(12, 2))
    sku = Column(String(100))
    stock_quantity = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="products")
    transaction_items = relationship("TransactionItem", back_populates="product")


# ── Customer ──────────────────────────────────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    external_id = Column(String(255))
    email = Column(String(255))
    segment = Column(String(20), default="regular")  # vip, regular, at_risk, lost
    first_seen = Column(DateTime)
    last_seen = Column(DateTime)
    visit_count = Column(Integer, default=1)
    total_spent = Column(Numeric(12, 2), default=0)
    avg_order_value = Column(Numeric(12, 2), default=0)
    avg_days_between_visits = Column(Float)

    shop = relationship("Shop", back_populates="customers")
    transactions = relationship("Transaction", back_populates="customer")


# ── Transaction ───────────────────────────────────────────────────────────────

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    external_id = Column(String(255))
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)
    subtotal = Column(Numeric(12, 2), nullable=False)
    tax = Column(Numeric(12, 2), default=0)
    discount = Column(Numeric(12, 2), default=0)
    total = Column(Numeric(12, 2), nullable=False)
    items_count = Column(Integer, default=1)
    payment_method = Column(String(50), default="card")
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="transactions")
    customer = relationship("Customer", back_populates="transactions")
    items = relationship("TransactionItem", back_populates="transaction", cascade="all, delete-orphan")


class TransactionItem(Base):
    __tablename__ = "transaction_items"

    id = Column(String(36), primary_key=True, default=new_id)
    transaction_id = Column(String(36), ForeignKey("transactions.id"), nullable=False)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False)
    total = Column(Numeric(12, 2), nullable=False)

    transaction = relationship("Transaction", back_populates="items")
    product = relationship("Product", back_populates="transaction_items")


# ── Snapshots ─────────────────────────────────────────────────────────────────

class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    total_revenue = Column(Numeric(12, 2), default=0)
    total_cost = Column(Numeric(12, 2), default=0)
    transaction_count = Column(Integer, default=0)
    avg_transaction_value = Column(Numeric(12, 2), default=0)
    items_sold = Column(Integer, default=0)
    unique_customers = Column(Integer, default=0)
    repeat_customers = Column(Integer, default=0)
    new_customers = Column(Integer, default=0)

    shop = relationship("Shop", back_populates="daily_snapshots")


class HourlySnapshot(Base):
    __tablename__ = "hourly_snapshots"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    date = Column(Date, nullable=False)
    hour = Column(Integer, nullable=False)
    revenue = Column(Numeric(12, 2), default=0)
    transaction_count = Column(Integer, default=0)

    shop = relationship("Shop", back_populates="hourly_snapshots")


# ── Review ────────────────────────────────────────────────────────────────────

class Review(Base):
    __tablename__ = "reviews"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    source = Column(String(50), default="google")
    author_name = Column(String(255))
    rating = Column(Integer)
    text = Column(Text)
    review_date = Column(DateTime)
    sentiment = Column(String(20))
    is_own_shop = Column(Boolean, default=True)
    response_text = Column(Text)
    responded_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="reviews")


# ── Competitor ────────────────────────────────────────────────────────────────

class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    name = Column(String(255), nullable=False)
    google_place_id = Column(String(255))
    address = Column(String(500))
    category = Column(String(100))
    rating = Column(Numeric(2, 1))
    review_count = Column(Integer, default=0)
    latitude = Column(Float)
    longitude = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="competitors")
    snapshots = relationship("CompetitorSnapshot", back_populates="competitor", cascade="all, delete-orphan")
    reviews = relationship("CompetitorReview", back_populates="competitor", cascade="all, delete-orphan")
    marketing_responses = relationship("MarketingResponse", back_populates="competitor", cascade="all, delete-orphan")


class CompetitorSnapshot(Base):
    __tablename__ = "competitor_snapshots"

    id = Column(String(36), primary_key=True, default=new_id)
    competitor_id = Column(String(36), ForeignKey("competitors.id"), nullable=False)
    date = Column(Date, nullable=False)
    rating = Column(Numeric(2, 1))
    review_count = Column(Integer)

    competitor = relationship("Competitor", back_populates="snapshots")


class CompetitorReview(Base):
    __tablename__ = "competitor_reviews"

    id = Column(String(36), primary_key=True, default=new_id)
    competitor_id = Column(String(36), ForeignKey("competitors.id"), nullable=False)
    author_name = Column(String(255))
    rating = Column(Integer)
    text = Column(Text)
    review_date = Column(DateTime)
    sentiment = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)

    competitor = relationship("Competitor", back_populates="reviews")


# ── Alert ─────────────────────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), default="warning")  # critical, warning, info, success
    category = Column(String(50), default="general")  # revenue, customers, reviews, competitors, inventory, goals
    title = Column(String(255), nullable=False)
    message = Column(Text)
    is_read = Column(Boolean, default=False)
    is_snoozed = Column(Boolean, default=False)
    snoozed_until = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="alerts")


# ── Marketing Response (Competitor Intelligence) ─────────────────────────────

class MarketingResponse(Base):
    __tablename__ = "marketing_responses"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    competitor_id = Column(String(36), ForeignKey("competitors.id"), nullable=True)
    competitor_name = Column(String(255))
    weakness = Column(Text, nullable=False)
    opportunity_type = Column(String(50))  # rating_drop, negative_reviews, low_engagement, service_gap
    instagram_post = Column(Text)
    email_content = Column(Text)
    promotion_idea = Column(Text)
    priority = Column(String(20), default="good")  # hot, good, fyi
    status = Column(String(20), default="new")  # new, saved, used
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="marketing_responses")
    competitor = relationship("Competitor", back_populates="marketing_responses")


# ── Goal Tracking ────────────────────────────────────────────────────────────

class Goal(Base):
    __tablename__ = "goals"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    goal_type = Column(String(50), nullable=False)  # revenue, transactions, customers, aov, custom
    title = Column(String(255), nullable=False)
    target_value = Column(Numeric(12, 2), nullable=False)
    unit = Column(String(20), default="$")  # $, #, %
    period = Column(String(20), nullable=False)  # monthly, quarterly
    period_key = Column(String(10), nullable=False)  # 2024-02 or 2024-Q1
    status = Column(String(20), default="active")  # active, met, missed
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="goals")


class ProductGoal(Base):
    __tablename__ = "product_goals"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    target_units = Column(Integer, nullable=False)
    period = Column(String(7), nullable=False)  # YYYY-MM
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="product_goals")
    product = relationship("Product")


class StrategyNote(Base):
    __tablename__ = "strategy_notes"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    quarter = Column(String(7), nullable=False)  # 2024-Q1
    title = Column(String(255), nullable=False)
    objectives = Column(JSON)
    key_results = Column(JSON)
    notes = Column(Text)
    status = Column(String(20), default="active")  # active, completed
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="strategy_notes")


# ── Plan Interest (Upgrade Page) ────────────────────────────────────────────

class PlanInterest(Base):
    __tablename__ = "plan_interests"

    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    email = Column(String(255), nullable=False)
    plan = Column(String(50), nullable=False)  # starter, growth, scale
    billing_cycle = Column(String(20), default="monthly")  # monthly, annual
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


# ── Win-Back Campaign ───────────────────────────────────────────────────────

class WinBackCampaign(Base):
    __tablename__ = "winback_campaigns"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    name = Column(String(255), nullable=False)
    template_type = Column(String(50), nullable=False)  # gentle_nudge, sweet_deal, last_chance
    customers_targeted = Column(Integer, default=0)
    discount_percentage = Column(Integer, default=0)
    status = Column(String(20), default="draft")  # draft, sent, completed
    sent_at = Column(DateTime)
    open_rate = Column(Float)
    response_rate = Column(Float)
    revenue_recovered = Column(Numeric(12, 2), default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")


# ── AI Chat Message ──────────────────────────────────────────────────────────

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Posted Content Tracker ──────────────────────────────────────────────────

class PostedContent(Base):
    __tablename__ = "posted_contents"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    content_type = Column(String(50), nullable=False)  # calendar, social, marketing, email
    content_text = Column(Text, nullable=False)
    platform = Column(String(50))  # instagram, facebook, tiktok, email
    hashtags = Column(Text, default="")
    posted_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="posted_contents")


# ── AI Agent Fleet ─────────────────────────────────────────────────────────

class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    agent_type = Column(String(20), nullable=False)  # maya, scout, emma, alex, max
    is_active = Column(Boolean, default=True)
    configuration = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="agents")
    activities = relationship("AgentActivity", back_populates="agent", cascade="all, delete-orphan")


class AgentActivity(Base):
    __tablename__ = "agent_activities"

    id = Column(String(36), primary_key=True, default=new_id)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False, index=True)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False)  # content_generated, alert_sent, analysis_complete, etc.
    description = Column(Text, nullable=False)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    agent = relationship("Agent", back_populates="activities")
    shop = relationship("Shop")


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    agent_type = Column(String(20), nullable=False)  # maya, scout, emma, alex, max
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), default="pending")  # pending, in_progress, completed
    priority = Column(String(20), default="medium")  # high, medium, low
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    result = Column(Text)

    shop = relationship("Shop")


# ── Autonomous Agent Operations ──────────────────────────────────────────────

class TaskGroup(Base):
    __tablename__ = "task_groups"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    command = Column(Text, nullable=False)
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    agent_count = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    shop = relationship("Shop")
    tasks = relationship("OrchestratedTask", back_populates="group", cascade="all, delete-orphan")


class OrchestratedTask(Base):
    __tablename__ = "orchestrated_tasks"

    id = Column(String(36), primary_key=True, default=new_id)
    group_id = Column(String(36), ForeignKey("task_groups.id"), nullable=False, index=True)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    agent_type = Column(String(20), nullable=False)
    instructions = Column(Text, nullable=False)
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    result_summary = Column(Text)
    tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    group = relationship("TaskGroup", back_populates="tasks")
    shop = relationship("Shop")


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    agent_type = Column(String(20), nullable=False)
    is_enabled = Column(Boolean, default=True)
    custom_instructions = Column(Text, default="")
    settings = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shop = relationship("Shop")


class AgentOutput(Base):
    __tablename__ = "agent_outputs"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    agent_type = Column(String(20), nullable=False, index=True)
    run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=True)
    output_type = Column(String(50), nullable=False)  # post, email, analysis, strategy, bundle, etc.
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, default=dict)
    rating = Column(Integer)  # 1-5 stars
    is_saved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")
    run = relationship("AgentRun", back_populates="outputs")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    agent_type = Column(String(20), nullable=False, index=True)
    trigger = Column(String(50), default="manual")  # manual, command, scheduled, chat
    instructions = Column(Text, default="")
    status = Column(String(20), default="running")  # running, completed, failed
    output_count = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    shop = relationship("Shop")
    outputs = relationship("AgentOutput", back_populates="run")


# ── Sent Email Log ──────────────────────────────────────────────────────────

class SentEmail(Base):
    __tablename__ = "sent_emails"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    to_email = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    body_preview = Column(Text, default="")
    template = Column(String(50), default="plain")  # plain, marketing, test
    status = Column(String(20), default="sent")  # sent, failed
    error_message = Column(Text)
    sent_by = Column(String(50), default="user")  # user, maya, emma, claw_bot, system
    agent_output_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")


# ── Claw Bot: Execution Goals ─────────────────────────────────────────────

class ExecutionGoal(Base):
    __tablename__ = "execution_goals"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    command = Column(Text, nullable=False)
    intent = Column(String(100))  # marketing, retention, strategy, competitive, sales
    priority = Column(String(20), default="medium")  # critical, high, medium, low
    status = Column(String(20), default="planning")  # planning, executing, verifying, completed, failed
    plan = Column(JSON, default=dict)
    result_summary = Column(Text)
    quality_score = Column(Float)  # 0-100
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    total_cost = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    shop = relationship("Shop")
    tasks = relationship("ExecutionTask", back_populates="goal", cascade="all, delete-orphan")
    deliverables = relationship("AgentDeliverable", back_populates="goal", cascade="all, delete-orphan")


# ── Claw Bot: Execution Tasks ─────────────────────────────────────────────

class ExecutionTask(Base):
    __tablename__ = "execution_tasks"

    id = Column(String(36), primary_key=True, default=new_id)
    goal_id = Column(String(36), ForeignKey("execution_goals.id"), nullable=False, index=True)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    agent_type = Column(String(20), nullable=False)
    instructions = Column(Text, nullable=False)
    depends_on = Column(JSON, default=list)  # task IDs this depends on
    status = Column(String(20), default="pending")  # pending, running, completed, failed, retrying
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=2)
    result_summary = Column(Text)
    quality_score = Column(Float)
    tokens_used = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    goal = relationship("ExecutionGoal", back_populates="tasks")
    shop = relationship("Shop")
    deliverables = relationship("AgentDeliverable", back_populates="task", cascade="all, delete-orphan")


# ── Claw Bot: Agent Deliverables ──────────────────────────────────────────

class AgentDeliverable(Base):
    __tablename__ = "agent_deliverables"

    id = Column(String(36), primary_key=True, default=new_id)
    goal_id = Column(String(36), ForeignKey("execution_goals.id"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("execution_tasks.id"), nullable=True, index=True)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    agent_type = Column(String(20), nullable=False)
    deliverable_type = Column(String(50), nullable=False)  # email_draft, social_post, analysis, strategy, bundle, etc.
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    quality_scores = Column(JSON, default=dict)  # 8 quality dimensions
    overall_quality = Column(Float)  # 0-100
    status = Column(String(20), default="draft")  # draft, approved, shipped, rejected
    shipped_via = Column(String(50))  # email, social, dashboard
    shipped_at = Column(DateTime)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    goal = relationship("ExecutionGoal", back_populates="deliverables")
    task = relationship("ExecutionTask", back_populates="deliverables")
    shop = relationship("Shop")


# ── Email Sequences ───────────────────────────────────────────────────────

class EmailSequence(Base):
    __tablename__ = "email_sequences"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    trigger_type = Column(String(50), nullable=False)  # winback, welcome, post_purchase, promotion
    steps = Column(JSON, default=list)  # [{delay_days, subject, body, template}]
    status = Column(String(20), default="draft")  # draft, active, paused, completed
    enrolled_count = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    open_rate = Column(Float)
    click_rate = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shop = relationship("Shop")


# ── Immutable Audit Log ──────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    actor = Column(String(50), nullable=False)  # claw_bot, maya, scout, emma, alex, max, user, system
    action = Column(String(100), nullable=False)  # goal_created, task_started, email_sent, etc.
    resource_type = Column(String(50))  # goal, task, deliverable, email
    resource_id = Column(String(36))
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")


# ── OpenClaw Engine: Agent Memory ─────────────────────────────────────────

class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    agent_type = Column(String(20), nullable=False, index=True)
    memory_type = Column(String(50), nullable=False)  # insight, preference, fact, pattern, success, failure
    content = Column(Text, nullable=False)
    importance = Column(Float, default=0.5)  # 0.0-1.0, higher = more important
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime)
    source_goal_id = Column(String(36))
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")


# ── OpenClaw Engine: Scheduled Tasks ──────────────────────────────────────

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    task_name = Column(String(255), nullable=False)
    agent_type = Column(String(20))  # specific agent or null for multi-agent
    instructions = Column(Text, nullable=False)
    schedule_type = Column(String(20), nullable=False)  # daily, weekly, hourly, interval
    schedule_config = Column(JSON, default=dict)  # {hour: 9, minute: 0, days: ["mon","wed","fri"]}
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime)
    next_run_at = Column(DateTime)
    run_count = Column(Integer, default=0)
    last_result_summary = Column(Text)
    last_status = Column(String(20))  # completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")


# ── OpenClaw Engine: Proactive Insights ───────────────────────────────────

class ProactiveInsight(Base):
    __tablename__ = "proactive_insights"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    agent_type = Column(String(20), nullable=False)
    insight_type = Column(String(50), nullable=False)  # opportunity, threat, alert, suggestion, milestone
    severity = Column(String(20), default="info")  # critical, warning, info, success
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    data_snapshot = Column(JSON, default=dict)  # raw data that triggered the insight
    is_read = Column(Boolean, default=False)
    is_actioned = Column(Boolean, default=False)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")


# ── OpenClaw Engine: Web Research Cache ───────────────────────────────────

class WebResearchResult(Base):
    __tablename__ = "web_research_results"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False, index=True)
    research_type = Column(String(50), nullable=False)  # competitor_search, trend_search, review_scrape
    query = Column(Text, nullable=False)
    results_json = Column(JSON, default=dict)
    source_urls = Column(JSON, default=list)
    agent_type = Column(String(20))
    ttl_hours = Column(Integer, default=24)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")
