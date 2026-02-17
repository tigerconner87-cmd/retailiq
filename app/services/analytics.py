from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, case, extract, and_
from sqlalchemy.orm import Session

from app.models import (
    Transaction, TransactionItem, Product, Customer,
    DailySnapshot, HourlySnapshot, Shop, Review,
)


def _today() -> date:
    return date.today()


def get_shop_for_user(db: Session, user_id: str) -> Shop | None:
    return db.query(Shop).filter(Shop.user_id == user_id).first()


# ── Summary KPIs ──────────────────────────────────────────────────────────────

def get_summary(db: Session, shop_id: str) -> dict:
    today = _today()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start - timedelta(days=1)

    def revenue_for_date(d: date) -> float:
        row = db.query(func.coalesce(func.sum(Transaction.total), 0)).filter(
            Transaction.shop_id == shop_id,
            func.date(Transaction.timestamp) == d,
        ).scalar()
        return float(row)

    def revenue_for_range(start: date, end: date) -> float:
        row = db.query(func.coalesce(func.sum(Transaction.total), 0)).filter(
            Transaction.shop_id == shop_id,
            func.date(Transaction.timestamp) >= start,
            func.date(Transaction.timestamp) <= end,
        ).scalar()
        return float(row)

    def tx_count_for_date(d: date) -> int:
        return db.query(func.count(Transaction.id)).filter(
            Transaction.shop_id == shop_id,
            func.date(Transaction.timestamp) == d,
        ).scalar() or 0

    rev_today = revenue_for_date(today)
    rev_yesterday = revenue_for_date(yesterday)
    rev_this_week = revenue_for_range(week_start, today)
    rev_last_week = revenue_for_range(last_week_start, last_week_end)
    tx_today = tx_count_for_date(today)

    avg_ov = round(rev_today / tx_today, 2) if tx_today > 0 else 0.0

    total_customers = db.query(func.count(Customer.id)).filter(Customer.shop_id == shop_id).scalar() or 0
    repeat_customers = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 1
    ).scalar() or 0
    repeat_rate = round(repeat_customers / total_customers * 100, 1) if total_customers > 0 else 0.0

    thirty_days_ago = today - timedelta(days=30)
    new_today = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        func.date(Customer.first_seen) == today,
    ).scalar() or 0

    dod = round((rev_today - rev_yesterday) / rev_yesterday * 100, 1) if rev_yesterday > 0 else 0.0
    wow = round((rev_this_week - rev_last_week) / rev_last_week * 100, 1) if rev_last_week > 0 else 0.0

    return {
        "revenue_today": rev_today,
        "revenue_yesterday": rev_yesterday,
        "revenue_this_week": rev_this_week,
        "revenue_last_week": rev_last_week,
        "transactions_today": tx_today,
        "avg_order_value": avg_ov,
        "repeat_customer_rate": repeat_rate,
        "revenue_change_dod": dod,
        "revenue_change_wow": wow,
        "total_customers": total_customers,
        "new_customers_today": new_today,
    }


# ── Sales Trends ──────────────────────────────────────────────────────────────

def get_sales_trends(db: Session, shop_id: str, days: int = 30) -> dict:
    end = _today()
    start = end - timedelta(days=days)

    rows = (
        db.query(
            DailySnapshot.date,
            DailySnapshot.total_revenue,
            DailySnapshot.transaction_count,
        )
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= start)
        .order_by(DailySnapshot.date)
        .all()
    )

    daily = [
        {"date": r.date.isoformat(), "revenue": float(r.total_revenue), "transactions": r.transaction_count}
        for r in rows
    ]

    # Weekly aggregation
    weekly: dict[str, dict] = {}
    for r in rows:
        wk = r.date - timedelta(days=r.date.weekday())
        key = wk.isoformat()
        if key not in weekly:
            weekly[key] = {"week_start": key, "revenue": 0.0, "transactions": 0}
        weekly[key]["revenue"] += float(r.total_revenue)
        weekly[key]["transactions"] += r.transaction_count

    # Monthly aggregation
    monthly: dict[str, dict] = {}
    for r in rows:
        key = r.date.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = {"month": key, "revenue": 0.0, "transactions": 0}
        monthly[key]["revenue"] += float(r.total_revenue)
        monthly[key]["transactions"] += r.transaction_count

    return {
        "daily": daily,
        "weekly_totals": list(weekly.values()),
        "monthly_totals": list(monthly.values()),
    }


# ── Peak Hours Heatmap ────────────────────────────────────────────────────────

def get_peak_hours(db: Session, shop_id: str, days: int = 30) -> list[dict]:
    start = _today() - timedelta(days=days)

    rows = (
        db.query(
            HourlySnapshot.date,
            HourlySnapshot.hour,
            HourlySnapshot.revenue,
        )
        .filter(HourlySnapshot.shop_id == shop_id, HourlySnapshot.date >= start)
        .all()
    )

    # Aggregate by (day_of_week, hour)
    grid: dict[tuple[int, int], list[float]] = {}
    for r in rows:
        dow = r.date.weekday()
        key = (dow, r.hour)
        grid.setdefault(key, []).append(float(r.revenue))

    return [
        {"day": k[0], "hour": k[1], "value": round(sum(v) / len(v), 2)}
        for k, v in sorted(grid.items())
    ]


# ── Product Rankings ──────────────────────────────────────────────────────────

def get_product_rankings(db: Session, shop_id: str, days: int = 30) -> dict:
    start = _today() - timedelta(days=days)

    rows = (
        db.query(
            Product.id,
            Product.name,
            Product.category,
            Product.price,
            Product.cost,
            func.coalesce(func.sum(TransactionItem.total), 0).label("revenue"),
            func.coalesce(func.sum(TransactionItem.quantity), 0).label("units"),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(
            Product.shop_id == shop_id,
            Transaction.timestamp >= datetime.combine(start, datetime.min.time()),
        )
        .group_by(Product.id, Product.name, Product.category, Product.price, Product.cost)
        .order_by(func.sum(TransactionItem.total).desc())
        .limit(20)
        .all()
    )

    products = []
    for r in rows:
        margin = None
        if r.cost and r.cost > 0:
            margin = round(float(r.price - r.cost) / float(r.price) * 100, 1)
        products.append({
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "revenue": float(r.revenue),
            "units_sold": int(r.units),
            "avg_price": float(r.price),
            "margin": margin,
        })

    total = db.query(func.count(Product.id)).filter(Product.shop_id == shop_id).scalar() or 0

    return {"top_products": products, "total_products": total}


# ── Customer Analytics ────────────────────────────────────────────────────────

def get_customer_metrics(db: Session, shop_id: str) -> dict:
    total = db.query(func.count(Customer.id)).filter(Customer.shop_id == shop_id).scalar() or 0
    repeat = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 1
    ).scalar() or 0

    thirty_days_ago = _today() - timedelta(days=30)
    new_30d = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        func.date(Customer.first_seen) >= thirty_days_ago,
    ).scalar() or 0

    repeat_rate = round(repeat / total * 100, 1) if total > 0 else 0.0

    avg_rev = db.query(func.avg(Customer.total_spent)).filter(
        Customer.shop_id == shop_id
    ).scalar()
    avg_rev = round(float(avg_rev), 2) if avg_rev else 0.0

    avg_visits = db.query(func.avg(Customer.visit_count)).filter(
        Customer.shop_id == shop_id
    ).scalar()
    avg_visits = round(float(avg_visits), 1) if avg_visits else 0.0

    top = (
        db.query(Customer)
        .filter(Customer.shop_id == shop_id)
        .order_by(Customer.total_spent.desc())
        .limit(10)
        .all()
    )
    top_list = [
        {
            "id": c.id,
            "visit_count": c.visit_count,
            "total_spent": float(c.total_spent),
            "last_seen": c.last_seen.isoformat() if c.last_seen else None,
        }
        for c in top
    ]

    return {
        "total_customers": total,
        "repeat_customers": repeat,
        "new_customers_30d": new_30d,
        "repeat_rate": repeat_rate,
        "avg_revenue_per_customer": avg_rev,
        "avg_visits_per_customer": avg_visits,
        "top_customers": top_list,
    }


# ── AI Action Items ───────────────────────────────────────────────────────────

def get_ai_actions(db: Session, shop_id: str) -> list[dict]:
    today = _today()
    actions = []

    # 1. Trending product — compare last 7d vs prior 7d
    week_ago = today - timedelta(days=7)
    two_weeks_ago = today - timedelta(days=14)

    this_week_products = (
        db.query(
            Product.name,
            func.coalesce(func.sum(TransactionItem.total), 0).label("rev"),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(Product.shop_id == shop_id, func.date(Transaction.timestamp) >= week_ago)
        .group_by(Product.name)
        .all()
    )
    last_week_products = dict(
        db.query(
            Product.name,
            func.coalesce(func.sum(TransactionItem.total), 0),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(
            Product.shop_id == shop_id,
            func.date(Transaction.timestamp) >= two_weeks_ago,
            func.date(Transaction.timestamp) < week_ago,
        )
        .group_by(Product.name)
        .all()
    )

    best_growth_name, best_growth_pct = None, 0
    for row in this_week_products:
        prev = float(last_week_products.get(row.name, 0))
        curr = float(row.rev)
        if prev > 50:
            pct = (curr - prev) / prev * 100
            if pct > best_growth_pct:
                best_growth_pct = pct
                best_growth_name = row.name

    if best_growth_name and best_growth_pct > 15:
        actions.append({
            "type": "product",
            "priority": "high",
            "emoji": "1f4c8",
            "title": f"{best_growth_name} sales are up {best_growth_pct:.0f}% this week",
            "description": f"Feature this product in your window display and social media to ride the momentum.",
        })

    # 2. Lapsed customers — repeat visitors not seen in 30+ days
    thirty_ago = datetime.combine(today - timedelta(days=30), datetime.min.time())
    lapsed = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        Customer.visit_count > 1,
        Customer.last_seen < thirty_ago,
    ).scalar() or 0

    if lapsed > 0:
        actions.append({
            "type": "retention",
            "priority": "high",
            "emoji": "1f4e9",
            "title": f"{lapsed} repeat customers haven't returned in 30+ days",
            "description": "Send a personalized win-back email with a 15% discount code to re-engage them.",
        })

    # 3. Weakest day of week — suggest a promotion
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    recent_snaps = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= today - timedelta(days=28))
        .all()
    )
    day_totals: dict[int, list[float]] = {}
    for snap in recent_snaps:
        dow = snap.date.weekday()
        day_totals.setdefault(dow, []).append(float(snap.total_revenue))

    if day_totals:
        weakest_dow = min(day_totals, key=lambda d: sum(day_totals[d]) / len(day_totals[d]))
        weakest_avg = sum(day_totals[weakest_dow]) / len(day_totals[weakest_dow])
        overall_avg = sum(sum(v) for v in day_totals.values()) / sum(len(v) for v in day_totals.values())
        if weakest_avg < overall_avg * 0.85:
            actions.append({
                "type": "revenue",
                "priority": "medium",
                "emoji": "1f4b0",
                "title": f"{day_names[weakest_dow]} is your weakest day (${weakest_avg:,.0f} avg)",
                "description": f"That's {((overall_avg - weakest_avg) / overall_avg * 100):.0f}% below your daily average. Try a {day_names[weakest_dow]}-only promotion to boost traffic.",
            })

    # 4. Peak hour staffing
    peak_snaps = (
        db.query(
            HourlySnapshot.hour,
            func.avg(HourlySnapshot.revenue).label("avg_rev"),
        )
        .filter(HourlySnapshot.shop_id == shop_id, HourlySnapshot.date >= today - timedelta(days=14))
        .group_by(HourlySnapshot.hour)
        .order_by(func.avg(HourlySnapshot.revenue).desc())
        .first()
    )
    if peak_snaps:
        h = peak_snaps.hour
        label = f"{h % 12 or 12}{'pm' if h >= 12 else 'am'}"
        actions.append({
            "type": "operations",
            "priority": "medium",
            "emoji": "23f0",
            "title": f"Your peak hour is {label} — make sure you're fully staffed",
            "description": f"Average revenue at {label} is ${float(peak_snaps.avg_rev):,.0f}. Ensure your best salespeople are on the floor.",
        })

    # 5. Review gap
    neg_reviews = db.query(func.count(Review.id)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True), Review.rating <= 2,
    ).scalar() or 0
    total_reviews = db.query(func.count(Review.id)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True),
    ).scalar() or 0

    if total_reviews > 0 and neg_reviews / total_reviews > 0.15:
        actions.append({
            "type": "reviews",
            "priority": "high",
            "emoji": "2b50",
            "title": f"{neg_reviews} negative reviews detected — respond promptly",
            "description": "Replying to negative reviews within 24 hours can improve your rating by up to 0.3 stars on average.",
        })

    return actions[:5]
