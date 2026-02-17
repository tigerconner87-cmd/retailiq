import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Alert, DailySnapshot, Customer, Review, Shop

log = logging.getLogger(__name__)


def check_revenue_drop(db: Session, shop: Shop) -> Alert | None:
    """Create alert if this week's revenue is >20% below last week."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start - timedelta(days=1)

    def week_revenue(start: date, end: date) -> float:
        val = db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0)).filter(
            DailySnapshot.shop_id == shop.id,
            DailySnapshot.date >= start,
            DailySnapshot.date <= end,
        ).scalar()
        return float(val)

    this_week = week_revenue(week_start, today)
    last_week = week_revenue(last_week_start, last_week_end)

    if last_week > 0:
        change = (this_week - last_week) / last_week * 100
        if change < -20:
            return Alert(
                shop_id=shop.id,
                alert_type="revenue_drop",
                severity="critical",
                title="Revenue dropped significantly",
                message=f"This week's revenue is down {abs(change):.0f}% compared to last week (${this_week:,.0f} vs ${last_week:,.0f}).",
            )
    return None


def check_negative_review(db: Session, shop: Shop) -> Alert | None:
    """Create alert if there's a recent negative review (<=2 stars)."""
    recent = (
        db.query(Review)
        .filter(
            Review.shop_id == shop.id,
            Review.is_own_shop.is_(True),
            Review.rating <= 2,
            Review.review_date >= date.today() - timedelta(days=1),
        )
        .first()
    )
    if recent:
        return Alert(
            shop_id=shop.id,
            alert_type="negative_review",
            severity="warning",
            title="New negative Google review",
            message=f'"{recent.text[:120]}..." — {recent.author_name}, {recent.rating} stars',
        )
    return None


def check_return_rate_drop(db: Session, shop: Shop) -> Alert | None:
    """Alert if repeat customer rate drops below 25%."""
    total = db.query(func.count(Customer.id)).filter(Customer.shop_id == shop.id).scalar() or 0
    repeat = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop.id, Customer.visit_count > 1
    ).scalar() or 0

    if total > 20:
        rate = repeat / total * 100
        if rate < 25:
            return Alert(
                shop_id=shop.id,
                alert_type="return_rate_drop",
                severity="warning",
                title="Customer return rate is low",
                message=f"Only {rate:.1f}% of your customers are returning. Industry average is 30-40%.",
            )
    return None


def run_alert_checks(db: Session, shop: Shop) -> list[Alert]:
    """Run all alert checks and persist new alerts."""
    checkers = [check_revenue_drop, check_negative_review, check_return_rate_drop]
    new_alerts = []

    for checker in checkers:
        try:
            alert = checker(db, shop)
            if alert:
                # Avoid duplicate alerts on the same day
                existing = db.query(Alert).filter(
                    Alert.shop_id == shop.id,
                    Alert.alert_type == alert.alert_type,
                    func.date(Alert.created_at) == date.today(),
                ).first()
                if not existing:
                    db.add(alert)
                    new_alerts.append(alert)
        except Exception as e:
            log.warning("Alert check %s failed: %s", checker.__name__, e)

    if new_alerts:
        db.commit()

    return new_alerts


def send_alert_email(alert: Alert, recipient_email: str) -> None:
    """Stub: send alert notification email. Replace with real SMTP."""
    log.info(
        "EMAIL STUB — To: %s | Subject: [RetailIQ Alert] %s | Body: %s",
        recipient_email,
        alert.title,
        alert.message,
    )
