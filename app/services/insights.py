"""Auto-Insight Generator — produces natural language insights from analytics data."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.models import (
    Transaction, TransactionItem, Product, Customer,
    DailySnapshot, Competitor, CompetitorReview, Review,
)


def _ref_date(db: Session, shop_id: str) -> date:
    """Return the latest date with transaction data."""
    latest = db.query(func.max(func.date(Transaction.timestamp))).filter(
        Transaction.shop_id == shop_id,
    ).scalar()
    return latest or date.today()


def generate_insights(db: Session, shop_id: str) -> list[dict]:
    """Generate all insight categories and return a flat list."""
    ref = _ref_date(db, shop_id)
    insights = []
    insights.extend(_revenue_insights(db, shop_id, ref))
    insights.extend(_product_insights(db, shop_id, ref))
    insights.extend(_customer_insights(db, shop_id, ref))
    insights.extend(_competitor_insights(db, shop_id))
    insights.extend(_trend_insights(db, shop_id, ref))
    return insights


def _revenue_insights(db: Session, shop_id: str, ref: date) -> list[dict]:
    """Revenue-related insights."""
    results = []
    month_start = ref.replace(day=1)

    # Best and worst day this month
    days = (
        db.query(
            DailySnapshot.date,
            DailySnapshot.total_revenue,
        )
        .filter(
            DailySnapshot.shop_id == shop_id,
            DailySnapshot.date >= month_start,
            DailySnapshot.date <= ref,
        )
        .order_by(DailySnapshot.total_revenue.desc())
        .all()
    )
    if len(days) >= 2:
        best = days[0]
        worst = days[-1]
        results.append({
            "category": "revenue",
            "icon": "1F4B0",
            "title": "Best & Worst Days",
            "text": f"Your best day this month was {best.date.strftime('%b %d')} (${float(best.total_revenue):,.0f}). "
                    f"Your worst was {worst.date.strftime('%b %d')} (${float(worst.total_revenue):,.0f}).",
            "priority": "medium",
        })

    # Week-over-week trend
    this_week_start = ref - timedelta(days=ref.weekday())
    last_week_start = this_week_start - timedelta(days=7)
    this_week_rev = db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0)).filter(
        DailySnapshot.shop_id == shop_id,
        DailySnapshot.date >= this_week_start,
        DailySnapshot.date <= ref,
    ).scalar()
    last_week_rev = db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0)).filter(
        DailySnapshot.shop_id == shop_id,
        DailySnapshot.date >= last_week_start,
        DailySnapshot.date < this_week_start,
    ).scalar()
    tw = float(this_week_rev)
    lw = float(last_week_rev)
    if lw > 0:
        pct = round((tw - lw) / lw * 100, 1)
        direction = "up" if pct > 0 else "down"
        results.append({
            "category": "revenue",
            "icon": "1F4C8" if pct > 0 else "1F4C9",
            "title": "Weekly Trend",
            "text": f"Revenue is {direction} {abs(pct)}% this week compared to last week (${tw:,.0f} vs ${lw:,.0f}).",
            "priority": "high" if abs(pct) > 15 else "medium",
        })

    return results


def _product_insights(db: Session, shop_id: str, ref: date) -> list[dict]:
    """Product-related insights."""
    results = []
    week_ago = ref - timedelta(days=7)
    two_weeks_ago = ref - timedelta(days=14)

    # Top growing product this week vs last week
    this_week = (
        db.query(
            Product.name,
            func.sum(TransactionItem.quantity).label("qty"),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(
            Transaction.shop_id == shop_id,
            func.date(Transaction.timestamp) >= week_ago,
            func.date(Transaction.timestamp) <= ref,
        )
        .group_by(Product.name)
        .all()
    )
    last_week = (
        db.query(
            Product.name,
            func.sum(TransactionItem.quantity).label("qty"),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(
            Transaction.shop_id == shop_id,
            func.date(Transaction.timestamp) >= two_weeks_ago,
            func.date(Transaction.timestamp) < week_ago,
        )
        .group_by(Product.name)
        .all()
    )

    tw_map = {r.name: int(r.qty) for r in this_week}
    lw_map = {r.name: int(r.qty) for r in last_week}

    growth_items = []
    decline_items = []
    for name, qty in tw_map.items():
        prev = lw_map.get(name, 0)
        if prev > 0:
            change = round((qty - prev) / prev * 100, 1)
            if change > 20:
                growth_items.append((name, change))
            elif change < -20:
                decline_items.append((name, change))

    growth_items.sort(key=lambda x: x[1], reverse=True)
    decline_items.sort(key=lambda x: x[1])

    if growth_items:
        name, pct = growth_items[0]
        results.append({
            "category": "products",
            "icon": "1F680",
            "title": "Hot Product",
            "text": f"{name} sales jumped {pct}% this week. Consider featuring it more prominently.",
            "priority": "high",
        })

    if decline_items:
        name, pct = decline_items[0]
        results.append({
            "category": "products",
            "icon": "26A0",
            "title": "Slowing Product",
            "text": f"{name} is down {abs(pct)}% this week. Consider a promotion or markdown.",
            "priority": "medium",
        })

    return results


def _customer_insights(db: Session, shop_id: str, ref: date) -> list[dict]:
    """Customer-related insights."""
    results = []
    week_ago = datetime.combine(ref - timedelta(days=7), datetime.min.time())

    new_custs = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        Customer.first_seen >= week_ago,
    ).scalar() or 0

    at_risk = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        Customer.segment == "at_risk",
    ).scalar() or 0

    lost = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        Customer.segment == "lost",
    ).scalar() or 0

    if new_custs > 0 or at_risk > 0:
        results.append({
            "category": "customers",
            "icon": "1F465",
            "title": "Customer Movement",
            "text": f"You gained {new_custs} new customers this week but {at_risk + lost} are at risk of leaving.",
            "priority": "high" if at_risk > 10 else "medium",
        })

    vip_count = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        Customer.segment == "vip",
    ).scalar() or 0
    total = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
    ).scalar() or 1

    if vip_count > 0:
        pct = round(vip_count / total * 100, 1)
        results.append({
            "category": "customers",
            "icon": "2B50",
            "title": "VIP Customers",
            "text": f"Your {vip_count} VIP customers ({pct}% of total) drive a disproportionate share of revenue. Prioritize their experience.",
            "priority": "low",
        })

    return results


def _competitor_insights(db: Session, shop_id: str) -> list[dict]:
    """Competitor-related insights."""
    results = []
    comps = db.query(Competitor).filter(Competitor.shop_id == shop_id).all()

    for comp in comps:
        if comp.rating and float(comp.rating) < 3.5:
            results.append({
                "category": "competitors",
                "icon": "1F50D",
                "title": f"{comp.name} Struggling",
                "text": f"{comp.name}'s rating is {float(comp.rating):.1f}/5. Their customers might be looking for alternatives — that's your opportunity.",
                "priority": "high",
            })
            break  # Only report the most notable

    # Check for recent negative competitor reviews
    week_ago = datetime.utcnow() - timedelta(days=7)
    for comp in comps[:3]:
        neg_count = db.query(func.count(CompetitorReview.id)).filter(
            CompetitorReview.competitor_id == comp.id,
            CompetitorReview.sentiment == "negative",
            CompetitorReview.created_at >= week_ago,
        ).scalar() or 0
        if neg_count >= 3:
            results.append({
                "category": "competitors",
                "icon": "1F4A1",
                "title": f"Opportunity: {comp.name}",
                "text": f"{comp.name} received {neg_count} negative reviews this week. Run a targeted ad campaign to attract their dissatisfied customers.",
                "priority": "high",
            })
            break

    return results


def _trend_insights(db: Session, shop_id: str, ref: date) -> list[dict]:
    """Trend-based insights (weekday vs weekend, seasonal)."""
    results = []

    # Weekend vs weekday revenue
    last_30 = ref - timedelta(days=30)
    snapshots = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(
            DailySnapshot.shop_id == shop_id,
            DailySnapshot.date >= last_30,
            DailySnapshot.date <= ref,
        )
        .all()
    )

    weekend_rev = []
    weekday_rev = []
    for snap in snapshots:
        rev = float(snap.total_revenue)
        if snap.date.weekday() >= 5:
            weekend_rev.append(rev)
        else:
            weekday_rev.append(rev)

    if weekend_rev and weekday_rev:
        avg_weekend = sum(weekend_rev) / len(weekend_rev)
        avg_weekday = sum(weekday_rev) / len(weekday_rev)
        if avg_weekday > 0:
            ratio = round(avg_weekend / avg_weekday, 1)
            if ratio > 1.3:
                results.append({
                    "category": "trends",
                    "icon": "1F4CA",
                    "title": "Weekend Boost",
                    "text": f"Weekends generate {ratio}x more revenue than weekdays for you. Focus staffing and inventory for Saturday-Sunday peaks.",
                    "priority": "medium",
                })

    # Best day of week
    day_totals = {}
    day_counts = {}
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for snap in snapshots:
        dow = snap.date.weekday()
        day_totals[dow] = day_totals.get(dow, 0) + float(snap.total_revenue)
        day_counts[dow] = day_counts.get(dow, 0) + 1

    if day_totals:
        best_dow = max(day_totals, key=lambda k: day_totals[k] / max(day_counts.get(k, 1), 1))
        avg_best = day_totals[best_dow] / day_counts.get(best_dow, 1)
        results.append({
            "category": "trends",
            "icon": "1F4C5",
            "title": "Best Day",
            "text": f"{day_names[best_dow]} is your strongest day, averaging ${avg_best:,.0f} in revenue.",
            "priority": "low",
        })

    return results


def get_sparkline_data(db: Session, shop_id: str, days: int = 7) -> list[float]:
    """Return last N days of revenue for sparkline rendering."""
    ref = _ref_date(db, shop_id)
    start = ref - timedelta(days=days - 1)
    rows = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(
            DailySnapshot.shop_id == shop_id,
            DailySnapshot.date >= start,
            DailySnapshot.date <= ref,
        )
        .order_by(DailySnapshot.date)
        .all()
    )
    return [float(r.total_revenue) for r in rows]
