import uuid
from datetime import datetime, date

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, Numeric, String, Text,
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
    latitude = Column(Float)
    longitude = Column(Float)
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
    first_seen = Column(DateTime)
    last_seen = Column(DateTime)
    visit_count = Column(Integer, default=1)
    total_spent = Column(Numeric(12, 2), default=0)

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
    total = Column(Numeric(12, 2), nullable=False)
    items_count = Column(Integer, default=1)
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
    transaction_count = Column(Integer, default=0)
    avg_transaction_value = Column(Numeric(12, 2), default=0)
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
    rating = Column(Numeric(2, 1))
    review_count = Column(Integer, default=0)
    latitude = Column(Float)
    longitude = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="competitors")
    snapshots = relationship("CompetitorSnapshot", back_populates="competitor", cascade="all, delete-orphan")


class CompetitorSnapshot(Base):
    __tablename__ = "competitor_snapshots"

    id = Column(String(36), primary_key=True, default=new_id)
    competitor_id = Column(String(36), ForeignKey("competitors.id"), nullable=False)
    date = Column(Date, nullable=False)
    rating = Column(Numeric(2, 1))
    review_count = Column(Integer)

    competitor = relationship("Competitor", back_populates="snapshots")


# ── Alert ─────────────────────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=new_id)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), default="warning")
    title = Column(String(255), nullable=False)
    message = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="alerts")
