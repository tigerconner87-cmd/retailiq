from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, EmailStr


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    shop_name: str
    pos_system: str = "other"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    plan_tier: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────────────────────────

class SummaryResponse(BaseModel):
    revenue_today: float
    revenue_yesterday: float
    revenue_this_week: float
    revenue_last_week: float
    transactions_today: int
    avg_order_value: float
    repeat_customer_rate: float
    revenue_change_dod: float
    revenue_change_wow: float
    total_customers: int
    new_customers_today: int


class SalesDayPoint(BaseModel):
    date: str
    revenue: float
    transactions: int


class SalesResponse(BaseModel):
    daily: list[SalesDayPoint]
    weekly_totals: list[dict]
    monthly_totals: list[dict]


class HourlyHeatmapCell(BaseModel):
    day: int
    hour: int
    value: float


class ProductRanking(BaseModel):
    id: str
    name: str
    category: Optional[str]
    revenue: float
    units_sold: int
    avg_price: float
    margin: Optional[float]


class ProductsResponse(BaseModel):
    top_products: list[ProductRanking]
    total_products: int


class CustomerMetrics(BaseModel):
    total_customers: int
    repeat_customers: int
    new_customers_30d: int
    repeat_rate: float
    avg_revenue_per_customer: float
    avg_visits_per_customer: float
    top_customers: list[dict]


class CompetitorInfo(BaseModel):
    id: str
    name: str
    address: Optional[str]
    rating: Optional[float]
    review_count: int
    rating_change: Optional[float]


class CompetitorsResponse(BaseModel):
    competitors: list[CompetitorInfo]
    own_rating: Optional[float]
    own_review_count: int


class ReviewItem(BaseModel):
    id: str
    author_name: Optional[str]
    rating: int
    text: Optional[str]
    review_date: Optional[datetime]
    sentiment: Optional[str]
    is_own_shop: bool


class ReviewsResponse(BaseModel):
    reviews: list[ReviewItem]
    avg_rating: Optional[float]
    total_reviews: int
    sentiment_breakdown: dict


class AlertItem(BaseModel):
    id: str
    alert_type: str
    severity: str
    title: str
    message: Optional[str]
    is_read: bool
    created_at: datetime


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]
    unread_count: int
