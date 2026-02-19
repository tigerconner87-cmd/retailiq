"""Centralized dashboard data service.

Single entry point for all dashboard data queries. Prevents data bugs
by ensuring consistent user → shop → data lookup chain.
"""

from datetime import date, datetime, timedelta
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.models import (
    Shop, Transaction, TransactionItem, Product, Customer,
    DailySnapshot, Review, Competitor, CompetitorReview, Alert,
)


def get_shop_for_user(db: Session, user_id: str) -> Shop | None:
    return db.query(Shop).filter(Shop.user_id == user_id).first()


def get_activity_feed(db: Session, shop_id: str, limit: int = 10) -> list[dict]:
    """Build a real-time activity feed from recent events."""
    events = []
    now = datetime.utcnow()

    # Recent transactions
    recent_txns = (
        db.query(Transaction)
        .filter(Transaction.shop_id == shop_id)
        .order_by(Transaction.timestamp.desc())
        .limit(5)
        .all()
    )
    for tx in recent_txns:
        # Get product name from first item
        item = db.query(TransactionItem).filter(TransactionItem.transaction_id == tx.id).first()
        product_name = ""
        if item:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                product_name = product.name
        customer_name = ""
        if tx.customer_id:
            cust = db.query(Customer).filter(Customer.id == tx.customer_id).first()
            if cust:
                customer_name = cust.email or f"Customer {cust.id[:8]}"

        events.append({
            "type": "sale",
            "icon": "💰",
            "description": f"New sale: ${float(tx.total):,.2f}" + (f" — {product_name}" if product_name else ""),
            "timestamp": tx.timestamp.isoformat(),
            "time_ago": _time_ago(tx.timestamp, now),
        })

        # Returning customer event
        if tx.customer_id and customer_name:
            tx_count = db.query(func.count(Transaction.id)).filter(
                Transaction.customer_id == tx.customer_id,
                Transaction.shop_id == shop_id,
            ).scalar()
            if tx_count and tx_count > 1:
                events.append({
                    "type": "returning_customer",
                    "icon": "👤",
                    "description": f"Returning customer: {customer_name} visited ({tx_count} total visits)",
                    "timestamp": tx.timestamp.isoformat(),
                    "time_ago": _time_ago(tx.timestamp, now),
                })

    # Recent reviews
    recent_reviews = (
        db.query(Review)
        .filter(Review.shop_id == shop_id)
        .order_by(Review.created_at.desc())
        .limit(3)
        .all()
    )
    for rev in recent_reviews:
        stars = "⭐" * (rev.rating or 0)
        events.append({
            "type": "review",
            "icon": "⭐",
            "description": f"New {rev.rating}-star review from {rev.author_name or 'Anonymous'}",
            "timestamp": rev.created_at.isoformat() if rev.created_at else now.isoformat(),
            "time_ago": _time_ago(rev.created_at or now, now),
        })

    # Recent competitor reviews (negative ones = alerts)
    comp_reviews = (
        db.query(CompetitorReview, Competitor.name)
        .join(Competitor, CompetitorReview.competitor_id == Competitor.id)
        .filter(Competitor.shop_id == shop_id)
        .order_by(CompetitorReview.review_date.desc())
        .limit(3)
        .all()
    )
    for cr, comp_name in comp_reviews:
        if cr.rating and cr.rating <= 2:
            events.append({
                "type": "competitor_alert",
                "icon": "🔴",
                "description": f"Competitor alert: {comp_name} got a {cr.rating}-star review",
                "timestamp": cr.review_date.isoformat() if cr.review_date else now.isoformat(),
                "time_ago": _time_ago(cr.review_date or now, now),
            })

    # Sort by timestamp descending and limit
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return events[:limit]


def get_customer_segments(db: Session, shop_id: str) -> dict:
    """Get customer segment breakdown for visualization."""
    customers = db.query(Customer).filter(Customer.shop_id == shop_id).all()
    if not customers:
        return {"segments": [], "total": 0}

    # Calculate segments based on visit count and recency
    now = datetime.utcnow()
    segments = {"vip": [], "regular": [], "at_risk": [], "lost": []}

    for c in customers:
        # Get customer transaction stats
        tx_data = db.query(
            func.count(Transaction.id).label("count"),
            func.sum(Transaction.total).label("revenue"),
            func.max(Transaction.timestamp).label("last_visit"),
        ).filter(
            Transaction.customer_id == c.id,
            Transaction.shop_id == shop_id,
        ).first()

        tx_count = tx_data.count or 0
        revenue = float(tx_data.revenue or 0)
        last_visit = tx_data.last_visit

        days_since = (now - last_visit).days if last_visit else 999

        if tx_count >= 5 and revenue > 500:
            segments["vip"].append({"name": c.email or c.id[:8], "revenue": revenue, "visits": tx_count})
        elif days_since > 90:
            segments["lost"].append({"name": c.email or c.id[:8], "revenue": revenue, "visits": tx_count})
        elif days_since > 45:
            segments["at_risk"].append({"name": c.email or c.id[:8], "revenue": revenue, "visits": tx_count})
        else:
            segments["regular"].append({"name": c.email or c.id[:8], "revenue": revenue, "visits": tx_count})

    result = []
    colors = {"vip": "#f59e0b", "regular": "#10b981", "at_risk": "#f97316", "lost": "#ef4444"}
    labels = {"vip": "VIP", "regular": "Regular", "at_risk": "At-Risk", "lost": "Lost"}

    for key in ["vip", "regular", "at_risk", "lost"]:
        seg = segments[key]
        total_rev = sum(c["revenue"] for c in seg)
        avg_order = total_rev / max(sum(c["visits"] for c in seg), 1)
        result.append({
            "key": key,
            "label": labels[key],
            "color": colors[key],
            "count": len(seg),
            "total_revenue": round(total_rev, 2),
            "avg_order_value": round(avg_order, 2),
        })

    return {
        "segments": result,
        "total": len(customers),
    }


def get_revenue_heatmap(db: Session, shop_id: str, days: int = 90) -> list[dict]:
    """Get daily revenue for heatmap calendar visualization."""
    cutoff = date.today() - timedelta(days=days)
    snapshots = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= cutoff)
        .order_by(DailySnapshot.date)
        .all()
    )
    if not snapshots:
        return []

    max_rev = max(float(s.total_revenue or 0) for s in snapshots) or 1
    return [
        {
            "date": s.date.isoformat(),
            "revenue": round(float(s.total_revenue or 0), 2),
            "intensity": round(float(s.total_revenue or 0) / max_rev, 2),
            "day_of_week": s.date.weekday(),
        }
        for s in snapshots
    ]


def _time_ago(dt, now=None):
    """Convert datetime to relative time string."""
    if not dt:
        return "recently"
    if now is None:
        now = datetime.utcnow()
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, datetime.min.time())
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} min{'s' if m > 1 else ''} ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h > 1 else ''} ago"
    d = seconds // 86400
    return f"{d} day{'s' if d > 1 else ''} ago"
