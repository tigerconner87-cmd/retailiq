import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import (
    User, Alert, Shop, Recommendation, ShopSettings, Expense,
    RevenueGoal, MarketingCampaign,
)
from app.schemas import (
    AlertsResponse,
    AnomalyItem,
    ChurnResponse,
    CLVResponse,
    CohortResponse,
    CompetitorsResponse,
    CustomerMetrics,
    ExportRequest,
    FinancialSummary,
    GoalProgressResponse,
    MarketingInsights,
    OnboardingUpdate,
    ProductsResponse,
    RecommendationsResponse,
    ReviewsResponse,
    RFMResponse,
    SalesForecastResponse,
    SalesResponse,
    SalesVelocityResponse,
    ShopSettingsResponse,
    ShopSettingsUpdate,
    SummaryResponse,
)
from app.services.analytics import (
    get_ai_actions,
    get_anomalies,
    get_churn_predictions,
    get_clv,
    get_cohort_analysis,
    get_customer_metrics,
    get_financial_summary,
    get_forecast,
    get_goal_progress,
    get_marketing_insights,
    get_moving_averages,
    get_peak_hours,
    get_product_rankings,
    get_rfm_analysis,
    get_sales_trends,
    get_sales_velocity,
    get_shop_for_user,
    get_summary,
)
from app.services.reviews import get_competitors_summary, get_reviews_summary
from app.services.ai_recommendations import generate_recommendations
from app.services.goals import (
    get_goals_overview,
    get_product_goals,
    get_strategy_notes,
    get_goal_history,
    get_strategy_recommendations,
)
from app.services.competitor_intelligence import (
    get_competitor_overview,
    get_competitor_comparison,
    get_opportunities,
    get_competitor_review_feed,
    get_competitor_sentiment,
    get_market_position,
    get_weekly_report,
    get_marketing_responses,
    update_marketing_response_status,
    generate_capitalize_response,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _get_shop(db: Session, user: User):
    shop = get_shop_for_user(db, user.id)
    if not shop:
        raise HTTPException(status_code=404, detail="No shop found for this user")
    return shop


# ── Overview ─────────────────────────────────────────────────────────────────

@router.get("/summary", response_model=SummaryResponse)
def dashboard_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_summary(db, shop.id)


@router.get("/ai-actions")
def dashboard_ai_actions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_ai_actions(db, shop.id)


# ── Sales ────────────────────────────────────────────────────────────────────

@router.get("/sales", response_model=SalesResponse)
def dashboard_sales(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_sales_trends(db, shop.id, days=days)


@router.get("/sales/velocity", response_model=SalesVelocityResponse)
def dashboard_sales_velocity(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_sales_velocity(db, shop.id)


@router.get("/sales/forecast", response_model=SalesForecastResponse)
def dashboard_forecast(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_forecast(db, shop.id)


@router.get("/sales/goal")
def dashboard_goal(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    result = get_goal_progress(db, shop.id)
    if result is None:
        return {"detail": "No goal set for this month"}
    return result


@router.get("/sales/moving-averages")
def dashboard_moving_averages(days: int = 90, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_moving_averages(db, shop.id, days=days)


@router.get("/sales/anomalies")
def dashboard_anomalies(days: int = 90, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_anomalies(db, shop.id, days=days)


@router.get("/peak-hours")
def dashboard_peak_hours(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_peak_hours(db, shop.id, days=days)


# ── Products ─────────────────────────────────────────────────────────────────

@router.get("/products", response_model=ProductsResponse)
def dashboard_products(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_product_rankings(db, shop.id, days=days)


# ── Customers ────────────────────────────────────────────────────────────────

@router.get("/customers", response_model=CustomerMetrics)
def dashboard_customers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_customer_metrics(db, shop.id)


@router.get("/customers/cohorts", response_model=CohortResponse)
def dashboard_cohorts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_cohort_analysis(db, shop.id)


@router.get("/customers/rfm", response_model=RFMResponse)
def dashboard_rfm(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_rfm_analysis(db, shop.id)


@router.get("/customers/clv", response_model=CLVResponse)
def dashboard_clv(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_clv(db, shop.id)


@router.get("/customers/churn", response_model=ChurnResponse)
def dashboard_churn(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_churn_predictions(db, shop.id)


# ── Competitors & Reviews ────────────────────────────────────────────────────

@router.get("/competitors", response_model=CompetitorsResponse)
def dashboard_competitors(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_competitors_summary(db, shop.id)


# ── Competitor Intelligence ─────────────────────────────────────────────────

@router.get("/competitors/overview")
def competitor_overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_competitor_overview(db, shop.id)


@router.get("/competitors/comparison")
def competitor_comparison(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_competitor_comparison(db, shop.id)


@router.get("/competitors/opportunities")
def competitor_opportunities(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_opportunities(db, shop.id)


@router.get("/competitors/review-feed")
def competitor_review_feed(
    competitor_id: str = Query(None),
    rating: int = Query(None),
    sentiment: str = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    return get_competitor_review_feed(db, shop.id, competitor_id, rating, sentiment)


@router.get("/competitors/sentiment")
def competitor_sentiment(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_competitor_sentiment(db, shop.id)


@router.get("/competitors/market-position")
def competitor_market_position(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_market_position(db, shop.id)


@router.get("/competitors/weekly-report")
def competitor_weekly_report(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_weekly_report(db, shop.id)


@router.get("/competitors/marketing-responses")
def competitor_marketing_responses(
    status: str = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    return get_marketing_responses(db, shop.id, status)


@router.patch("/competitors/marketing-responses/{response_id}")
def update_marketing_response(
    response_id: str,
    status: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    if not update_marketing_response_status(db, shop.id, response_id, status):
        raise HTTPException(status_code=404, detail="Marketing response not found")
    return {"detail": "Status updated"}


@router.post("/competitors/capitalize/{review_id}")
def capitalize_on_review(
    review_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    result = generate_capitalize_response(db, shop.id, review_id)
    if not result:
        raise HTTPException(status_code=404, detail="Review not found")
    return result


# ── Goals & Strategy ──────────────────────────────────────────────────────

@router.get("/goals")
def dashboard_goals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_goals_overview(db, shop.id)


@router.get("/goals/product-goals")
def dashboard_product_goals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_product_goals(db, shop.id)


@router.get("/goals/strategy")
def dashboard_strategy(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_strategy_notes(db, shop.id)


@router.get("/goals/history")
def dashboard_goal_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_goal_history(db, shop.id)


@router.get("/goals/recommendations")
def dashboard_goal_recommendations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_strategy_recommendations(db, shop.id)


@router.get("/reviews", response_model=ReviewsResponse)
def dashboard_reviews(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_reviews_summary(db, shop.id)


# ── Financial ────────────────────────────────────────────────────────────────

@router.get("/financial", response_model=FinancialSummary)
def dashboard_financial(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_financial_summary(db, shop.id)


# ── Marketing ────────────────────────────────────────────────────────────────

@router.get("/marketing", response_model=MarketingInsights)
def dashboard_marketing(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_marketing_insights(db, shop.id)


# ── Recommendations ──────────────────────────────────────────────────────────

@router.get("/recommendations")
def dashboard_recommendations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    recs = (
        db.query(Recommendation)
        .filter(Recommendation.shop_id == shop.id, Recommendation.status == "active")
        .order_by(Recommendation.created_at.desc())
        .all()
    )
    return {
        "recommendations": [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "category": r.category,
                "priority": r.priority,
                "estimated_impact": r.estimated_impact,
                "action_steps": r.action_steps,
                "emoji": r.emoji,
                "status": r.status,
                "created_at": r.created_at,
            }
            for r in recs
        ],
        "total_active": len(recs),
    }


@router.post("/recommendations/refresh")
def refresh_recommendations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    actions = generate_recommendations(db, shop.id)
    return {"detail": f"Generated {len(actions)} recommendations", "count": len(actions)}


@router.patch("/recommendations/{rec_id}/dismiss")
def dismiss_recommendation(rec_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    rec = db.query(Recommendation).filter(Recommendation.id == rec_id, Recommendation.shop_id == shop.id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.status = "dismissed"
    rec.resolved_at = datetime.utcnow()
    db.commit()
    return {"detail": "Dismissed"}


@router.patch("/recommendations/{rec_id}/complete")
def complete_recommendation(rec_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    rec = db.query(Recommendation).filter(Recommendation.id == rec_id, Recommendation.shop_id == shop.id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.status = "done"
    rec.resolved_at = datetime.utcnow()
    db.commit()
    return {"detail": "Marked as done"}


# ── Alerts ───────────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=AlertsResponse)
def dashboard_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    alerts = (
        db.query(Alert)
        .filter(Alert.shop_id == shop.id, Alert.is_snoozed.is_(False))
        .order_by(Alert.created_at.desc())
        .limit(50)
        .all()
    )
    unread = sum(1 for a in alerts if not a.is_read)
    by_category = {}
    for a in alerts:
        cat = a.category or "general"
        by_category[cat] = by_category.get(cat, 0) + 1

    return AlertsResponse(
        alerts=[
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "category": a.category or "general",
                "title": a.title,
                "message": a.message,
                "is_read": a.is_read,
                "is_snoozed": a.is_snoozed,
                "created_at": a.created_at,
            }
            for a in alerts
        ],
        unread_count=unread,
        by_category=by_category,
    )


@router.patch("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.shop_id == shop.id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_read = True
    db.commit()
    return {"detail": "Marked as read"}


@router.patch("/alerts/{alert_id}/snooze")
def snooze_alert(alert_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.shop_id == shop.id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_snoozed = True
    db.commit()
    return {"detail": "Snoozed"}


@router.post("/alerts/read-all")
def mark_all_alerts_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    db.query(Alert).filter(Alert.shop_id == shop.id, Alert.is_read.is_(False)).update({"is_read": True})
    db.commit()
    return {"detail": "All marked as read"}


# ── Settings ─────────────────────────────────────────────────────────────────

@router.get("/settings")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    settings = db.query(ShopSettings).filter(ShopSettings.shop_id == shop.id).first()
    return {
        "shop_name": shop.name,
        "address": shop.address,
        "category": shop.category,
        "store_size_sqft": shop.store_size_sqft,
        "staff_count": shop.staff_count,
        "pos_system": shop.pos_system,
        "business_hours": settings.business_hours if settings else None,
        "monthly_rent": float(settings.monthly_rent) if settings else 0,
        "avg_cogs_percentage": settings.avg_cogs_percentage if settings else 40.0,
        "staff_hourly_rate": float(settings.staff_hourly_rate) if settings else 15.0,
        "tax_rate": settings.tax_rate if settings else 8.25,
        "email_frequency": settings.email_frequency if settings else "weekly",
        "alert_revenue": settings.alert_revenue if settings else True,
        "alert_customers": settings.alert_customers if settings else True,
        "alert_reviews": settings.alert_reviews if settings else True,
        "alert_competitors": settings.alert_competitors if settings else True,
    }


@router.put("/settings")
def update_settings(body: ShopSettingsUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    settings = db.query(ShopSettings).filter(ShopSettings.shop_id == shop.id).first()
    if not settings:
        settings = ShopSettings(shop_id=shop.id)
        db.add(settings)

    # Update shop-level fields
    if body.shop_name is not None:
        shop.name = body.shop_name
    if body.address is not None:
        shop.address = body.address
    if body.category is not None:
        shop.category = body.category
    if body.store_size_sqft is not None:
        shop.store_size_sqft = body.store_size_sqft
    if body.staff_count is not None:
        shop.staff_count = body.staff_count

    # Update settings-level fields
    if body.monthly_rent is not None:
        settings.monthly_rent = body.monthly_rent
    if body.avg_cogs_percentage is not None:
        settings.avg_cogs_percentage = body.avg_cogs_percentage
    if body.staff_hourly_rate is not None:
        settings.staff_hourly_rate = body.staff_hourly_rate
    if body.tax_rate is not None:
        settings.tax_rate = body.tax_rate
    if body.email_frequency is not None:
        settings.email_frequency = body.email_frequency
    if body.alert_revenue is not None:
        settings.alert_revenue = body.alert_revenue
    if body.alert_customers is not None:
        settings.alert_customers = body.alert_customers
    if body.alert_reviews is not None:
        settings.alert_reviews = body.alert_reviews
    if body.alert_competitors is not None:
        settings.alert_competitors = body.alert_competitors
    if body.business_hours is not None:
        settings.business_hours = body.business_hours

    db.commit()
    return {"detail": "Settings updated"}


# ── Onboarding ───────────────────────────────────────────────────────────────

@router.post("/onboarding")
def update_onboarding(body: OnboardingUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.onboarding_step = body.step
    if body.completed:
        user.onboarding_completed = True
    db.commit()
    return {"detail": "Onboarding updated", "step": user.onboarding_step, "completed": user.onboarding_completed}


# ── Export ───────────────────────────────────────────────────────────────────

@router.post("/export")
def export_data(body: ExportRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models import Customer, Product, Transaction
    shop = _get_shop(db, user)

    output = io.StringIO()
    writer = csv.writer(output)

    if body.export_type == "customers":
        writer.writerow(["ID", "Email", "Segment", "Visit Count", "Total Spent", "Avg Order Value", "First Seen", "Last Seen"])
        customers = db.query(Customer).filter(Customer.shop_id == shop.id).order_by(Customer.total_spent.desc()).all()
        for c in customers:
            writer.writerow([
                c.id, c.email or "", c.segment, c.visit_count,
                float(c.total_spent), float(c.avg_order_value) if c.avg_order_value else 0,
                c.first_seen.isoformat() if c.first_seen else "",
                c.last_seen.isoformat() if c.last_seen else "",
            ])
    elif body.export_type == "products":
        writer.writerow(["ID", "Name", "Category", "Price", "Cost", "SKU", "Stock", "Active"])
        products = db.query(Product).filter(Product.shop_id == shop.id).order_by(Product.name).all()
        for p in products:
            writer.writerow([
                p.id, p.name, p.category or "", float(p.price),
                float(p.cost) if p.cost else "", p.sku or "",
                p.stock_quantity or "", p.is_active,
            ])
    elif body.export_type == "sales":
        writer.writerow(["ID", "Date", "Customer ID", "Subtotal", "Tax", "Discount", "Total", "Items", "Payment"])
        q = db.query(Transaction).filter(Transaction.shop_id == shop.id).order_by(Transaction.timestamp.desc())
        if body.date_from:
            q = q.filter(Transaction.timestamp >= body.date_from)
        if body.date_to:
            q = q.filter(Transaction.timestamp <= body.date_to)
        for t in q.limit(10000).all():
            writer.writerow([
                t.id, t.timestamp.isoformat(), t.customer_id or "",
                float(t.subtotal), float(t.tax), float(t.discount),
                float(t.total), t.items_count, t.payment_method,
            ])
    elif body.export_type == "financial":
        writer.writerow(["Category", "Name", "Amount", "Monthly"])
        expenses = db.query(Expense).filter(Expense.shop_id == shop.id).all()
        for e in expenses:
            writer.writerow([e.category, e.name, float(e.amount), e.is_monthly])
    else:
        raise HTTPException(status_code=400, detail="Invalid export type")

    output.seek(0)
    filename = f"retailiq_{body.export_type}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
