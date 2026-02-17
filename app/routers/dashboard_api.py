from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User, Alert
from app.schemas import (
    AlertsResponse,
    CompetitorsResponse,
    CustomerMetrics,
    ProductsResponse,
    ReviewsResponse,
    SalesResponse,
    SummaryResponse,
)
from app.services.analytics import (
    get_ai_actions,
    get_customer_metrics,
    get_peak_hours,
    get_product_rankings,
    get_sales_trends,
    get_shop_for_user,
    get_summary,
)
from app.services.reviews import get_competitors_summary, get_reviews_summary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _get_shop(db: Session, user: User):
    shop = get_shop_for_user(db, user.id)
    if not shop:
        raise HTTPException(status_code=404, detail="No shop found for this user")
    return shop


@router.get("/summary", response_model=SummaryResponse)
def dashboard_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_summary(db, shop.id)


@router.get("/sales", response_model=SalesResponse)
def dashboard_sales(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_sales_trends(db, shop.id, days=days)


@router.get("/peak-hours")
def dashboard_peak_hours(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_peak_hours(db, shop.id, days=days)


@router.get("/products", response_model=ProductsResponse)
def dashboard_products(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_product_rankings(db, shop.id, days=days)


@router.get("/customers", response_model=CustomerMetrics)
def dashboard_customers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_customer_metrics(db, shop.id)


@router.get("/competitors", response_model=CompetitorsResponse)
def dashboard_competitors(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_competitors_summary(db, shop.id)


@router.get("/reviews", response_model=ReviewsResponse)
def dashboard_reviews(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_reviews_summary(db, shop.id)


@router.get("/ai-actions")
def dashboard_ai_actions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    return get_ai_actions(db, shop.id)


@router.get("/alerts", response_model=AlertsResponse)
def dashboard_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = _get_shop(db, user)
    alerts = (
        db.query(Alert)
        .filter(Alert.shop_id == shop.id)
        .order_by(Alert.created_at.desc())
        .limit(50)
        .all()
    )
    unread = sum(1 for a in alerts if not a.is_read)
    return AlertsResponse(
        alerts=[
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "title": a.title,
                "message": a.message,
                "is_read": a.is_read,
                "created_at": a.created_at,
            }
            for a in alerts
        ],
        unread_count=unread,
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
