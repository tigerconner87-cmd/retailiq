import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import (
    User, Alert, Shop, Recommendation, ShopSettings, Expense,
    RevenueGoal, MarketingCampaign, PlanInterest, WinBackCampaign,
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
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #eee">{p.get("name","")}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right">${p.get("revenue",0):,.2f}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right">{p.get("units",0)}</td></tr>'
        for p in top
    )
    recs_html = "".join(
        f'<li style="padding:6px 0;border-bottom:1px solid #f3f4f6">{r}</li>' for r in recs
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Weekly Digest — {shop.name}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif">
<div style="max-width:600px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <div style="background:linear-gradient(135deg,#6366f1,#06b6d4);padding:32px 24px;color:#fff;text-align:center">
    <h1 style="margin:0;font-size:24px">Forge Weekly Digest</h1>
    <p style="margin:8px 0 0;opacity:.85;font-size:14px">{shop.name} — {period.get('start','')} to {period.get('end','')}</p>
  </div>
  <div style="padding:24px">
    <h2 style="font-size:16px;color:#111;margin:0 0 16px">Revenue Snapshot</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
      <tr>
        <td style="padding:16px;background:#f9fafb;border-radius:8px;text-align:center;width:50%">
          <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em">This Week</div>
          <div style="font-size:24px;font-weight:700;color:#111;margin-top:4px">${rev.get('this_week',0):,.2f}</div>
        </td>
        <td style="width:12px"></td>
        <td style="padding:16px;background:#f9fafb;border-radius:8px;text-align:center;width:50%">
          <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em">Change</div>
          <div style="font-size:24px;font-weight:700;color:{'#10b981' if rev.get('change_pct',0)>=0 else '#ef4444'};margin-top:4px">{rev.get('change_pct',0):+.1f}%</div>
        </td>
      </tr>
    </table>

    <h2 style="font-size:16px;color:#111;margin:0 0 12px">Top Products</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:24px;font-size:13px">
      <thead><tr style="background:#f9fafb">
        <th style="padding:8px 12px;text-align:left;font-weight:600;color:#6b7280">Product</th>
        <th style="padding:8px 12px;text-align:right;font-weight:600;color:#6b7280">Revenue</th>
        <th style="padding:8px 12px;text-align:right;font-weight:600;color:#6b7280">Units</th>
      </tr></thead>
      <tbody>{products_html}</tbody>
    </table>

    <h2 style="font-size:16px;color:#111;margin:0 0 12px">AI Recommendations</h2>
    <ul style="list-style:none;padding:0;margin:0 0 24px;font-size:13px;color:#374151">{recs_html}</ul>

    <div style="text-align:center;padding:16px 0">
      <a href="/dashboard" style="display:inline-block;padding:12px 32px;background:linear-gradient(135deg,#6366f1,#06b6d4);color:#fff;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px">View Full Dashboard</a>
    </div>
  </div>
  <div style="padding:16px 24px;background:#f9fafb;text-align:center;font-size:11px;color:#9ca3af;border-top:1px solid #e5e7eb">
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
    user.onboarding_step = 1
    db.commit()
    return {"detail": "Step 1 saved"}


@router.post("/onboarding/step2")
def onboarding_step2(body: OnboardingStep2, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Just save step progress; competitors are created in /complete
    user.onboarding_step = 2
    db.commit()
    return {"detail": "Step 2 saved"}


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

    user.onboarding_step = 3
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
