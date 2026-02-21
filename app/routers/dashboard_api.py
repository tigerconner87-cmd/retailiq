import csv
import io
import random
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import (
    User, Alert, Shop, Recommendation, ShopSettings, Expense,
    RevenueGoal, MarketingCampaign, PlanInterest, WinBackCampaign,
    PostedContent, Agent, AgentActivity, AgentTask,
    Goal, ProductGoal, Product, Customer, Competitor, StrategyNote,
    ExecutionGoal, ExecutionTask, AgentDeliverable, AuditLog,
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
    OnboardingStep1,
    OnboardingStep2,
    OnboardingStep3,
    PlanInterestRequest,
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
    get_product_recommendations,
    get_break_even_analysis,
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
from app.services.marketing_engine import (
    get_content_calendar,
    get_social_posts,
    get_email_campaigns,
    get_promotions,
    get_marketing_performance,
    predict_content_performance,
    generate_hashtags,
    get_weekly_marketing_report,
    build_email_template,
)
from app.services.cache import cache_get, cache_set
from app.services.dashboard_service import (
    get_activity_feed,
    get_customer_segments,
    get_revenue_heatmap,
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
    get_trend_alerts,
    get_response_analysis,
    get_competitive_advantages,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _effective_plan_tier(user: User) -> str:
    """Return effective plan tier — demo and trial users get full 'scale' access."""
    if user.email == "demo@forgeapp.com":
        return "scale"
    # 14-day trial gets full access
    if user.trial_end_date and datetime.utcnow() < user.trial_end_date:
        return "scale"
    if user.created_at and (datetime.utcnow() - user.created_at).days <= 14:
        return "scale"
    return user.plan_tier or "starter"


def _get_shop(db: Session, user: User):
    shop = get_shop_for_user(db, user.id)
    if not shop:
        raise HTTPException(status_code=404, detail="No shop found for this user")
    return shop


# ── Activity Feed ────────────────────────────────────────────────────────────

@router.get("/activity-feed")
def dashboard_activity_feed(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return {"events": get_activity_feed(db, shop.id, limit=10)}


# ── Customer Segments ────────────────────────────────────────────────────────

@router.get("/customers/segments")
def dashboard_customer_segments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_customer_segments(db, shop.id)


# ── Revenue Heatmap ──────────────────────────────────────────────────────────

@router.get("/sales/heatmap")
def dashboard_revenue_heatmap(
    days: int = Query(90),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    return {"days": get_revenue_heatmap(db, shop.id, days=days)}


# ── Overview ─────────────────────────────────────────────────────────────────

@router.get("/summary", response_model=SummaryResponse)
def dashboard_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    hit = cache_get(f"riq:summary:{shop.id}")
    if hit:
        return hit
    result = get_summary(db, shop.id)
    cache_set(f"riq:summary:{shop.id}", result, ttl=30)
    return result


@router.get("/ai-actions")
def dashboard_ai_actions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_ai_actions(db, shop.id)


# ── Sales ────────────────────────────────────────────────────────────────────

@router.get("/sales", response_model=SalesResponse)
def dashboard_sales(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    key = f"riq:sales:{shop.id}:{days}"
    hit = cache_get(key)
    if hit:
        return hit
    result = get_sales_trends(db, shop.id, days=days)
    cache_set(key, result, ttl=60)
    return result


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


@router.get("/products/recommendations")
def dashboard_product_recommendations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_product_recommendations(db, shop.id)


@router.get("/financial/break-even")
def dashboard_break_even(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_break_even_analysis(db, shop.id)


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


@router.get("/competitors/trend-alerts")
def competitor_trend_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_trend_alerts(db, shop.id)


@router.get("/competitors/response-analysis")
def competitor_response_analysis(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_response_analysis(db, shop.id)


@router.get("/competitors/advantages")
def competitor_advantages(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_competitive_advantages(db, shop.id)


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


# ── Marketing Content Engine ────────────────────────────────────────────────

@router.get("/marketing-engine/calendar")
def marketing_calendar(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_content_calendar(db, shop.id)


@router.get("/marketing-engine/social-posts")
def marketing_social_posts(
    category: str = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    return get_social_posts(db, shop.id, category)


@router.get("/marketing-engine/email-campaigns")
def marketing_email_campaigns(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_email_campaigns(db, shop.id)


@router.get("/marketing-engine/promotions")
def marketing_promotions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_promotions(db, shop.id)


@router.get("/marketing-engine/performance")
def marketing_performance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_marketing_performance(db, shop.id)


@router.post("/marketing-engine/predict")
def marketing_predict(
    content: str = Query(...),
    platform: str = Query("instagram"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    return predict_content_performance(db, shop.id, content, platform)


@router.get("/marketing-engine/hashtags")
def marketing_hashtags(
    topic: str = Query(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    return generate_hashtags(db, shop.id, topic)


@router.get("/marketing-engine/weekly-report")
def marketing_weekly_report(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_weekly_marketing_report(db, shop.id)


@router.get("/marketing-engine/email-template")
def marketing_email_template(
    template_type: str = Query("welcome"),
    discount: str = Query("15"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    return build_email_template(db, shop.id, template_type, {"discount": discount})


@router.get("/weekly-digest-preview", response_class=HTMLResponse)
def weekly_digest_preview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate a preview of the weekly email digest with inline styles."""
    shop = _get_shop(db, user)
    report = get_weekly_marketing_report(db, shop.id)
    summary = get_summary(db, shop.id)

    rev = report.get("revenue", {})
    top = report.get("top_products", [])[:5]
    recs = report.get("recommendations", [])[:5]
    period = report.get("period", {})

    products_html = "".join(
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #2a2a3e;color:#e2e8f0">{p.get("name","")}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #2a2a3e;text-align:right;color:#e2e8f0">${p.get("revenue",0):,.2f}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #2a2a3e;text-align:right;color:#e2e8f0">{p.get("units",0)}</td></tr>'
        for p in top
    )
    recs_html = "".join(
        f'<li style="padding:6px 0;border-bottom:1px solid #2a2a3e;color:#cbd5e1">{r}</li>' for r in recs
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Weekly Digest — {shop.name}</title></head>
<body style="margin:0;padding:0;background:#0f0f1a;font-family:Arial,sans-serif">
<div style="max-width:600px;margin:20px auto;background:#1e1e2e;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.3)">
  <div style="background:linear-gradient(135deg,#6366f1,#06b6d4);padding:32px 24px;color:#fff;text-align:center">
    <h1 style="margin:0;font-size:24px">Forge Weekly Digest</h1>
    <p style="margin:8px 0 0;opacity:.85;font-size:14px">{shop.name} — {period.get('start','')} to {period.get('end','')}</p>
  </div>
  <div style="padding:24px">
    <h2 style="font-size:16px;color:#e2e8f0;margin:0 0 16px">Revenue Snapshot</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
      <tr>
        <td style="padding:16px;background:#16162a;border-radius:8px;text-align:center;width:50%">
          <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em">This Week</div>
          <div style="font-size:24px;font-weight:700;color:#e2e8f0;margin-top:4px">${rev.get('this_week',0):,.2f}</div>
        </td>
        <td style="width:12px"></td>
        <td style="padding:16px;background:#16162a;border-radius:8px;text-align:center;width:50%">
          <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em">Change</div>
          <div style="font-size:24px;font-weight:700;color:{'#10b981' if rev.get('change_pct',0)>=0 else '#ef4444'};margin-top:4px">{rev.get('change_pct',0):+.1f}%</div>
        </td>
      </tr>
    </table>

    <h2 style="font-size:16px;color:#e2e8f0;margin:0 0 12px">Top Products</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:24px;font-size:13px">
      <thead><tr style="background:#16162a">
        <th style="padding:8px 12px;text-align:left;font-weight:600;color:#94a3b8">Product</th>
        <th style="padding:8px 12px;text-align:right;font-weight:600;color:#94a3b8">Revenue</th>
        <th style="padding:8px 12px;text-align:right;font-weight:600;color:#94a3b8">Units</th>
      </tr></thead>
      <tbody>{products_html}</tbody>
    </table>

    <h2 style="font-size:16px;color:#e2e8f0;margin:0 0 12px">AI Recommendations</h2>
    <ul style="list-style:none;padding:0;margin:0 0 24px;font-size:13px;color:#cbd5e1">{recs_html}</ul>

    <div style="text-align:center;padding:16px 0">
      <a href="/dashboard" style="display:inline-block;padding:12px 32px;background:linear-gradient(135deg,#6366f1,#06b6d4);color:#fff;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px">View Full Dashboard</a>
    </div>
  </div>
  <div style="padding:16px 24px;background:#16162a;text-align:center;font-size:11px;color:#64748b;border-top:1px solid #2a2a3e">
    Sent by Forge — Your AI-Powered Retail Intelligence Platform
  </div>
</div>
</body></html>"""
    return HTMLResponse(content=html)


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
        "google_api_key": settings.google_api_key if settings else "",
        "anthropic_api_key": settings.anthropic_api_key if settings and hasattr(settings, 'anthropic_api_key') else "",
        "ai_enabled": settings.ai_enabled if settings and hasattr(settings, 'ai_enabled') else True,
        "ai_personality": settings.ai_personality if settings and hasattr(settings, 'ai_personality') else "professional",
        "instagram_handle": shop.instagram_handle or "",
        "facebook_url": shop.facebook_url or "",
        "tiktok_handle": shop.tiktok_handle or "",
        "email_list_size": shop.email_list_size or 0,
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
    if body.google_api_key is not None:
        settings.google_api_key = body.google_api_key
        # Also update the runtime config so Google API calls use the new key immediately
        from app.config import settings as app_settings
        app_settings.GOOGLE_PLACES_API_KEY = body.google_api_key
    if body.anthropic_api_key is not None:
        settings.anthropic_api_key = body.anthropic_api_key
    if body.ai_enabled is not None:
        settings.ai_enabled = body.ai_enabled
    if body.ai_personality is not None:
        settings.ai_personality = body.ai_personality

    # Update social media fields on shop
    if body.instagram_handle is not None:
        shop.instagram_handle = body.instagram_handle
    if body.facebook_url is not None:
        shop.facebook_url = body.facebook_url
    if body.tiktok_handle is not None:
        shop.tiktok_handle = body.tiktok_handle
    if body.email_list_size is not None:
        shop.email_list_size = body.email_list_size

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


@router.post("/onboarding/step1")
def onboarding_step1(body: OnboardingStep1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if shop:
        shop.name = body.business_name or shop.name
        shop.address = body.address or shop.address
        shop.pos_system = body.pos_system or shop.pos_system
        shop.category = body.industry or shop.category
        shop.city = body.city or shop.city
        if body.employees:
            emp_map = {"1-5": 3, "6-15": 10, "16-50": 30, "50+": 60}
            shop.staff_count = emp_map.get(body.employees, 3)
    user.onboarding_step = 1
    db.commit()
    return {"detail": "Step 1 saved"}


@router.post("/onboarding/step2")
def onboarding_step2(body: OnboardingStep2, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if shop and body.competitors:
        from app.models import Competitor, new_id
        for name in body.competitors[:5]:
            name = name.strip()
            if not name:
                continue
            existing = db.query(Competitor).filter(
                Competitor.shop_id == shop.id, Competitor.name == name
            ).first()
            if not existing:
                db.add(Competitor(id=new_id(), shop_id=shop.id, name=name, category=shop.category))
        db.commit()
    user.onboarding_step = 2
    db.commit()
    return {"detail": "Step 2 saved"}


@router.post("/onboarding/generate-products")
def onboarding_generate_products(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI-generate products for the user's industry."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(status_code=400, detail="No shop found")

    industry = body.get("industry", "general_retail").replace("_", " ")
    shop_name = body.get("shop_name", shop.name)
    city = body.get("city", "")
    state = body.get("state", "")
    location = f" in {city}, {state}" if city else ""

    # Try AI generation, fall back to template-based
    products = []
    try:
        from app.config import settings as app_settings
        import os, json
        api_key = app_settings.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            import httpx
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": f'Generate 18 realistic products for a {industry} shop called "{shop_name}"{location}. For each product include: name, price (realistic), category, sku (short code). Return ONLY a JSON array, no markdown. Example: [{{"name":"...","price":29.99,"category":"...","sku":"SKU001"}}]'}],
                },
                timeout=30,
            )
            text = resp.json()["content"][0]["text"].strip()
            # Extract JSON array
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                products = json.loads(text[start:end])
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("AI product generation failed: %s", e)

    # Fallback: template products by industry
    if not products:
        products = _fallback_products(industry)

    # Save to database
    from app.models import Product, new_id
    saved = []
    for p in products[:20]:
        prod = Product(
            id=new_id(), shop_id=shop.id,
            name=p.get("name", "Product"),
            price=round(float(p.get("price", 19.99)), 2),
            category=p.get("category", "General"),
            sku=p.get("sku", ""),
            stock_quantity=random.randint(10, 100),
            cost=round(float(p.get("price", 19.99)) * 0.45, 2),
        )
        db.add(prod)
        saved.append({"name": prod.name, "price": float(prod.price), "category": prod.category})
    db.commit()
    return {"products": saved, "count": len(saved)}


def _fallback_products(industry):
    """Generate template products when AI is unavailable."""
    templates = {
        "clothing fashion": [
            {"name": "Classic Cotton T-Shirt", "price": 28.00, "category": "Tops", "sku": "TOP001"},
            {"name": "Slim Fit Jeans", "price": 65.00, "category": "Bottoms", "sku": "BOT001"},
            {"name": "Oversized Hoodie", "price": 55.00, "category": "Outerwear", "sku": "OUT001"},
            {"name": "Floral Sundress", "price": 72.00, "category": "Dresses", "sku": "DRS001"},
            {"name": "Leather Belt", "price": 35.00, "category": "Accessories", "sku": "ACC001"},
            {"name": "Canvas Tote Bag", "price": 42.00, "category": "Accessories", "sku": "ACC002"},
            {"name": "Wool Beanie", "price": 22.00, "category": "Accessories", "sku": "ACC003"},
            {"name": "Linen Button-Up", "price": 48.00, "category": "Tops", "sku": "TOP002"},
            {"name": "Yoga Leggings", "price": 45.00, "category": "Activewear", "sku": "ACT001"},
            {"name": "Denim Jacket", "price": 89.00, "category": "Outerwear", "sku": "OUT002"},
            {"name": "Silk Scarf", "price": 38.00, "category": "Accessories", "sku": "ACC004"},
            {"name": "Crossbody Purse", "price": 58.00, "category": "Bags", "sku": "BAG001"},
            {"name": "Running Sneakers", "price": 95.00, "category": "Shoes", "sku": "SHO001"},
            {"name": "Graphic Sweatshirt", "price": 50.00, "category": "Tops", "sku": "TOP003"},
            {"name": "Tailored Blazer", "price": 120.00, "category": "Outerwear", "sku": "OUT003"},
        ],
        "food beverage": [
            {"name": "Artisan Sourdough", "price": 8.50, "category": "Bread", "sku": "BRD001"},
            {"name": "Cold Brew Coffee (12oz)", "price": 5.50, "category": "Beverages", "sku": "BEV001"},
            {"name": "Organic Granola", "price": 12.00, "category": "Pantry", "sku": "PAN001"},
            {"name": "Avocado Toast", "price": 11.00, "category": "Breakfast", "sku": "BRK001"},
            {"name": "Seasonal Fruit Smoothie", "price": 7.50, "category": "Beverages", "sku": "BEV002"},
            {"name": "Gourmet Sandwich", "price": 13.50, "category": "Lunch", "sku": "LUN001"},
            {"name": "Fresh Pressed Juice", "price": 9.00, "category": "Beverages", "sku": "BEV003"},
            {"name": "Croissant", "price": 4.50, "category": "Pastry", "sku": "PAS001"},
            {"name": "Matcha Latte", "price": 6.50, "category": "Beverages", "sku": "BEV004"},
            {"name": "House Salad", "price": 10.50, "category": "Lunch", "sku": "LUN002"},
            {"name": "Chocolate Chip Cookie", "price": 3.50, "category": "Pastry", "sku": "PAS002"},
            {"name": "Espresso Shot", "price": 3.00, "category": "Beverages", "sku": "BEV005"},
            {"name": "Turkey Club Wrap", "price": 12.00, "category": "Lunch", "sku": "LUN003"},
            {"name": "Blueberry Muffin", "price": 4.00, "category": "Pastry", "sku": "PAS003"},
            {"name": "Kombucha (16oz)", "price": 6.00, "category": "Beverages", "sku": "BEV006"},
        ],
    }
    # Default fallback
    default = [
        {"name": f"Product {i+1}", "price": round(random.uniform(10, 80), 2), "category": "General", "sku": f"GEN{i+1:03d}"}
        for i in range(15)
    ]
    for key, val in templates.items():
        if key in industry.lower():
            return val
    return default


@router.post("/onboarding/add-products")
def onboarding_add_products(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save manually entered or CSV-imported products."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(status_code=400, detail="No shop found")

    from app.models import Product, new_id
    products = body.get("products", [])
    saved = 0
    for p in products[:100]:
        name = str(p.get("name", "")).strip()
        price = float(p.get("price", 0))
        if not name or price <= 0:
            continue
        prod = Product(
            id=new_id(), shop_id=shop.id,
            name=name, price=round(price, 2),
            category=str(p.get("category", "General")).strip() or "General",
            sku=str(p.get("sku", "")).strip(),
            stock_quantity=int(p.get("stock", 0)) or random.randint(10, 50),
            cost=round(price * 0.45, 2),
        )
        db.add(prod)
        saved += 1
    db.commit()
    return {"detail": f"{saved} products saved", "count": saved}


@router.post("/onboarding/generate-competitors")
def onboarding_generate_competitors(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI-generate competitor suggestions."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(status_code=400, detail="No shop found")

    industry = body.get("industry", "general_retail").replace("_", " ")
    city = body.get("city", "")
    state = body.get("state", "")
    shop_name = body.get("shop_name", shop.name)

    competitors = []
    try:
        from app.config import settings as app_settings
        import os, json
        api_key = app_settings.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            import httpx
            location = f"{city}, {state}" if city else "a mid-size US city"
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": f'Suggest 5 realistic competitor business names for a {industry} shop called "{shop_name}" in {location}. For each include: name, estimated_rating (3.0-4.8), estimated_review_count (20-300). Return ONLY a JSON array, no markdown. Example: [{{"name":"...","estimated_rating":4.2,"estimated_review_count":89}}]'}],
                },
                timeout=20,
            )
            text = resp.json()["content"][0]["text"].strip()
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                competitors = json.loads(text[start:end])
    except Exception:
        pass

    if not competitors:
        prefixes = ["Urban", "City", "Metro", "Local", "Main Street"]
        suffixes = {"clothing fashion": ["Style Co", "Threads", "Apparel", "Fashion Hub", "Boutique"],
                     "food beverage": ["Cafe", "Kitchen", "Bites", "Roasters", "Eats"]}
        default_suf = ["Shop", "Store", "Market", "Goods", "Supply"]
        suf_list = default_suf
        for k, v in suffixes.items():
            if k in industry.lower():
                suf_list = v
                break
        competitors = [{"name": f"{prefixes[i]} {suf_list[i]}", "estimated_rating": round(random.uniform(3.2, 4.6), 1), "estimated_review_count": random.randint(30, 250)} for i in range(5)]

    return {"competitors": competitors}


@router.post("/onboarding/generate-goals")
def onboarding_generate_goals(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI-generate smart goals based on industry and revenue."""
    rev_range = body.get("monthly_revenue", "15k_50k")
    rev_map = {"under_5k": 4000, "5k_15k": 10000, "15k_50k": 30000, "50k_100k": 75000, "100k_plus": 125000}
    est_rev = rev_map.get(rev_range, 30000)

    goals = [
        {"title": "Monthly Revenue Target", "target_value": int(est_rev * 1.1), "unit": "$", "goal_type": "revenue"},
        {"title": "Monthly Transactions", "target_value": max(50, int(est_rev / 25)), "unit": "#", "goal_type": "transactions"},
        {"title": "New Customers This Month", "target_value": max(10, int(est_rev / 500)), "unit": "#", "goal_type": "customers"},
        {"title": "Average Order Value", "target_value": round(est_rev / max(1, int(est_rev / 25)) * 1.05, 2), "unit": "$", "goal_type": "aov"},
    ]
    return {"goals": goals}


@router.get("/setup-progress")
def get_setup_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get onboarding setup progress for the progress bar."""
    shop = _get_shop(db, user)
    if not shop:
        return {"steps": [], "completed": 0, "total": 6}

    from app.models import Product, Goal, Competitor, AgentRun, SentEmail
    product_count = db.query(Product).filter(Product.shop_id == shop.id).count()
    goal_count = db.query(Goal).filter(Goal.shop_id == shop.id).count()
    comp_count = db.query(Competitor).filter(Competitor.shop_id == shop.id).count()
    agent_run_count = db.query(AgentRun).filter(AgentRun.shop_id == shop.id).count()
    email_count = db.query(SentEmail).filter(SentEmail.shop_id == shop.id).count()

    steps = [
        {"key": "business_info", "label": "Business info added", "done": bool(shop.name and shop.name != "My Shop")},
        {"key": "products", "label": f"Products added ({product_count})", "done": product_count >= 5},
        {"key": "goals", "label": "First goal set", "done": goal_count > 0},
        {"key": "competitors", "label": "Competitors added", "done": comp_count > 0, "link": "/dashboard/competitors"},
        {"key": "agent_run", "label": "First agent run", "done": agent_run_count > 0, "link": "/dashboard/agents"},
        {"key": "email_sent", "label": "First email sent", "done": email_count > 0, "link": "/dashboard/win-back"},
    ]
    completed = sum(1 for s in steps if s["done"])
    pct = round((completed / len(steps)) * 100) if steps else 0
    return {"steps": steps, "completed": completed, "total": len(steps), "percentage": pct}


@router.get("/team-status")
def get_team_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get AI team status summary for overview page."""
    shop = _get_shop(db, user)
    if not shop:
        return {"pending_count": 0, "today_created": 0, "today_approved": 0, "last_activity": None}

    from app.models import AgentDeliverable, AuditLog
    from sqlalchemy import func
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    pending = db.query(func.count(AgentDeliverable.id)).filter(
        AgentDeliverable.shop_id == shop.id, AgentDeliverable.status == "pending_approval"
    ).scalar() or 0

    today_created = db.query(func.count(AgentDeliverable.id)).filter(
        AgentDeliverable.shop_id == shop.id, AgentDeliverable.created_at >= today_start
    ).scalar() or 0

    today_approved = db.query(func.count(AgentDeliverable.id)).filter(
        AgentDeliverable.shop_id == shop.id, AgentDeliverable.status.in_(["approved", "sent", "shipped"]),
        AgentDeliverable.created_at >= today_start
    ).scalar() or 0

    last = db.query(AuditLog).filter(AuditLog.shop_id == shop.id).order_by(AuditLog.created_at.desc()).first()
    last_activity = None
    if last:
        last_activity = {"actor": last.actor, "action": last.action, "time": last.created_at.isoformat()}

    return {"pending_count": pending, "today_created": today_created, "today_approved": today_approved, "last_activity": last_activity}


# ── CSV Import (Settings page) ─────────────────────────────────────────────

@router.get("/csv-template/{template_type}")
def download_csv_template(template_type: str):
    """Download a sample CSV template for import."""
    templates = {
        "products": "name,price,category,sku,stock\nClassic T-Shirt,28.00,Tops,TOP001,50\nSlim Jeans,65.00,Bottoms,BOT001,30\nCanvas Tote,42.00,Accessories,ACC001,25\n",
        "customers": "name,email,phone,last_visit_date\nSarah Johnson,sarah@example.com,555-0101,2025-12-15\nMike Chen,mike@example.com,555-0102,2025-11-20\nLisa Park,lisa@example.com,,2025-10-05\n",
        "sales": "date,amount,items,customer_email\n2025-12-01,45.50,2,sarah@example.com\n2025-12-01,89.00,3,mike@example.com\n2025-12-02,28.00,1,\n",
    }
    content = templates.get(template_type, "")
    if not content:
        raise HTTPException(status_code=404, detail="Unknown template type")

    return StreamingResponse(
        io.StringIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=forge_{template_type}_template.csv"},
    )


@router.post("/csv-import/{import_type}")
async def csv_import(
    import_type: str,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import CSV data (products, customers, or sales)."""
    shop = _get_shop(db, user)
    if not shop:
        raise HTTPException(status_code=400, detail="No shop found")

    rows = body.get("rows", [])
    if not rows:
        raise HTTPException(status_code=400, detail="No data provided")

    from app.models import Product, Customer, Transaction, TransactionItem, new_id

    if import_type == "products":
        count = 0
        for row in rows[:500]:
            name = str(row.get("name", "")).strip()
            price = float(row.get("price", 0))
            if not name or price <= 0:
                continue
            db.add(Product(
                id=new_id(), shop_id=shop.id, name=name,
                price=round(price, 2), cost=round(price * 0.45, 2),
                category=str(row.get("category", "General")).strip() or "General",
                sku=str(row.get("sku", "")).strip(),
                stock_quantity=int(row.get("stock", 0)) or 0,
            ))
            count += 1
        db.commit()
        return {"detail": f"{count} products imported", "count": count}

    elif import_type == "customers":
        count = 0
        for row in rows[:1000]:
            name = str(row.get("name", "")).strip()
            email_addr = str(row.get("email", "")).strip()
            if not name:
                continue
            last_visit = None
            if row.get("last_visit_date"):
                try:
                    last_visit = datetime.strptime(str(row["last_visit_date"]), "%Y-%m-%d")
                except Exception:
                    pass
            # Determine segment
            segment = "regular"
            if last_visit:
                days_since = (datetime.utcnow() - last_visit).days
                if days_since > 60:
                    segment = "lost"
                elif days_since > 30:
                    segment = "at_risk"
            db.add(Customer(
                id=new_id(), shop_id=shop.id,
                email=email_addr or None,
                segment=segment,
                first_seen=last_visit or datetime.utcnow(),
                last_seen=last_visit or datetime.utcnow(),
                visit_count=1,
            ))
            count += 1
        db.commit()
        return {"detail": f"{count} customers imported", "count": count}

    elif import_type == "sales":
        count = 0
        for row in rows[:2000]:
            amount = float(row.get("amount", 0))
            if amount <= 0:
                continue
            ts = datetime.utcnow()
            if row.get("date"):
                try:
                    ts = datetime.strptime(str(row["date"]), "%Y-%m-%d")
                except Exception:
                    pass
            items_count = int(row.get("items", 1)) or 1
            db.add(Transaction(
                id=new_id(), shop_id=shop.id,
                subtotal=round(amount, 2), tax=round(amount * 0.08, 2),
                total=round(amount * 1.08, 2), items_count=items_count,
                timestamp=ts, payment_method="imported",
            ))
            count += 1
        db.commit()
        return {"detail": f"{count} sales imported", "count": count}

    raise HTTPException(status_code=400, detail="Unknown import type")


@router.post("/onboarding/complete")
def onboarding_complete(body: OnboardingStep3, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.onboarding_data import generate_onboarding_setup

    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(status_code=400, detail="No shop found for user")

    # Check if setup was already done (idempotency)
    from app.models import Goal
    existing = db.query(Goal).filter(Goal.shop_id == shop.id).first()
    if not existing:
        generate_onboarding_setup(
            db=db,
            shop=shop,
            monthly_revenue=body.monthly_revenue,
            revenue_target=body.revenue_target,
            competitor_names=body.competitors,
            biggest_challenges=body.biggest_challenges,
        )

    user.onboarding_step = 5
    user.onboarding_completed = True
    db.commit()
    return {"detail": "Onboarding complete", "redirect": "/dashboard?welcome=1"}


# ── Daily Briefing ──────────────────────────────────────────────────────────

@router.get("/briefing")
def dashboard_briefing(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.briefing import get_briefing
    shop = _get_shop(db, user)
    return get_briefing(db, shop.id, user.full_name)


# ── Notifications (Bell) ───────────────────────────────────────────────────

@router.get("/notifications")
def dashboard_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    alerts = (
        db.query(Alert)
        .filter(Alert.shop_id == shop.id)
        .order_by(Alert.created_at.desc())
        .limit(15)
        .all()
    )
    unread = sum(1 for a in alerts if not a.is_read)

    severity_icons = {
        "critical": "🔴", "warning": "🟡", "info": "🔵", "success": "🟢",
    }
    category_icons = {
        "revenue": "💰", "customers": "👥", "reviews": "⭐", "competitors": "🔍",
        "inventory": "📦", "goals": "🎯", "general": "📋",
    }

    return {
        "notifications": [
            {
                "id": a.id,
                "icon": category_icons.get(a.category or "general", "📋"),
                "severity_icon": severity_icons.get(a.severity, "🔵"),
                "title": a.title,
                "message": (a.message or "")[:120],
                "category": a.category or "general",
                "severity": a.severity,
                "is_read": a.is_read,
                "time_ago": _time_ago(a.created_at),
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts[:10]
        ],
        "unread_count": unread,
    }


@router.post("/notifications/read-all")
def mark_all_notifications_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    db.query(Alert).filter(Alert.shop_id == shop.id, Alert.is_read.is_(False)).update({"is_read": True})
    db.commit()
    return {"detail": "All notifications marked as read"}


def _time_ago(dt):
    if not dt:
        return "unknown"
    diff = datetime.utcnow() - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    weeks = days // 7
    if weeks < 4:
        return f"{weeks}w ago"
    return dt.strftime("%b %d")


# ── Insights ────────────────────────────────────────────────────────────────

@router.get("/insights")
def dashboard_insights(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.insights import generate_insights
    shop = _get_shop(db, user)
    return generate_insights(db, shop.id)


@router.get("/sparkline")
def dashboard_sparkline(days: int = 7, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.insights import get_sparkline_data
    shop = _get_shop(db, user)
    return get_sparkline_data(db, shop.id, days)


# ── Search ──────────────────────────────────────────────────────────────────

@router.get("/search")
def dashboard_search(q: str = Query(""), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models import Product, Customer, Competitor
    shop = _get_shop(db, user)
    if not q or len(q) < 2:
        return {"results": []}

    results = []
    term = f"%{q}%"

    # Search products
    products = db.query(Product).filter(
        Product.shop_id == shop.id,
        Product.name.ilike(term),
    ).limit(5).all()
    for p in products:
        results.append({
            "type": "product",
            "icon": "📦",
            "title": p.name,
            "subtitle": p.category or "Product",
            "section": "products",
        })

    # Search customers
    customers = db.query(Customer).filter(
        Customer.shop_id == shop.id,
        Customer.email.ilike(term),
    ).limit(5).all()
    for c in customers:
        results.append({
            "type": "customer",
            "icon": "👤",
            "title": c.email or f"Customer #{c.id[:8]}",
            "subtitle": f"{c.segment} — {c.visit_count} visits",
            "section": "customers",
        })

    # Search competitors
    competitors = db.query(Competitor).filter(
        Competitor.shop_id == shop.id,
        Competitor.name.ilike(term),
    ).limit(3).all()
    for comp in competitors:
        results.append({
            "type": "competitor",
            "icon": "🔍",
            "title": comp.name,
            "subtitle": f"Rating: {float(comp.rating):.1f}" if comp.rating else "Competitor",
            "section": "competitors",
        })

    return {"results": results[:10]}


# ── Plan Interest (Upgrade Page) ──────────────────────────────────────────

@router.post("/plan-interest")
def submit_plan_interest(body: PlanInterestRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pi = PlanInterest(
        user_id=user.id,
        email=body.email,
        plan=body.plan,
        billing_cycle=body.billing_cycle,
    )
    db.add(pi)
    db.commit()
    return {"detail": "Interest recorded", "plan": body.plan}


# ── Win-Back Campaigns ────────────────────────────────────────────────────

@router.get("/winback/overview")
def winback_overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.winback import get_winback_overview
    shop = _get_shop(db, user)
    return get_winback_overview(db, shop.id)


@router.get("/winback/at-risk")
def winback_at_risk(
    sort_by: str = Query("days_since"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.winback import get_at_risk_customers
    shop = _get_shop(db, user)
    return get_at_risk_customers(db, shop.id, sort_by)


@router.get("/winback/templates")
def winback_templates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.winback import get_campaign_templates
    return get_campaign_templates()


@router.get("/winback/history")
def winback_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.winback import get_campaign_history
    shop = _get_shop(db, user)
    return get_campaign_history(db, shop.id)


@router.get("/winback/settings")
def winback_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.winback import get_automation_settings
    shop = _get_shop(db, user)
    return get_automation_settings(db, shop.id)


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
    filename = f"forge_{body.export_type}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Posted Content Tracking ──────────────────────────────────────────────────

@router.post("/content/mark-posted")
def mark_content_posted(
    body: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    posted = PostedContent(
        shop_id=shop.id,
        content_type=body.get("content_type", "social"),
        content_text=body.get("content_text", ""),
        platform=body.get("platform", ""),
        hashtags=body.get("hashtags", ""),
    )
    db.add(posted)
    db.commit()
    return {"detail": "Content marked as posted", "id": posted.id}


@router.get("/content/posted-stats")
def get_posted_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from sqlalchemy import func
    shop = _get_shop(db, user)

    # This week's posts
    today = datetime.utcnow()
    week_start = today - __import__("datetime").timedelta(days=today.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    total_this_week = db.query(func.count(PostedContent.id)).filter(
        PostedContent.shop_id == shop.id,
        PostedContent.posted_at >= week_start,
    ).scalar() or 0

    total_all = db.query(func.count(PostedContent.id)).filter(
        PostedContent.shop_id == shop.id,
    ).scalar() or 0

    # Recent posted items
    recent = db.query(PostedContent).filter(
        PostedContent.shop_id == shop.id,
    ).order_by(PostedContent.posted_at.desc()).limit(20).all()

    suggested_per_week = 7
    usage_rate = round((total_this_week / suggested_per_week) * 100) if suggested_per_week > 0 else 0

    return {
        "total_this_week": total_this_week,
        "suggested_per_week": suggested_per_week,
        "usage_rate": min(usage_rate, 100),
        "total_all_time": total_all,
        "recent": [
            {
                "id": p.id,
                "content_type": p.content_type,
                "content_text": p.content_text[:100] + ("..." if len(p.content_text) > 100 else ""),
                "platform": p.platform,
                "posted_at": p.posted_at.isoformat() if p.posted_at else None,
            }
            for p in recent
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# AI AGENT FLEET
# ══════════════════════════════════════════════════════════════════════════════

AGENT_DEFAULTS = {
    "maya": {
        "name": "Maya",
        "role": "Marketing Director",
        "description": "Maya creates your social media posts, email campaigns, and promotions. She knows your products, your customers, and your competitors' weaknesses.",
        "color": "#8b5cf6",
        "icon": "megaphone",
        "config_defaults": {
            "posting_frequency": "daily",
            "tone": "casual",
            "focus": "products",
            "auto_generate": True,
        },
    },
    "scout": {
        "name": "Scout",
        "role": "Competitive Intelligence Analyst",
        "description": "Scout monitors your competitors around the clock. When they slip up, Scout tells you exactly how to capitalize.",
        "color": "#ef4444",
        "icon": "binoculars",
        "config_defaults": {
            "monitor_frequency": "daily",
            "alert_sensitivity": "significant",
            "auto_generate_responses": True,
            "competitors_to_watch": [],
        },
    },
    "emma": {
        "name": "Emma",
        "role": "Customer Success Manager",
        "description": "Emma keeps your customers coming back. She writes win-back emails, responds to reviews, and identifies VIPs who deserve special attention.",
        "color": "#10b981",
        "icon": "heart",
        "config_defaults": {
            "at_risk_threshold": 30,
            "auto_draft_emails": True,
            "review_response_style": "grateful",
            "winback_discount": 15,
        },
    },
    "alex": {
        "name": "Alex",
        "role": "Chief Strategy Officer",
        "description": "Alex analyzes your data every day and gives you CEO-level strategic advice. Think of Alex as your business consultant who never sleeps.",
        "color": "#3b82f6",
        "icon": "chess",
        "config_defaults": {
            "report_frequency": "daily",
            "focus_areas": ["revenue", "customers"],
            "alert_threshold": "10pct",
            "goals_auto_adjust": False,
        },
    },
    "max": {
        "name": "Max",
        "role": "Sales Director",
        "description": "Max finds ways to increase your revenue. Bundle suggestions, pricing optimization, upsell opportunities — Max spots money you're leaving on the table.",
        "color": "#f59e0b",
        "icon": "dollar",
        "config_defaults": {
            "bundle_suggestions": True,
            "price_optimization": "moderate",
            "markdown_alerts": True,
            "upsell_suggestions": True,
        },
    },
}


def _seed_agent_activities(db: Session, shop_id: str, agents: list[Agent]):
    """Generate realistic mock activity data for demo accounts."""
    now = datetime.utcnow()
    agent_map = {a.agent_type: a for a in agents}

    activities_data = [
        # Maya - Marketing
        ("maya", "content_generated", "Created 7 Instagram posts for this week", -0.5),
        ("maya", "content_generated", "Drafted Valentine's Day email campaign — subject line: 'Our hearts are full (and so are our shelves)'", -2.1),
        ("maya", "content_generated", "Generated 15 hashtag sets for your top products", -4.5),
        ("maya", "content_generated", "Created weekend flash sale promotion — 20% off accessories", -18.3),
        ("maya", "analysis_complete", "Content performance review: Lifestyle posts get 2.3x more engagement than product-only posts", -26.7),
        ("maya", "content_generated", "Wrote 3 Instagram stories for behind-the-scenes content", -43.2),
        ("maya", "content_generated", "Created email sequence for new customer onboarding (3 emails)", -51.0),
        ("maya", "content_generated", "Generated TikTok script for trending product: Canvas Tote Bag", -72.5),
        ("maya", "analysis_complete", "Best posting time analysis: Your audience is most active Tue & Thu 11am-1pm", -96.0),
        ("maya", "content_generated", "Created 5 promotional graphics copy for Spring Collection launch", -120.4),
        # Scout - Competitor Intelligence
        ("scout", "alert_sent", "Style Hub received 2 negative reviews about slow service — opportunity alert sent", -1.2),
        ("scout", "analysis_complete", "Neighborhood Finds rating dropped from 3.4 to 3.1 — generated competitive response campaign", -8.0),
        ("scout", "report_generated", "Weekly competitor report generated — you're #1 in your area", -24.0),
        ("scout", "alert_sent", "Urban Threads launched a 30% off sale — counter-promotion suggested", -36.5),
        ("scout", "analysis_complete", "Competitor review sentiment analysis: Style Hub has 34% negative mentions about 'pricing'", -52.0),
        ("scout", "alert_sent", "New competitor detected: 'The Modern Boutique' opened 0.8mi away — monitoring started", -74.3),
        ("scout", "report_generated", "Monthly competitive landscape report ready — 3 new opportunities identified", -120.0),
        ("scout", "analysis_complete", "Price comparison: You're 12% below market avg on accessories — room to increase margins", -168.0),
        # Emma - Customer Care
        ("emma", "email_drafted", "Drafted win-back emails for 8 at-risk customers who haven't visited in 30+ days", -1.8),
        ("emma", "review_response", "Generated review response for 5-star review from Emery T. — 'Amazing boutique!'", -5.5),
        ("emma", "customer_alert", "Identified 3 VIP customers for appreciation outreach — total lifetime value: $4,200", -12.0),
        ("emma", "email_drafted", "Created 'We miss you' campaign for 12 lapsed customers with personalized product picks", -28.0),
        ("emma", "review_response", "Drafted empathetic response for 3-star review mentioning wait times", -48.0),
        ("emma", "customer_alert", "Churn risk alert: 5 regular customers haven't returned in 25+ days", -72.5),
        ("emma", "email_drafted", "Birthday email template created for this month's 4 customer birthdays", -96.0),
        ("emma", "analysis_complete", "Customer satisfaction trend: NPS improved from 62 to 71 this month", -144.0),
        # Alex - Strategy
        ("alex", "analysis_complete", "Daily analysis: Revenue up 12% vs last week. Beanie Hats driving growth.", -0.8),
        ("alex", "alert_sent", "Alert: At current pace, you'll miss your monthly goal by $3,200. Recommended actions sent.", -6.0),
        ("alex", "report_generated", "Weekly strategy brief ready — 3 action items for revenue growth", -24.0),
        ("alex", "analysis_complete", "Product mix analysis: Accessories margin is 62% vs apparel at 45%. Recommend increasing accessory floor space.", -48.0),
        ("alex", "alert_sent", "Break-even alert: You need $420/day to cover fixed costs. Today's pace: $580. On track.", -72.5),
        ("alex", "report_generated", "Q1 2026 strategy review prepared — focus areas: foot traffic, AOV, accessory expansion", -168.0),
        ("alex", "analysis_complete", "Revenue forecasting: Projecting $18,400 for this month based on current trends (+8% vs last month)", -192.0),
        # Max - Sales
        ("max", "opportunity_found", "Bundle opportunity: Customers who buy Slim Fit Jeans often buy Canvas Tote Bag. Suggested bundle saves 15%.", -2.0),
        ("max", "alert_sent", "Price alert: Cotton Hoodie demand is strong. Test raising price by $5 — projected +$380/month revenue.", -7.5),
        ("max", "alert_sent", "Slow mover: Linen Summer Dress hasn't sold in 14 days. Suggested 20% markdown to move inventory.", -16.0),
        ("max", "opportunity_found", "Upsell opportunity: 67% of Scarf buyers also browse Gloves. Cross-sell display recommended.", -32.0),
        ("max", "analysis_complete", "Promotion effectiveness: 'Buy 2 Get 1' outperforms '25% off' by 2.1x in your category", -56.0),
        ("max", "opportunity_found", "New bundle suggestion: 'Date Night Kit' — Slim Fit Jeans + Leather Belt + Canvas Tote = $127 (save $18)", -96.0),
        ("max", "alert_sent", "Inventory alert: Beanie Hat stock down to 4 units. Reorder recommended — it's your #2 seller.", -120.0),
        ("max", "analysis_complete", "Weekly revenue optimization report: 5 pricing adjustments suggested, est. impact +$1,200/month", -168.0),
    ]

    for agent_type, action_type, desc, hours_ago in activities_data:
        agent = agent_map.get(agent_type)
        if not agent:
            continue
        db.add(AgentActivity(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            shop_id=shop_id,
            action_type=action_type,
            description=desc,
            details={},
            created_at=now + timedelta(hours=hours_ago),
        ))


def _seed_claw_bot_data(db: Session, shop_id: str):
    """Seed demo execution goals, tasks, deliverables and audit log for Claw Bot."""
    now = datetime.utcnow()

    # Check if already seeded
    existing = db.query(ExecutionGoal).filter(ExecutionGoal.shop_id == shop_id).first()
    if existing:
        return

    goals_data = [
        {
            "command": "Create a full week of social media content for our spring collection",
            "intent": "content_creation",
            "priority": "high",
            "status": "completed",
            "quality_score": 87.5,
            "total_tasks": 3,
            "completed_tasks": 3,
            "total_tokens": 4200,
            "total_cost": 0.021,
            "hours_ago": 4,
            "tasks": [
                {"agent_type": "maya", "instructions": "Generate 7 Instagram captions for spring collection", "status": "completed", "quality_score": 91.0, "tokens_used": 1800, "duration_ms": 3200},
                {"agent_type": "maya", "instructions": "Create 3 promotional email subjects and bodies", "status": "completed", "quality_score": 85.0, "tokens_used": 1400, "duration_ms": 2800},
                {"agent_type": "maya", "instructions": "Draft 2 TikTok video scripts with hooks", "status": "completed", "quality_score": 82.0, "tokens_used": 1000, "duration_ms": 2100},
            ],
            "deliverables": [
                {"agent_type": "maya", "type": "social_post", "title": "Spring Collection — Instagram Week", "content": "Monday: 'New arrivals are blooming! Our Spring Collection just dropped — think pastels, florals, and fresh fits for the season ahead. Link in bio!'\n\nTuesday: 'Style tip: Pair our new Linen Sundress with the Canvas Tote for the perfect weekend look. Which color is your fave? Drop a comment!'\n\nWednesday: 'Behind the scenes at Forge HQ — picking our favorite pieces from the Spring line. Stay tuned for a surprise drop Friday!'\n\nThursday: 'Customer spotlight: @emery_t rocking the Slim Fit Jeans with our Leather Belt combo. Tag us to be featured!'\n\nFriday: 'FLASH FRIDAY: 20% off all new spring accessories for the next 24 hours. Use code SPRING24 at checkout.'\n\nSaturday: 'Weekend vibes with our new Oversized Hoodie in Sage Green. Cozy never looked this good.'\n\nSunday: 'Week in review: Which was your favorite spring look? Vote in our stories!'", "quality": 91.0, "status": "approved"},
                {"agent_type": "maya", "type": "email_campaign", "title": "Spring Launch Email Sequence", "content": "Subject: Spring has sprung at [Shop Name]!\n\nHi [Name],\n\nOur Spring Collection is here and it's our freshest drop yet. From breezy linens to vibrant accessories — there's something for everyone.\n\nShop early for first pick on limited pieces.\n\n[CTA: Shop Spring Collection]", "quality": 85.0, "status": "shipped"},
            ],
        },
        {
            "command": "Analyze competitor pricing and find opportunities",
            "intent": "competitive_analysis",
            "priority": "medium",
            "status": "completed",
            "quality_score": 79.0,
            "total_tasks": 2,
            "completed_tasks": 2,
            "total_tokens": 3100,
            "total_cost": 0.016,
            "hours_ago": 18,
            "tasks": [
                {"agent_type": "scout", "instructions": "Compare pricing across all tracked competitors", "status": "completed", "quality_score": 82.0, "tokens_used": 1600, "duration_ms": 2900},
                {"agent_type": "max", "instructions": "Identify pricing optimization opportunities", "status": "completed", "quality_score": 76.0, "tokens_used": 1500, "duration_ms": 2700},
            ],
            "deliverables": [
                {"agent_type": "scout", "type": "report", "title": "Competitor Price Comparison Report", "content": "Competitor pricing analysis for your market:\n\n1. Style Hub: Average price 8% higher on comparable items. Weak on accessories.\n2. Urban Threads: Running a 30% off sale this week — expect foot traffic dip.\n3. Neighborhood Finds: Prices 5% below yours but declining review scores.\n\nOpportunity: You're underpriced on accessories by 12%. Room to increase margins on Leather Belts, Scarves, and Tote Bags.", "quality": 82.0, "status": "approved"},
                {"agent_type": "max", "type": "recommendation", "title": "Pricing Optimization Suggestions", "content": "Based on competitive analysis, here are 5 pricing adjustments:\n\n1. Leather Belt: $45 → $52 (+$7) — still below competitor avg\n2. Canvas Tote: $38 → $42 (+$4) — high demand supports increase\n3. Silk Scarf: $35 → $39 (+$4) — unique design justifies premium\n4. Beanie Hat: Keep at $28 — competitive sweet spot\n5. Cotton Hoodie: $55 → $59 (+$4) — strong repeat purchase item\n\nEstimated monthly impact: +$1,420 revenue", "quality": 76.0, "status": "draft"},
            ],
        },
        {
            "command": "Win back customers who haven't visited in 30 days",
            "intent": "customer_retention",
            "priority": "high",
            "status": "executing",
            "quality_score": None,
            "total_tasks": 2,
            "completed_tasks": 1,
            "total_tokens": 1800,
            "total_cost": 0.009,
            "hours_ago": 1,
            "tasks": [
                {"agent_type": "emma", "instructions": "Identify at-risk customers and draft win-back emails", "status": "completed", "quality_score": 88.0, "tokens_used": 1800, "duration_ms": 3400},
                {"agent_type": "emma", "instructions": "Create follow-up sequence for non-responders", "status": "running", "quality_score": None, "tokens_used": 0, "duration_ms": 0},
            ],
            "deliverables": [
                {"agent_type": "emma", "type": "email_campaign", "title": "Win-Back Campaign — 8 At-Risk Customers", "content": "Subject: We miss you, [Name]!\n\nIt's been a while since your last visit and we've got some exciting new pieces we think you'd love.\n\nAs a thank you for being a loyal customer, here's 15% off your next purchase:\n\nCode: COMEBACK15\n\nValid for 7 days. We can't wait to see you again!\n\n[CTA: Shop New Arrivals]", "quality": 88.0, "status": "draft"},
            ],
        },
    ]

    audit_entries = []

    for g_data in goals_data:
        goal_id = str(uuid.uuid4())
        goal = ExecutionGoal(
            id=goal_id,
            shop_id=shop_id,
            command=g_data["command"],
            intent=g_data["intent"],
            priority=g_data["priority"],
            status=g_data["status"],
            plan={"tasks": [{"agent": t["agent_type"], "instructions": t["instructions"]} for t in g_data["tasks"]]},
            quality_score=g_data["quality_score"],
            total_tasks=g_data["total_tasks"],
            completed_tasks=g_data["completed_tasks"],
            total_tokens=g_data["total_tokens"],
            total_cost=g_data["total_cost"],
            created_at=now - timedelta(hours=g_data["hours_ago"]),
        )
        db.add(goal)
        audit_entries.append(AuditLog(
            id=str(uuid.uuid4()), shop_id=shop_id, actor="claw_bot",
            action="goal_started", resource_type="goal", resource_id=goal_id,
            details={"command": g_data["command"], "intent": g_data["intent"]},
            created_at=now - timedelta(hours=g_data["hours_ago"]),
        ))

        for i, t_data in enumerate(g_data["tasks"]):
            task_id = str(uuid.uuid4())
            task = ExecutionTask(
                id=task_id,
                goal_id=goal_id,
                shop_id=shop_id,
                agent_type=t_data["agent_type"],
                instructions=t_data["instructions"],
                depends_on=[],
                status=t_data["status"],
                quality_score=t_data["quality_score"],
                tokens_used=t_data["tokens_used"],
                duration_ms=t_data["duration_ms"],
                created_at=now - timedelta(hours=g_data["hours_ago"]) + timedelta(minutes=i * 2),
            )
            db.add(task)

            if t_data["status"] == "completed":
                audit_entries.append(AuditLog(
                    id=str(uuid.uuid4()), shop_id=shop_id, actor="claw_bot",
                    action="task_completed", resource_type="task", resource_id=task_id,
                    details={"agent_type": t_data["agent_type"], "quality_score": t_data["quality_score"]},
                    created_at=now - timedelta(hours=g_data["hours_ago"]) + timedelta(minutes=i * 2 + 3),
                ))

            # Create deliverables for this task's agent
            for d_data in g_data.get("deliverables", []):
                if d_data["agent_type"] == t_data["agent_type"] and t_data["status"] == "completed":
                    del_id = str(uuid.uuid4())
                    deliverable = AgentDeliverable(
                        id=del_id,
                        goal_id=goal_id,
                        task_id=task_id,
                        shop_id=shop_id,
                        agent_type=d_data["agent_type"],
                        deliverable_type=d_data["type"],
                        title=d_data["title"],
                        content=d_data["content"],
                        quality_scores={"relevance": d_data["quality"], "clarity": d_data["quality"] - 2, "brand_voice": d_data["quality"] + 1},
                        overall_quality=d_data["quality"],
                        status=d_data["status"],
                        created_at=now - timedelta(hours=g_data["hours_ago"]) + timedelta(minutes=5),
                    )
                    db.add(deliverable)
                    audit_entries.append(AuditLog(
                        id=str(uuid.uuid4()), shop_id=shop_id, actor="claw_bot",
                        action="deliverable_created", resource_type="deliverable", resource_id=del_id,
                        details={"title": d_data["title"], "quality_score": d_data["quality"]},
                        created_at=now - timedelta(hours=g_data["hours_ago"]) + timedelta(minutes=5),
                    ))

    for entry in audit_entries:
        db.add(entry)


@router.get("/agents")
async def get_agents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all agents for the current shop, creating defaults if needed."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(404, "Shop not found")

    agents = db.query(Agent).filter(Agent.shop_id == shop.id).all()

    # Auto-create agents on first access
    if not agents:
        for atype, meta in AGENT_DEFAULTS.items():
            agent = Agent(
                id=str(uuid.uuid4()),
                shop_id=shop.id,
                agent_type=atype,
                is_active=True,
                configuration=meta["config_defaults"],
            )
            db.add(agent)
            agents.append(agent)
        db.flush()
        # Seed mock activity for demo
        _seed_agent_activities(db, shop.id, agents)
        _seed_claw_bot_data(db, shop.id)
        db.commit()

    # Get activity counts
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = []
    for agent in agents:
        meta = AGENT_DEFAULTS.get(agent.agent_type, {})
        today_count = db.query(AgentActivity).filter(
            AgentActivity.agent_id == agent.id,
            AgentActivity.created_at >= today_start,
        ).count()
        month_count = db.query(AgentActivity).filter(
            AgentActivity.agent_id == agent.id,
            AgentActivity.created_at >= month_start,
        ).count()
        last_activity = db.query(AgentActivity).filter(
            AgentActivity.agent_id == agent.id,
        ).order_by(AgentActivity.created_at.desc()).first()

        result.append({
            "id": agent.id,
            "agent_type": agent.agent_type,
            "name": meta.get("name", agent.agent_type.title()),
            "role": meta.get("role", ""),
            "description": meta.get("description", ""),
            "color": meta.get("color", "#6366f1"),
            "icon": meta.get("icon", "bot"),
            "is_active": agent.is_active,
            "configuration": agent.configuration or meta.get("config_defaults", {}),
            "tasks_today": today_count,
            "tasks_month": month_count,
            "last_action": last_activity.description if last_activity else None,
            "last_action_at": last_activity.created_at.isoformat() if last_activity else None,
        })

    # Aggregate metrics
    total_month = db.query(AgentActivity).filter(
        AgentActivity.shop_id == shop.id,
        AgentActivity.created_at >= month_start,
    ).count()

    content_count = db.query(AgentActivity).filter(
        AgentActivity.shop_id == shop.id,
        AgentActivity.action_type == "content_generated",
        AgentActivity.created_at >= month_start,
    ).count()

    opps_count = db.query(AgentActivity).filter(
        AgentActivity.shop_id == shop.id,
        AgentActivity.action_type.in_(["opportunity_found", "alert_sent"]),
        AgentActivity.created_at >= month_start,
    ).count()

    return {
        "agents": result,
        "metrics": {
            "total_tasks_month": total_month,
            "content_generated": content_count,
            "opportunities_found": opps_count,
            "estimated_revenue_impact": round(total_month * 28.5, -1),
            "hours_saved": round(total_month * 0.3, 1),
        },
        "plan_tier": _effective_plan_tier(user),
    }


@router.put("/agents/{agent_type}/toggle")
async def toggle_agent(
    agent_type: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(404, "Shop not found")
    agent = db.query(Agent).filter(Agent.shop_id == shop.id, Agent.agent_type == agent_type).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    agent.is_active = not agent.is_active
    db.commit()
    return {"ok": True, "is_active": agent.is_active}


@router.put("/agents/{agent_type}/configure")
async def configure_agent(
    agent_type: str,
    config: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(404, "Shop not found")
    agent = db.query(Agent).filter(Agent.shop_id == shop.id, Agent.agent_type == agent_type).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    agent.configuration = config
    db.commit()
    return {"ok": True, "configuration": agent.configuration}


@router.get("/agents/{agent_type}/activity")
async def get_agent_activity(
    agent_type: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(404, "Shop not found")
    agent = db.query(Agent).filter(Agent.shop_id == shop.id, Agent.agent_type == agent_type).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    activities = (
        db.query(AgentActivity)
        .filter(AgentActivity.agent_id == agent.id)
        .order_by(AgentActivity.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "activities": [
            {
                "id": a.id,
                "action_type": a.action_type,
                "description": a.description,
                "details": a.details,
                "created_at": a.created_at.isoformat(),
            }
            for a in activities
        ]
    }


@router.get("/agents/activity/all")
async def get_all_agent_activity(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    agent_filter: str = Query(None),
):
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(404, "Shop not found")

    q = (
        db.query(AgentActivity, Agent.agent_type)
        .join(Agent, Agent.id == AgentActivity.agent_id)
        .filter(AgentActivity.shop_id == shop.id)
    )
    if agent_filter:
        q = q.filter(Agent.agent_type == agent_filter)

    rows = q.order_by(AgentActivity.created_at.desc()).limit(50).all()

    return {
        "activities": [
            {
                "id": a.id,
                "agent_type": atype,
                "agent_name": AGENT_DEFAULTS.get(atype, {}).get("name", atype),
                "agent_color": AGENT_DEFAULTS.get(atype, {}).get("color", "#6366f1"),
                "action_type": a.action_type,
                "description": a.description,
                "created_at": a.created_at.isoformat(),
            }
            for a, atype in rows
        ]
    }


# ── Agent Tasks ──────────────────────────────────────────────────────────────

def _seed_agent_tasks(db: Session, shop_id: str):
    """Generate demo tasks for the task board."""
    now = datetime.utcnow()
    tasks = [
        ("maya", "Create Valentine's Day social campaign", "Generate 5 Instagram posts and 2 stories for Valentine's Day", "completed", "high", -72, -48, "Created 5 posts with lifestyle imagery and 2 story templates. Average engagement predicted: 4.2%"),
        ("maya", "Design spring collection teaser content", "Create preview posts for upcoming spring arrivals", "in_progress", "medium", -12, -6, None),
        ("scout", "Analyze Style Hub's weekend sale impact", "Monitor competitor pricing changes and customer flow", "completed", "high", -48, -24, "Style Hub's 30% sale drove 15% traffic increase. Recommended counter: exclusive bundle deals targeting their dissatisfied customers."),
        ("scout", "Weekly competitor review scan", "Check all competitor review changes and new reviews", "in_progress", "medium", -8, -4, None),
        ("emma", "Draft win-back emails for lapsed VIPs", "Create personalized emails for 5 VIP customers inactive 30+ days", "completed", "high", -96, -72, "Drafted 5 personalized win-back emails with 15% discount offers. 3 customers have personal product picks based on purchase history."),
        ("emma", "Respond to new Google reviews", "Draft responses for 3 new reviews received this week", "pending", "medium", -2, None, None),
        ("alex", "Monthly revenue forecast update", "Analyze current trends and update Q1 projections", "completed", "high", -120, -96, "Q1 projection updated: $54,200 (+8% vs Q4). Key drivers: accessory category growth and improved repeat rate."),
        ("alex", "Identify underperforming product categories", "Run margin analysis across all categories", "pending", "medium", -4, None, None),
        ("max", "Create weekend bundle suggestions", "Design 3 product bundles for weekend promotion", "in_progress", "high", -6, -3, None),
        ("max", "Price optimization analysis", "Review slow movers for markdown opportunities", "pending", "low", -1, None, None),
    ]

    for agent_type, title, desc, status, priority, created_h, started_h, result in tasks:
        task = AgentTask(
            id=str(uuid.uuid4()),
            shop_id=shop_id,
            agent_type=agent_type,
            title=title,
            description=desc,
            status=status,
            priority=priority,
            created_at=now + timedelta(hours=created_h),
            started_at=(now + timedelta(hours=started_h)) if started_h else None,
            completed_at=(now + timedelta(hours=started_h + 12)) if status == "completed" and started_h else None,
            result=result,
        )
        db.add(task)


@router.get("/agents/tasks")
async def get_agent_tasks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status: str = Query(None),
    agent_filter: str = Query(None),
):
    """Get all agent tasks for the task board."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(404, "Shop not found")

    # Auto-seed tasks on first access
    existing = db.query(AgentTask).filter(AgentTask.shop_id == shop.id).count()
    if existing == 0:
        _seed_agent_tasks(db, shop.id)
        db.commit()

    q = db.query(AgentTask).filter(AgentTask.shop_id == shop.id)
    if status:
        q = q.filter(AgentTask.status == status)
    if agent_filter:
        q = q.filter(AgentTask.agent_type == agent_filter)

    tasks = q.order_by(AgentTask.created_at.desc()).all()

    return {
        "tasks": [
            {
                "id": t.id,
                "agent_type": t.agent_type,
                "agent_name": AGENT_DEFAULTS.get(t.agent_type, {}).get("name", t.agent_type),
                "agent_color": AGENT_DEFAULTS.get(t.agent_type, {}).get("color", "#6366f1"),
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "created_at": t.created_at.isoformat(),
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "result": t.result,
            }
            for t in tasks
        ],
        "counts": {
            "pending": db.query(AgentTask).filter(AgentTask.shop_id == shop.id, AgentTask.status == "pending").count(),
            "in_progress": db.query(AgentTask).filter(AgentTask.shop_id == shop.id, AgentTask.status == "in_progress").count(),
            "completed": db.query(AgentTask).filter(AgentTask.shop_id == shop.id, AgentTask.status == "completed").count(),
        },
    }


@router.post("/agents/tasks")
async def create_agent_task(
    agent_type: str = Body(...),
    title: str = Body(...),
    description: str = Body(""),
    priority: str = Body("medium"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new task for an agent."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(404, "Shop not found")
    if agent_type not in AGENT_DEFAULTS:
        raise HTTPException(400, "Invalid agent type")

    task = AgentTask(
        id=str(uuid.uuid4()),
        shop_id=shop.id,
        agent_type=agent_type,
        title=title,
        description=description,
        priority=priority,
    )
    db.add(task)
    db.commit()

    return {
        "ok": True,
        "task": {
            "id": task.id,
            "agent_type": task.agent_type,
            "agent_name": AGENT_DEFAULTS[agent_type]["name"],
            "agent_color": AGENT_DEFAULTS[agent_type]["color"],
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "created_at": task.created_at.isoformat(),
        },
    }


@router.put("/agents/tasks/{task_id}/status")
async def update_agent_task_status(
    task_id: str,
    status: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a task's status."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(404, "Shop not found")
    task = db.query(AgentTask).filter(AgentTask.id == task_id, AgentTask.shop_id == shop.id).first()
    if not task:
        raise HTTPException(404, "Task not found")

    now = datetime.utcnow()
    task.status = status
    if status == "in_progress" and not task.started_at:
        task.started_at = now
    elif status == "completed":
        task.completed_at = now
    db.commit()

    return {"ok": True, "status": task.status}


# ══════════════════════════════════════════════════════════════════════════════
# CRUD — Goals, Products, Customers, Competitors
# ══════════════════════════════════════════════════════════════════════════════

# ── Goals CRUD ──

@router.post("/goals")
async def create_goal(
    goal_type: str = Body(...),
    title: str = Body(...),
    target_value: float = Body(...),
    unit: str = Body("$"),
    period: str = Body("monthly"),
    period_key: str = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    goal = Goal(
        id=str(uuid.uuid4()),
        shop_id=shop.id,
        goal_type=goal_type,
        title=title,
        target_value=target_value,
        unit=unit,
        period=period,
        period_key=period_key,
    )
    db.add(goal)
    db.commit()
    return {"ok": True, "id": goal.id, "title": goal.title}


@router.put("/goals/{goal_id}")
async def update_goal(
    goal_id: str,
    title: str = Body(None),
    target_value: float = Body(None),
    period_key: str = Body(None),
    status: str = Body(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.shop_id == shop.id).first()
    if not goal:
        raise HTTPException(404, "Goal not found")
    if title is not None:
        goal.title = title
    if target_value is not None:
        goal.target_value = target_value
    if period_key is not None:
        goal.period_key = period_key
    if status is not None:
        goal.status = status
    db.commit()
    return {"ok": True}


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.shop_id == shop.id).first()
    if not goal:
        raise HTTPException(404, "Goal not found")
    db.delete(goal)
    db.commit()
    return {"ok": True}


# ── Product Goals CRUD ──

@router.post("/goals/product-goals")
async def create_product_goal(
    product_id: str = Body(...),
    target_units: int = Body(...),
    period: str = Body(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    now = datetime.utcnow()
    p = period or now.strftime("%Y-%m")
    existing = db.query(ProductGoal).filter(
        ProductGoal.shop_id == shop.id,
        ProductGoal.product_id == product_id,
        ProductGoal.period == p,
    ).first()
    if existing:
        existing.target_units = target_units
    else:
        db.add(ProductGoal(
            id=str(uuid.uuid4()),
            shop_id=shop.id,
            product_id=product_id,
            target_units=target_units,
            period=p,
        ))
    db.commit()
    return {"ok": True}


@router.delete("/goals/product-goals/{pg_id}")
async def delete_product_goal(
    pg_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    pg = db.query(ProductGoal).filter(ProductGoal.id == pg_id, ProductGoal.shop_id == shop.id).first()
    if not pg:
        raise HTTPException(404, "Product goal not found")
    db.delete(pg)
    db.commit()
    return {"ok": True}


# ── Strategy Notes CRUD ──

@router.post("/goals/strategy")
async def create_strategy(
    quarter: str = Body(...),
    title: str = Body(...),
    objectives: list = Body(None),
    key_results: list = Body(None),
    notes: str = Body(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    sn = StrategyNote(
        id=str(uuid.uuid4()),
        shop_id=shop.id,
        quarter=quarter,
        title=title,
        objectives=objectives or [],
        key_results=key_results or [],
        notes=notes,
    )
    db.add(sn)
    db.commit()
    return {"ok": True, "id": sn.id}


@router.put("/goals/strategy/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    title: str = Body(None),
    objectives: list = Body(None),
    key_results: list = Body(None),
    notes: str = Body(None),
    status: str = Body(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    sn = db.query(StrategyNote).filter(StrategyNote.id == strategy_id, StrategyNote.shop_id == shop.id).first()
    if not sn:
        raise HTTPException(404, "Strategy not found")
    if title is not None:
        sn.title = title
    if objectives is not None:
        sn.objectives = objectives
    if key_results is not None:
        sn.key_results = key_results
    if notes is not None:
        sn.notes = notes
    if status is not None:
        sn.status = status
    db.commit()
    return {"ok": True}


# ── Products CRUD ──

@router.post("/products")
async def create_product(
    name: str = Body(...),
    price: float = Body(...),
    cost: float = Body(None),
    category: str = Body(""),
    sku: str = Body(""),
    stock_quantity: int = Body(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    product = Product(
        id=str(uuid.uuid4()),
        shop_id=shop.id,
        name=name,
        price=price,
        cost=cost,
        category=category,
        sku=sku,
        stock_quantity=stock_quantity,
    )
    db.add(product)
    db.commit()
    return {"ok": True, "id": product.id, "name": product.name}


@router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    name: str = Body(None),
    price: float = Body(None),
    cost: float = Body(None),
    category: str = Body(None),
    sku: str = Body(None),
    stock_quantity: int = Body(None),
    is_active: bool = Body(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    product = db.query(Product).filter(Product.id == product_id, Product.shop_id == shop.id).first()
    if not product:
        raise HTTPException(404, "Product not found")
    for field, val in [("name", name), ("price", price), ("cost", cost), ("category", category), ("sku", sku), ("stock_quantity", stock_quantity), ("is_active", is_active)]:
        if val is not None:
            setattr(product, field, val)
    db.commit()
    return {"ok": True}


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    product = db.query(Product).filter(Product.id == product_id, Product.shop_id == shop.id).first()
    if not product:
        raise HTTPException(404, "Product not found")
    product.is_active = False
    db.commit()
    return {"ok": True}


# ── Customers CRUD ──

@router.post("/customers")
async def create_customer(
    email: str = Body(...),
    segment: str = Body("regular"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    customer = Customer(
        id=str(uuid.uuid4()),
        shop_id=shop.id,
        email=email,
        segment=segment,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        visit_count=1,
    )
    db.add(customer)
    db.commit()
    return {"ok": True, "id": customer.id}


@router.put("/customers/{customer_id}")
async def update_customer(
    customer_id: str,
    email: str = Body(None),
    segment: str = Body(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.shop_id == shop.id).first()
    if not customer:
        raise HTTPException(404, "Customer not found")
    if email is not None:
        customer.email = email
    if segment is not None:
        customer.segment = segment
    db.commit()
    return {"ok": True}


# ── Competitors CRUD ──

@router.post("/competitors")
async def create_competitor(
    name: str = Body(...),
    address: str = Body(""),
    category: str = Body(""),
    google_place_id: str = Body(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    comp = Competitor(
        id=str(uuid.uuid4()),
        shop_id=shop.id,
        name=name,
        address=address,
        category=category,
        google_place_id=google_place_id,
    )
    db.add(comp)
    db.commit()
    return {"ok": True, "id": comp.id, "name": comp.name}


@router.delete("/competitors/{competitor_id}")
async def delete_competitor(
    competitor_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    comp = db.query(Competitor).filter(Competitor.id == competitor_id, Competitor.shop_id == shop.id).first()
    if not comp:
        raise HTTPException(404, "Competitor not found")
    db.delete(comp)
    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# SAGE ACTION ENDPOINT — unified action API for Sage AI
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/sage/action")
async def sage_action(
    action: str = Body(...),
    params: dict = Body({}),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unified endpoint for Sage to perform actions on behalf of the user."""
    shop = _get_shop(db, user)
    now = datetime.utcnow()

    try:
        if action == "create_goal":
            goal = Goal(
                id=str(uuid.uuid4()), shop_id=shop.id,
                goal_type=params.get("goal_type", "revenue"),
                title=params.get("title", "Revenue Goal"),
                target_value=float(params.get("target_value", 0)),
                unit=params.get("unit", "$"),
                period=params.get("period", "monthly"),
                period_key=params.get("period_key", now.strftime("%Y-%m")),
            )
            db.add(goal)
            db.commit()
            return {"ok": True, "message": f"Created goal: {goal.title} ({goal.period_key})"}

        elif action == "add_competitor":
            comp = Competitor(
                id=str(uuid.uuid4()), shop_id=shop.id,
                name=params.get("name", "Unnamed"),
                address=params.get("address", ""),
                category=params.get("category", ""),
            )
            db.add(comp)
            db.commit()
            return {"ok": True, "message": f"Added competitor: {comp.name}"}

        elif action == "create_product":
            product = Product(
                id=str(uuid.uuid4()), shop_id=shop.id,
                name=params.get("name", "New Product"),
                price=float(params.get("price", 0)),
                cost=float(params.get("cost", 0)) if params.get("cost") else None,
                category=params.get("category", ""),
            )
            db.add(product)
            db.commit()
            return {"ok": True, "message": f"Added product: {product.name} at ${product.price}"}

        elif action == "set_product_target":
            product_name = params.get("product_name", "")
            product = db.query(Product).filter(
                Product.shop_id == shop.id,
                Product.name.ilike(f"%{product_name}%"),
            ).first()
            if not product:
                return {"ok": False, "message": f"Product '{product_name}' not found"}
            period = params.get("period", now.strftime("%Y-%m"))
            existing = db.query(ProductGoal).filter(
                ProductGoal.shop_id == shop.id,
                ProductGoal.product_id == product.id,
                ProductGoal.period == period,
            ).first()
            target = int(params.get("target_units", 0))
            if existing:
                existing.target_units = target
            else:
                db.add(ProductGoal(
                    id=str(uuid.uuid4()), shop_id=shop.id,
                    product_id=product.id, target_units=target, period=period,
                ))
            db.commit()
            return {"ok": True, "message": f"Set {product.name} target to {target} units for {period}"}

        elif action == "toggle_agent":
            agent_type = params.get("agent_type", "")
            agent = db.query(Agent).filter(Agent.shop_id == shop.id, Agent.agent_type == agent_type).first()
            if not agent:
                return {"ok": False, "message": f"Agent '{agent_type}' not found"}
            active = params.get("active", not agent.is_active)
            agent.is_active = active
            db.commit()
            name = AGENT_DEFAULTS.get(agent_type, {}).get("name", agent_type)
            return {"ok": True, "message": f"{'Activated' if active else 'Paused'} agent {name}"}

        elif action == "create_task":
            agent_type = params.get("agent_type", "alex")
            task = AgentTask(
                id=str(uuid.uuid4()), shop_id=shop.id,
                agent_type=agent_type,
                title=params.get("title", "New Task"),
                description=params.get("description", ""),
                priority=params.get("priority", "medium"),
            )
            db.add(task)
            db.commit()
            name = AGENT_DEFAULTS.get(agent_type, {}).get("name", agent_type)
            return {"ok": True, "message": f"Created task for {name}: {task.title}"}

        elif action == "update_customer":
            email = params.get("email", "")
            customer = db.query(Customer).filter(
                Customer.shop_id == shop.id,
                Customer.email.ilike(f"%{email}%"),
            ).first()
            if not customer:
                return {"ok": False, "message": f"Customer '{email}' not found"}
            segment = params.get("segment")
            if segment:
                customer.segment = segment
            db.commit()
            return {"ok": True, "message": f"Updated customer {customer.email}"}

        elif action == "create_strategy":
            sn = StrategyNote(
                id=str(uuid.uuid4()), shop_id=shop.id,
                quarter=params.get("quarter", f"{now.year}-Q{(now.month - 1) // 3 + 1}"),
                title=params.get("title", "Quarterly Strategy"),
                objectives=params.get("objectives", []),
                key_results=params.get("key_results", []),
                notes=params.get("notes", ""),
            )
            db.add(sn)
            db.commit()
            return {"ok": True, "message": f"Created strategy for {sn.quarter}: {sn.title}"}

        else:
            return {"ok": False, "message": f"Unknown action: {action}"}

    except Exception as e:
        db.rollback()
        return {"ok": False, "message": f"Action failed: {str(e)}"}
