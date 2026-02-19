from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    shop_name: str
    shop_type: str = "general_retail"
    city: str = ""
    pos_system: str = "other"

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


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
    onboarding_completed: bool
    onboarding_step: int
    trial_start_date: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Dashboard Summary ─────────────────────────────────────────────────────────

class SummaryResponse(BaseModel):
    revenue_today: float
    revenue_yesterday: float
    revenue_this_week: float
    revenue_last_week: float
    revenue_this_month: float
    revenue_last_month: float
    revenue_this_year: float
    transactions_today: int
    avg_order_value: float
    items_per_transaction: float
    repeat_customer_rate: float
    revenue_change_dod: float
    revenue_change_wow: float
    revenue_change_mom: float
    total_customers: int
    new_customers_today: int
    estimated_profit_today: float
    daily_foot_traffic_estimate: int
    has_data: bool = True
    effective_date: Optional[str] = None
    data_is_stale: bool = False


# ── Sales ─────────────────────────────────────────────────────────────────────

class SalesDayPoint(BaseModel):
    date: str
    revenue: float
    transactions: int
    avg_value: float = 0


class SalesResponse(BaseModel):
    daily: list[SalesDayPoint]
    weekly_totals: list[dict]
    monthly_totals: list[dict]


class SalesForecastPoint(BaseModel):
    date: str
    predicted_revenue: float
    lower_bound: float
    upper_bound: float


class SalesForecastResponse(BaseModel):
    forecast_7d: list[SalesForecastPoint]
    forecast_30d: list[SalesForecastPoint]
    model_confidence: float


class SalesVelocityResponse(BaseModel):
    hourly_avg: list[dict]
    daily_avg: list[dict]
    best_day_ever: dict
    worst_day_ever: dict
    yoy_growth_rate: Optional[float]
    seasonality_index: list[dict]


class GoalProgressResponse(BaseModel):
    month: str
    target: float
    current: float
    percentage: float
    daily_needed: float
    days_remaining: int
    on_track: bool


# ── Products ──────────────────────────────────────────────────────────────────

class ProductRanking(BaseModel):
    id: str
    name: str
    category: Optional[str]
    revenue: float
    units_sold: int
    avg_price: float
    margin: Optional[float]
    trend: str = "stable"  # growing, stable, declining
    last_sold: Optional[str]
    lifecycle: str = "mature"  # growing, mature, declining


class ProductsResponse(BaseModel):
    top_products: list[ProductRanking]
    total_products: int
    slow_movers: list[dict]
    best_sellers: list[dict]
    bundling_suggestions: list[dict]
    category_breakdown: list[dict]


# ── Customers ─────────────────────────────────────────────────────────────────

class CustomerSegments(BaseModel):
    vip: int
    regular: int
    at_risk: int
    lost: int


class CustomerMetrics(BaseModel):
    total_customers: int
    repeat_customers: int
    new_customers_30d: int
    repeat_rate: float
    churn_rate: float
    avg_revenue_per_customer: float
    avg_visits_per_customer: float
    avg_days_between_visits: float
    segments: CustomerSegments
    top_customers: list[dict]
    acquisition_trend: list[dict]
    spending_distribution: list[dict]


class CohortRow(BaseModel):
    cohort: str
    total: int
    retention: list[Optional[float]]


class CohortResponse(BaseModel):
    cohorts: list[CohortRow]
    months: list[str]


class RFMCustomer(BaseModel):
    id: str
    recency_days: int
    frequency: int
    monetary: float
    rfm_score: str
    segment: str


class RFMResponse(BaseModel):
    customers: list[RFMCustomer]
    segment_counts: dict


class CLVResponse(BaseModel):
    avg_clv: float
    median_clv: float
    top_clv_customers: list[dict]
    clv_distribution: list[dict]


class ChurnPrediction(BaseModel):
    id: str
    risk_score: float
    days_since_visit: int
    visit_count: int
    total_spent: float
    segment: str


class ChurnResponse(BaseModel):
    at_risk_count: int
    predictions: list[ChurnPrediction]
    win_back_opportunities: list[dict]


# ── Competitors ───────────────────────────────────────────────────────────────

class CompetitorInfo(BaseModel):
    id: str
    name: str
    address: Optional[str]
    category: Optional[str]
    rating: Optional[float]
    review_count: int
    rating_change: Optional[float]
    trend: str = "stable"
    sentiment_breakdown: Optional[dict]


class CompetitorsResponse(BaseModel):
    competitors: list[CompetitorInfo]
    own_rating: Optional[float]
    own_review_count: int
    market_position: dict


# ── Reviews ───────────────────────────────────────────────────────────────────

class ReviewItem(BaseModel):
    id: str
    author_name: Optional[str]
    rating: int
    text: Optional[str]
    review_date: Optional[datetime]
    sentiment: Optional[str]
    is_own_shop: bool
    response_text: Optional[str]
    suggested_response: Optional[str]


class ReviewsResponse(BaseModel):
    reviews: list[ReviewItem]
    avg_rating: Optional[float]
    total_reviews: int
    sentiment_breakdown: dict
    rating_distribution: dict
    review_velocity: list[dict]
    nps_estimate: float
    response_rate: float
    common_terms: list[dict]


# ── Financial ─────────────────────────────────────────────────────────────────

class ExpenseItem(BaseModel):
    id: str
    category: str
    name: str
    amount: float
    is_monthly: bool

    model_config = {"from_attributes": True}


class FinancialSummary(BaseModel):
    total_revenue_30d: float
    total_expenses_monthly: float
    estimated_cogs: float
    gross_profit: float
    gross_margin: float
    net_profit_estimate: float
    break_even_daily_transactions: int
    revenue_per_sqft: Optional[float]
    revenue_per_staff_hour: float
    estimated_tax_collected: float
    cash_flow_projection: list[dict]
    monthly_pnl: list[dict]
    expenses: list[ExpenseItem]


# ── Marketing ─────────────────────────────────────────────────────────────────

class CampaignItem(BaseModel):
    id: str
    name: str
    channel: Optional[str]
    spend: float
    start_date: str
    end_date: Optional[str]
    revenue_attributed: float
    roi: float

    model_config = {"from_attributes": True}


class MarketingInsights(BaseModel):
    campaigns: list[CampaignItem]
    total_spend: float
    total_attributed_revenue: float
    overall_roi: float
    avg_customer_acquisition_cost: float
    best_posting_times: list[dict]
    content_suggestions: list[dict]
    promotional_effectiveness: list[dict]


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertItem(BaseModel):
    id: str
    alert_type: str
    severity: str
    category: str
    title: str
    message: Optional[str]
    is_read: bool
    is_snoozed: bool
    created_at: datetime


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]
    unread_count: int
    by_category: dict


# ── Recommendations ───────────────────────────────────────────────────────────

class RecommendationItem(BaseModel):
    id: str
    title: str
    description: Optional[str]
    category: str
    priority: str
    estimated_impact: Optional[str]
    action_steps: Optional[list]
    emoji: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RecommendationsResponse(BaseModel):
    recommendations: list[RecommendationItem]
    total_active: int


# ── Settings ──────────────────────────────────────────────────────────────────

class ShopSettingsResponse(BaseModel):
    shop_name: str
    address: Optional[str]
    category: Optional[str]
    store_size_sqft: Optional[int]
    staff_count: int
    pos_system: Optional[str]
    business_hours: Optional[dict]
    monthly_rent: float
    avg_cogs_percentage: float
    staff_hourly_rate: float
    tax_rate: float
    email_frequency: str
    alert_revenue: bool
    alert_customers: bool
    alert_reviews: bool
    alert_competitors: bool


class ShopSettingsUpdate(BaseModel):
    shop_name: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None
    store_size_sqft: Optional[int] = None
    staff_count: Optional[int] = None
    monthly_rent: Optional[float] = None
    avg_cogs_percentage: Optional[float] = None
    staff_hourly_rate: Optional[float] = None
    tax_rate: Optional[float] = None
    email_frequency: Optional[str] = None
    alert_revenue: Optional[bool] = None
    alert_customers: Optional[bool] = None
    alert_reviews: Optional[bool] = None
    alert_competitors: Optional[bool] = None
    business_hours: Optional[dict] = None
    google_api_key: Optional[str] = None


# ── Onboarding ────────────────────────────────────────────────────────────────

class OnboardingUpdate(BaseModel):
    step: int
    completed: bool = False


class OnboardingStep1(BaseModel):
    business_name: str
    address: str = ""
    locations: str = "1"
    monthly_revenue: str = "10k_25k"
    pos_system: str = "other"


class OnboardingStep2(BaseModel):
    competitors: list[str] = []


class OnboardingStep3(BaseModel):
    revenue_target: float = 25000
    biggest_challenges: list[str] = ["new_customers", "retention", "marketing", "competitors"]
    competitors: list[str] = []
    monthly_revenue: str = "10k_25k"


# ── Export ────────────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    export_type: str  # customers, products, sales, financial
    date_from: Optional[str] = None
    date_to: Optional[str] = None


# ── Plan Interest ────────────────────────────────────────────────────────────

class PlanInterestRequest(BaseModel):
    email: str
    plan: str  # starter, growth, scale
    billing_cycle: str = "monthly"  # monthly, annual


# ── Anomaly ───────────────────────────────────────────────────────────────────

class AnomalyItem(BaseModel):
    date: str
    revenue: float
    expected: float
    deviation: float
    type: str  # spike, dip
