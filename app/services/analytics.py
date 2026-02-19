"""Advanced analytics engine for Forge.

Provides: summary KPIs, sales trends, peak hours, product rankings, customer metrics,
forecasting, anomaly detection, cohort analysis, RFM scoring, CLV, churn prediction,
seasonality, break-even analysis, and more.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from collections import defaultdict
import math
import random
import statistics

from sqlalchemy import func, case, and_, extract
from sqlalchemy.orm import Session

from app.models import (
    Transaction, TransactionItem, Product, Customer,
    DailySnapshot, HourlySnapshot, Shop, Review, Expense,
    RevenueGoal, ShopSettings,
)


def _today() -> date:
    return date.today()


def get_shop_for_user(db: Session, user_id: str) -> Shop | None:
    return db.query(Shop).filter(Shop.user_id == user_id).first()


# ── Summary KPIs ──────────────────────────────────────────────────────────────

def get_summary(db: Session, shop_id: str) -> dict:
    actual_today = _today()

    # Check if there's data for today; if not, use the most recent date with data
    rev_check = db.query(func.coalesce(func.sum(Transaction.total), 0)).filter(
        Transaction.shop_id == shop_id,
        func.date(Transaction.timestamp) == actual_today,
    ).scalar()

    today = actual_today
    data_is_stale = False
    if float(rev_check) == 0:
        latest_date = db.query(func.max(func.date(Transaction.timestamp))).filter(
            Transaction.shop_id == shop_id,
        ).scalar()
        if latest_date:
            today = latest_date
            data_is_stale = True

    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start - timedelta(days=1)
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    year_start = today.replace(month=1, day=1)

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
    rev_this_month = revenue_for_range(month_start, today)
    rev_last_month = revenue_for_range(last_month_start, last_month_end)
    rev_this_year = revenue_for_range(year_start, today)
    tx_today = tx_count_for_date(today)

    avg_ov = round(rev_today / tx_today, 2) if tx_today > 0 else 0.0

    # Items per transaction today
    items_today = db.query(func.coalesce(func.sum(Transaction.items_count), 0)).filter(
        Transaction.shop_id == shop_id,
        func.date(Transaction.timestamp) == today,
    ).scalar()
    items_per_tx = round(float(items_today) / tx_today, 1) if tx_today > 0 else 0.0

    total_customers = db.query(func.count(Customer.id)).filter(Customer.shop_id == shop_id).scalar() or 0
    repeat_customers = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 1
    ).scalar() or 0
    repeat_rate = round(repeat_customers / total_customers * 100, 1) if total_customers > 0 else 0.0

    new_today = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        func.date(Customer.first_seen) == today,
    ).scalar() or 0

    dod = round((rev_today - rev_yesterday) / rev_yesterday * 100, 1) if rev_yesterday > 0 else 0.0
    wow = round((rev_this_week - rev_last_week) / rev_last_week * 100, 1) if rev_last_week > 0 else 0.0
    mom = round((rev_this_month - rev_last_month) / rev_last_month * 100, 1) if rev_last_month > 0 else 0.0

    # Estimated profit (revenue - estimated COGS)
    shop_settings = db.query(ShopSettings).filter(ShopSettings.shop_id == shop_id).first()
    cogs_pct = shop_settings.avg_cogs_percentage / 100 if shop_settings else 0.38
    estimated_profit = round(rev_today * (1 - cogs_pct), 2)

    # Foot traffic estimate (~1.4x transactions)
    foot_traffic = int(tx_today * 1.4)

    return {
        "revenue_today": rev_today,
        "revenue_yesterday": rev_yesterday,
        "revenue_this_week": rev_this_week,
        "revenue_last_week": rev_last_week,
        "revenue_this_month": rev_this_month,
        "revenue_last_month": rev_last_month,
        "revenue_this_year": rev_this_year,
        "transactions_today": tx_today,
        "avg_order_value": avg_ov,
        "items_per_transaction": items_per_tx,
        "repeat_customer_rate": repeat_rate,
        "revenue_change_dod": dod,
        "revenue_change_wow": wow,
        "revenue_change_mom": mom,
        "total_customers": total_customers,
        "new_customers_today": new_today,
        "estimated_profit_today": estimated_profit,
        "daily_foot_traffic_estimate": foot_traffic,
        "has_data": total_customers > 0 or rev_today > 0,
        "effective_date": today.isoformat(),
        "data_is_stale": data_is_stale,
    }


# ── Sales Trends ──────────────────────────────────────────────────────────────

def get_sales_trends(db: Session, shop_id: str, days: int = 30) -> dict:
    end = _today()
    # If no DailySnapshot data near today, use the latest available date
    latest_snap = db.query(func.max(DailySnapshot.date)).filter(
        DailySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < end - timedelta(days=1):
        end = latest_snap
    start = end - timedelta(days=days)

    rows = (
        db.query(
            DailySnapshot.date,
            DailySnapshot.total_revenue,
            DailySnapshot.transaction_count,
            DailySnapshot.avg_transaction_value,
        )
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= start)
        .order_by(DailySnapshot.date)
        .all()
    )

    daily = [
        {
            "date": r.date.isoformat(),
            "revenue": float(r.total_revenue),
            "transactions": r.transaction_count,
            "avg_value": float(r.avg_transaction_value),
        }
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


# ── Sales Velocity & Stats ───────────────────────────────────────────────────

def get_sales_velocity(db: Session, shop_id: str) -> dict:
    today = _today()
    latest_snap = db.query(func.max(DailySnapshot.date)).filter(
        DailySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < today - timedelta(days=1):
        today = latest_snap
    start = today - timedelta(days=180)

    # Hourly averages
    hourly = (
        db.query(
            HourlySnapshot.hour,
            func.avg(HourlySnapshot.revenue).label("avg_rev"),
            func.avg(HourlySnapshot.transaction_count).label("avg_tx"),
        )
        .filter(HourlySnapshot.shop_id == shop_id, HourlySnapshot.date >= start)
        .group_by(HourlySnapshot.hour)
        .order_by(HourlySnapshot.hour)
        .all()
    )
    hourly_avg = [{"hour": h.hour, "avg_revenue": round(float(h.avg_rev), 2), "avg_transactions": round(float(h.avg_tx), 1)} for h in hourly]

    # Daily averages (by day of week)
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    snaps = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue, DailySnapshot.transaction_count)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= start)
        .all()
    )
    day_totals: dict[int, list] = defaultdict(list)
    all_days = []
    for s in snaps:
        day_totals[s.date.weekday()].append(float(s.total_revenue))
        all_days.append({"date": s.date.isoformat(), "revenue": float(s.total_revenue), "transactions": s.transaction_count})

    daily_avg = [
        {"day": day_names[d], "avg_revenue": round(statistics.mean(vals), 2) if vals else 0, "count": len(vals)}
        for d, vals in sorted(day_totals.items())
    ]

    # Best and worst days
    if all_days:
        best = max(all_days, key=lambda x: x["revenue"])
        worst = min(all_days, key=lambda x: x["revenue"])
    else:
        best = worst = {"date": "", "revenue": 0, "transactions": 0}

    # Year-over-year growth
    yoy = None
    one_year_ago = today - timedelta(days=365)
    this_year_30d = _revenue_range(db, shop_id, today - timedelta(days=30), today)
    last_year_30d = _revenue_range(db, shop_id, one_year_ago - timedelta(days=30), one_year_ago)
    if last_year_30d > 0:
        yoy = round((this_year_30d - last_year_30d) / last_year_30d * 100, 1)

    # Seasonality index
    month_avgs: dict[int, list] = defaultdict(list)
    for s in snaps:
        month_avgs[s.date.month].append(float(s.total_revenue))
    overall_avg = statistics.mean([float(s.total_revenue) for s in snaps]) if snaps else 1
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    seasonality = []
    for m in range(1, 13):
        if month_avgs[m]:
            idx = round(statistics.mean(month_avgs[m]) / overall_avg, 2) if overall_avg > 0 else 1.0
            seasonality.append({"month": month_names[m - 1], "index": idx})

    return {
        "hourly_avg": hourly_avg,
        "daily_avg": daily_avg,
        "best_day_ever": best,
        "worst_day_ever": worst,
        "yoy_growth_rate": yoy,
        "seasonality_index": seasonality,
    }


def _revenue_range(db: Session, shop_id: str, start: date, end: date) -> float:
    row = db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0)).filter(
        DailySnapshot.shop_id == shop_id,
        DailySnapshot.date >= start,
        DailySnapshot.date <= end,
    ).scalar()
    return float(row)


# ── Revenue Forecasting ──────────────────────────────────────────────────────

def get_forecast(db: Session, shop_id: str) -> dict:
    today = _today()
    latest_snap = db.query(func.max(DailySnapshot.date)).filter(
        DailySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < today - timedelta(days=1):
        today = latest_snap
    start = today - timedelta(days=90)

    rows = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= start)
        .order_by(DailySnapshot.date)
        .all()
    )

    if len(rows) < 14:
        return {"forecast_7d": [], "forecast_30d": [], "model_confidence": 0}

    # Simple linear regression
    revenues = [float(r.total_revenue) for r in rows]
    n = len(revenues)
    x = list(range(n))
    x_mean = statistics.mean(x)
    y_mean = statistics.mean(revenues)

    numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, revenues))
    denominator = sum((xi - x_mean) ** 2 for xi in x)
    slope = numerator / denominator if denominator != 0 else 0
    intercept = y_mean - slope * x_mean

    # Calculate R-squared for confidence
    y_pred = [slope * xi + intercept for xi in x]
    ss_res = sum((yi - yp) ** 2 for yi, yp in zip(revenues, y_pred))
    ss_tot = sum((yi - y_mean) ** 2 for yi in revenues)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    # Standard error for prediction intervals
    std_err = math.sqrt(ss_res / (n - 2)) if n > 2 else 0

    # Day-of-week adjustment
    dow_avgs: dict[int, list] = defaultdict(list)
    for r in rows:
        dow_avgs[r.date.weekday()].append(float(r.total_revenue))
    overall_daily_avg = statistics.mean(revenues)
    dow_factors = {}
    for dow, vals in dow_avgs.items():
        dow_factors[dow] = statistics.mean(vals) / overall_daily_avg if overall_daily_avg > 0 else 1.0

    def forecast_day(days_ahead: int) -> dict:
        future_x = n + days_ahead
        base = slope * future_x + intercept
        future_date = today + timedelta(days=days_ahead + 1)
        dow_adj = dow_factors.get(future_date.weekday(), 1.0)
        predicted = max(0, base * dow_adj)
        margin = std_err * 1.96
        return {
            "date": future_date.isoformat(),
            "predicted_revenue": round(predicted, 2),
            "lower_bound": round(max(0, predicted - margin), 2),
            "upper_bound": round(predicted + margin, 2),
        }

    forecast_7d = [forecast_day(i) for i in range(7)]
    forecast_30d = [forecast_day(i) for i in range(30)]

    return {
        "forecast_7d": forecast_7d,
        "forecast_30d": forecast_30d,
        "model_confidence": round(max(0, r_squared), 3),
    }


# ── Goal Tracking ────────────────────────────────────────────────────────────

def get_goal_progress(db: Session, shop_id: str) -> dict | None:
    today = _today()
    latest_snap = db.query(func.max(DailySnapshot.date)).filter(
        DailySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < today - timedelta(days=1):
        today = latest_snap
    current_month = today.strftime("%Y-%m")

    goal = db.query(RevenueGoal).filter(
        RevenueGoal.shop_id == shop_id,
        RevenueGoal.month == current_month,
    ).first()

    if not goal:
        return None

    month_start = today.replace(day=1)
    current_rev = _revenue_range(db, shop_id, month_start, today)
    target = float(goal.target_amount)
    pct = round(current_rev / target * 100, 1) if target > 0 else 0

    # Days remaining
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    days_left = (next_month - today).days
    remaining = target - current_rev
    daily_needed = round(remaining / days_left, 2) if days_left > 0 else 0

    return {
        "month": current_month,
        "target": target,
        "current": round(current_rev, 2),
        "percentage": pct,
        "daily_needed": max(0, daily_needed),
        "days_remaining": days_left,
        "on_track": pct >= (today.day / next_month.day * 100) if next_month.day > 0 else False,
    }


# ── Peak Hours Heatmap ────────────────────────────────────────────────────────

def get_peak_hours(db: Session, shop_id: str, days: int = 30) -> list[dict]:
    end = _today()
    # If no HourlySnapshot data near today, use the latest available date
    latest_snap = db.query(func.max(HourlySnapshot.date)).filter(
        HourlySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < end - timedelta(days=1):
        end = latest_snap
    start = end - timedelta(days=days)

    rows = (
        db.query(
            HourlySnapshot.date,
            HourlySnapshot.hour,
            HourlySnapshot.revenue,
        )
        .filter(HourlySnapshot.shop_id == shop_id, HourlySnapshot.date >= start)
        .all()
    )

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
    today = _today()
    # If no transaction data near today, use the latest available date
    latest_tx = db.query(func.max(func.date(Transaction.timestamp))).filter(
        Transaction.shop_id == shop_id,
    ).scalar()
    if latest_tx and latest_tx < today - timedelta(days=1):
        today = latest_tx
    start = today - timedelta(days=days)
    prev_start = start - timedelta(days=days)
    start_dt = datetime.combine(start, datetime.min.time())
    prev_start_dt = datetime.combine(prev_start, datetime.min.time())
    start_plus_dt = datetime.combine(start, datetime.min.time())

    # Current period
    rows = (
        db.query(
            Product.id, Product.name, Product.category, Product.price, Product.cost,
            func.coalesce(func.sum(TransactionItem.total), 0).label("revenue"),
            func.coalesce(func.sum(TransactionItem.quantity), 0).label("units"),
            func.max(Transaction.timestamp).label("last_sold"),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(Product.shop_id == shop_id, Transaction.timestamp >= start_dt)
        .group_by(Product.id, Product.name, Product.category, Product.price, Product.cost)
        .order_by(func.sum(TransactionItem.total).desc())
        .limit(30)
        .all()
    )

    # Previous period for trend comparison
    prev_rev = dict(
        db.query(
            Product.id,
            func.coalesce(func.sum(TransactionItem.total), 0),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(
            Product.shop_id == shop_id,
            Transaction.timestamp >= prev_start_dt,
            Transaction.timestamp < start_plus_dt,
        )
        .group_by(Product.id)
        .all()
    )

    products = []
    for r in rows:
        margin = None
        if r.cost and r.cost > 0:
            margin = round(float(r.price - r.cost) / float(r.price) * 100, 1)

        # Trend calculation
        curr_rev = float(r.revenue)
        prev = float(prev_rev.get(r.id, 0))
        if prev > 0:
            change = (curr_rev - prev) / prev * 100
            trend = "growing" if change > 10 else ("declining" if change < -10 else "stable")
        else:
            trend = "growing" if curr_rev > 0 else "stable"

        # Lifecycle stage
        lifecycle = "growing" if trend == "growing" else ("declining" if trend == "declining" else "mature")

        products.append({
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "revenue": curr_rev,
            "units_sold": int(r.units),
            "avg_price": float(r.price),
            "margin": margin,
            "trend": trend,
            "last_sold": r.last_sold.isoformat() if r.last_sold else None,
            "lifecycle": lifecycle,
        })

    total = db.query(func.count(Product.id)).filter(Product.shop_id == shop_id).scalar() or 0

    # Slow movers: products not sold in 14+ days
    fourteen_days_ago = datetime.combine(today - timedelta(days=14), datetime.min.time())
    all_products = db.query(Product).filter(Product.shop_id == shop_id, Product.is_active.is_(True)).all()
    recent_sellers = set(
        r[0] for r in db.query(TransactionItem.product_id)
        .join(Transaction)
        .filter(Transaction.shop_id == shop_id, Transaction.timestamp >= fourteen_days_ago)
        .distinct()
        .all()
    )
    slow_movers = [
        {"id": p.id, "name": p.name, "category": p.category, "price": float(p.price)}
        for p in all_products if p.id not in recent_sellers
    ]

    # Best sellers (top 3 detailed)
    best_sellers = products[:3] if products else []

    # Bundling suggestions from co-purchase data
    bundling = _get_bundling_suggestions(db, shop_id, start_dt)

    # Category breakdown
    cat_rows = (
        db.query(
            Product.category,
            func.coalesce(func.sum(TransactionItem.total), 0).label("revenue"),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(Product.shop_id == shop_id, Transaction.timestamp >= start_dt)
        .group_by(Product.category)
        .order_by(func.sum(TransactionItem.total).desc())
        .all()
    )
    category_breakdown = [{"category": c.category or "Uncategorized", "revenue": float(c.revenue)} for c in cat_rows]

    return {
        "top_products": products,
        "total_products": total,
        "slow_movers": slow_movers,
        "best_sellers": best_sellers,
        "bundling_suggestions": bundling,
        "category_breakdown": category_breakdown,
    }


def _get_bundling_suggestions(db: Session, shop_id: str, since: datetime) -> list[dict]:
    """Find products frequently purchased together."""
    txs = (
        db.query(Transaction.id)
        .filter(Transaction.shop_id == shop_id, Transaction.timestamp >= since, Transaction.items_count >= 2)
        .all()
    )
    tx_ids = [t.id for t in txs]
    if not tx_ids:
        return []

    # Get items per transaction (limit for performance)
    pairs: dict[tuple, int] = defaultdict(int)
    for batch_start in range(0, len(tx_ids), 200):
        batch = tx_ids[batch_start:batch_start + 200]
        items_by_tx: dict[str, list] = defaultdict(list)
        rows = (
            db.query(TransactionItem.transaction_id, Product.id, Product.name)
            .join(Product, Product.id == TransactionItem.product_id)
            .filter(TransactionItem.transaction_id.in_(batch))
            .all()
        )
        for row in rows:
            items_by_tx[row.transaction_id].append((row.id, row.name))

        for tx_items in items_by_tx.values():
            if len(tx_items) < 2:
                continue
            for i in range(len(tx_items)):
                for j in range(i + 1, len(tx_items)):
                    if tx_items[i][0] != tx_items[j][0]:
                        key = tuple(sorted([tx_items[i], tx_items[j]], key=lambda x: x[0]))
                        pairs[key] += 1

    top_pairs = sorted(pairs.items(), key=lambda x: x[1], reverse=True)[:5]
    return [
        {
            "product_a": pair[0][1],
            "product_b": pair[1][1],
            "co_purchase_count": count,
            "suggestion": f"Customers who buy {pair[0][1]} often also buy {pair[1][1]}",
        }
        for pair, count in top_pairs
    ]


# ── Customer Analytics ────────────────────────────────────────────────────────

def get_customer_metrics(db: Session, shop_id: str) -> dict:
    today = _today()
    latest_tx = db.query(func.max(func.date(Transaction.timestamp))).filter(
        Transaction.shop_id == shop_id,
    ).scalar()
    if latest_tx and latest_tx < today - timedelta(days=1):
        today = latest_tx
    total = db.query(func.count(Customer.id)).filter(Customer.shop_id == shop_id).scalar() or 0
    repeat = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 1
    ).scalar() or 0

    thirty_days_ago = today - timedelta(days=30)
    sixty_days_ago = today - timedelta(days=60)

    new_30d = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        func.date(Customer.first_seen) >= thirty_days_ago,
    ).scalar() or 0

    repeat_rate = round(repeat / total * 100, 1) if total > 0 else 0.0

    # Churn rate: customers not seen in 60+ days / total active
    active_before = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.visit_count >= 1,
        Customer.first_seen < datetime.combine(sixty_days_ago, datetime.min.time()),
    ).scalar() or 0
    churned = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.segment == "lost",
    ).scalar() or 0
    churn_rate = round(churned / active_before * 100, 1) if active_before > 0 else 0.0

    avg_rev = db.query(func.avg(Customer.total_spent)).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 0
    ).scalar()
    avg_rev = round(float(avg_rev), 2) if avg_rev else 0.0

    avg_visits = db.query(func.avg(Customer.visit_count)).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 0
    ).scalar()
    avg_visits = round(float(avg_visits), 1) if avg_visits else 0.0

    avg_days = db.query(func.avg(Customer.avg_days_between_visits)).filter(
        Customer.shop_id == shop_id, Customer.avg_days_between_visits.isnot(None)
    ).scalar()
    avg_days = round(float(avg_days), 1) if avg_days else 0.0

    # Segments
    segments = {}
    for seg in ["vip", "regular", "at_risk", "lost"]:
        segments[seg] = db.query(func.count(Customer.id)).filter(
            Customer.shop_id == shop_id, Customer.segment == seg
        ).scalar() or 0

    # Top 20 customers
    top = (
        db.query(Customer)
        .filter(Customer.shop_id == shop_id, Customer.visit_count > 0)
        .order_by(Customer.total_spent.desc())
        .limit(20)
        .all()
    )
    top_list = [
        {
            "id": c.id,
            "segment": c.segment,
            "visit_count": c.visit_count,
            "total_spent": float(c.total_spent),
            "avg_order_value": float(c.avg_order_value) if c.avg_order_value else 0,
            "last_seen": c.last_seen.isoformat() if c.last_seen else None,
        }
        for c in top
    ]

    # Acquisition trend (new customers per week, last 12 weeks)
    acq_trend = []
    for w in range(12):
        week_end = today - timedelta(weeks=w)
        week_start = week_end - timedelta(days=6)
        count = db.query(func.count(Customer.id)).filter(
            Customer.shop_id == shop_id,
            func.date(Customer.first_seen) >= week_start,
            func.date(Customer.first_seen) <= week_end,
        ).scalar() or 0
        acq_trend.append({"week_start": week_start.isoformat(), "new_customers": count})
    acq_trend.reverse()

    # Spending distribution
    spending_dist = _get_spending_distribution(db, shop_id)

    return {
        "total_customers": total,
        "repeat_customers": repeat,
        "new_customers_30d": new_30d,
        "repeat_rate": repeat_rate,
        "churn_rate": churn_rate,
        "avg_revenue_per_customer": avg_rev,
        "avg_visits_per_customer": avg_visits,
        "avg_days_between_visits": avg_days,
        "segments": segments,
        "top_customers": top_list,
        "acquisition_trend": acq_trend,
        "spending_distribution": spending_dist,
    }


def _get_spending_distribution(db: Session, shop_id: str) -> list[dict]:
    """Histogram of customer spending."""
    customers = db.query(Customer.total_spent).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 0
    ).all()
    if not customers:
        return []

    buckets = [0, 25, 50, 100, 200, 500, 1000, float("inf")]
    labels = ["$0-25", "$25-50", "$50-100", "$100-200", "$200-500", "$500-1k", "$1k+"]
    counts = [0] * len(labels)

    for (spent,) in customers:
        val = float(spent)
        for i in range(len(buckets) - 1):
            if buckets[i] <= val < buckets[i + 1]:
                counts[i] += 1
                break

    return [{"range": labels[i], "count": counts[i]} for i in range(len(labels))]


# ── Cohort Analysis ──────────────────────────────────────────────────────────

def get_cohort_analysis(db: Session, shop_id: str) -> dict:
    """Monthly cohort retention analysis."""
    today = _today()
    customers = db.query(Customer).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 0
    ).all()

    if not customers:
        return {"cohorts": [], "months": []}

    # Group customers by acquisition month
    cohorts: dict[str, set] = defaultdict(set)
    for c in customers:
        if c.first_seen:
            cohort_key = c.first_seen.strftime("%Y-%m")
            cohorts[cohort_key].add(c.id)

    # Get all transactions grouped by customer and month
    tx_months: dict[str, set] = defaultdict(set)
    txs = db.query(Transaction.customer_id, Transaction.timestamp).filter(
        Transaction.shop_id == shop_id,
        Transaction.customer_id.isnot(None),
    ).all()
    for tx in txs:
        month_key = tx.timestamp.strftime("%Y-%m")
        tx_months[tx.customer_id].add(month_key)

    # Build cohort table
    sorted_cohorts = sorted(cohorts.keys())[-6:]  # Last 6 months
    all_months = sorted(set(m for months in tx_months.values() for m in months))

    result = []
    for cohort_key in sorted_cohorts:
        cust_ids = cohorts[cohort_key]
        total = len(cust_ids)
        retention = []

        cohort_month_idx = all_months.index(cohort_key) if cohort_key in all_months else -1
        if cohort_month_idx < 0:
            continue

        for offset in range(min(6, len(all_months) - cohort_month_idx)):
            target_month = all_months[cohort_month_idx + offset]
            active = sum(1 for cid in cust_ids if target_month in tx_months.get(cid, set()))
            retention.append(round(active / total * 100, 1) if total > 0 else 0)

        # Pad with None
        while len(retention) < 6:
            retention.append(None)

        result.append({
            "cohort": cohort_key,
            "total": total,
            "retention": retention,
        })

    month_labels = [f"Month {i}" for i in range(6)]
    return {"cohorts": result, "months": month_labels}


# ── RFM Analysis ──────────────────────────────────────────────────────────────

def get_rfm_analysis(db: Session, shop_id: str) -> dict:
    """Recency, Frequency, Monetary scoring."""
    today = _today()
    latest_tx = db.query(func.max(func.date(Transaction.timestamp))).filter(
        Transaction.shop_id == shop_id,
    ).scalar()
    if latest_tx and latest_tx < today - timedelta(days=1):
        today = latest_tx
    today_dt = datetime.combine(today, datetime.min.time())
    customers = db.query(Customer).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 0
    ).all()

    if not customers:
        return {"customers": [], "segment_counts": {}}

    rfm_data = []
    for c in customers:
        recency = (today_dt - c.last_seen).days if c.last_seen else 999
        frequency = c.visit_count
        monetary = float(c.total_spent)
        rfm_data.append((c, recency, frequency, monetary))

    # Score each dimension 1-5 using quintiles
    recencies = sorted(set(r for _, r, _, _ in rfm_data))
    frequencies = sorted(set(f for _, _, f, _ in rfm_data))
    monetaries = sorted(set(m for _, _, _, m in rfm_data))

    def quintile_score(val, sorted_vals, reverse=False):
        if not sorted_vals:
            return 3
        idx = 0
        for i, v in enumerate(sorted_vals):
            if val <= v:
                idx = i
                break
            idx = i
        pct = idx / len(sorted_vals) if len(sorted_vals) > 1 else 0.5
        score = int(pct * 5) + 1
        score = min(5, max(1, score))
        return (6 - score) if reverse else score

    result = []
    segment_counts: dict[str, int] = defaultdict(int)

    for c, recency, frequency, monetary in rfm_data:
        r_score = quintile_score(recency, recencies, reverse=True)  # Lower recency = higher score
        f_score = quintile_score(frequency, frequencies)
        m_score = quintile_score(monetary, monetaries)
        rfm_str = f"{r_score}{f_score}{m_score}"

        # Segment based on RFM
        total_score = r_score + f_score + m_score
        if total_score >= 13:
            segment = "Champions"
        elif r_score >= 4 and f_score >= 3:
            segment = "Loyal"
        elif r_score >= 3 and f_score <= 2:
            segment = "Potential"
        elif r_score <= 2 and f_score >= 3:
            segment = "At Risk"
        elif r_score <= 2 and f_score <= 2:
            segment = "Lost"
        else:
            segment = "Regular"

        segment_counts[segment] += 1
        result.append({
            "id": c.id,
            "recency_days": recency,
            "frequency": frequency,
            "monetary": monetary,
            "rfm_score": rfm_str,
            "segment": segment,
        })

    # Sort by monetary desc, limit to top 100
    result.sort(key=lambda x: x["monetary"], reverse=True)
    return {"customers": result[:100], "segment_counts": dict(segment_counts)}


# ── Customer Lifetime Value ──────────────────────────────────────────────────

def get_clv(db: Session, shop_id: str) -> dict:
    """Calculate customer lifetime value."""
    customers = db.query(Customer).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 0
    ).all()

    if not customers:
        return {"avg_clv": 0, "median_clv": 0, "top_clv_customers": [], "clv_distribution": []}

    clv_values = []
    for c in customers:
        aov = float(c.avg_order_value) if c.avg_order_value else 0
        freq = c.visit_count
        # Estimated lifespan: based on average days between visits
        if c.avg_days_between_visits and c.avg_days_between_visits > 0:
            annual_freq = 365 / c.avg_days_between_visits
        else:
            annual_freq = freq  # Use actual visits as proxy
        clv = aov * annual_freq * 2  # 2-year estimated lifespan
        clv_values.append((c, clv))

    clv_only = [v for _, v in clv_values]
    avg_clv = round(statistics.mean(clv_only), 2) if clv_only else 0
    median_clv = round(statistics.median(clv_only), 2) if clv_only else 0

    # Top CLV customers
    top = sorted(clv_values, key=lambda x: x[1], reverse=True)[:10]
    top_list = [
        {
            "id": c.id,
            "clv": round(clv, 2),
            "total_spent": float(c.total_spent),
            "visit_count": c.visit_count,
            "segment": c.segment,
        }
        for c, clv in top
    ]

    # CLV distribution
    buckets = [0, 100, 250, 500, 1000, 2500, 5000, float("inf")]
    labels = ["$0-100", "$100-250", "$250-500", "$500-1k", "$1k-2.5k", "$2.5k-5k", "$5k+"]
    counts = [0] * len(labels)
    for val in clv_only:
        for i in range(len(buckets) - 1):
            if buckets[i] <= val < buckets[i + 1]:
                counts[i] += 1
                break

    dist = [{"range": labels[i], "count": counts[i]} for i in range(len(labels))]

    return {
        "avg_clv": avg_clv,
        "median_clv": median_clv,
        "top_clv_customers": top_list,
        "clv_distribution": dist,
    }


# ── Churn Prediction ─────────────────────────────────────────────────────────

def get_churn_predictions(db: Session, shop_id: str) -> dict:
    """Flag customers likely to churn based on declining visit frequency."""
    today = _today()
    latest_tx = db.query(func.max(func.date(Transaction.timestamp))).filter(
        Transaction.shop_id == shop_id,
    ).scalar()
    if latest_tx and latest_tx < today - timedelta(days=1):
        today = latest_tx
    today_dt = datetime.combine(today, datetime.min.time())

    customers = db.query(Customer).filter(
        Customer.shop_id == shop_id,
        Customer.visit_count >= 2,
        Customer.segment.in_(["regular", "at_risk", "vip"]),
    ).all()

    predictions = []
    for c in customers:
        days_since = (today_dt - c.last_seen).days if c.last_seen else 999
        avg_gap = c.avg_days_between_visits or 30

        # Risk score: higher = more likely to churn
        if avg_gap > 0:
            overdue_ratio = days_since / avg_gap
        else:
            overdue_ratio = 1.0

        if overdue_ratio > 3:
            risk = min(0.95, 0.5 + overdue_ratio * 0.1)
        elif overdue_ratio > 2:
            risk = min(0.80, 0.3 + overdue_ratio * 0.1)
        elif overdue_ratio > 1.5:
            risk = min(0.60, 0.2 + overdue_ratio * 0.1)
        else:
            risk = max(0.05, overdue_ratio * 0.15)

        if risk > 0.3:
            predictions.append({
                "id": c.id,
                "risk_score": round(risk, 2),
                "days_since_visit": days_since,
                "visit_count": c.visit_count,
                "total_spent": float(c.total_spent),
                "segment": c.segment,
            })

    predictions.sort(key=lambda x: x["risk_score"], reverse=True)

    # Win-back opportunities (high-value at-risk customers)
    win_back = [
        {
            "id": p["id"],
            "total_spent": p["total_spent"],
            "days_since_visit": p["days_since_visit"],
            "suggestion": f"Send a personalized offer — this customer has spent ${p['total_spent']:.0f} total",
        }
        for p in predictions[:10]
        if p["total_spent"] > 100
    ]

    return {
        "at_risk_count": len(predictions),
        "predictions": predictions[:50],
        "win_back_opportunities": win_back,
    }


# ── Anomaly Detection ────────────────────────────────────────────────────────

def get_anomalies(db: Session, shop_id: str, days: int = 90) -> list[dict]:
    """Detect unusual revenue days (2+ standard deviations from mean)."""
    today = _today()
    latest_snap = db.query(func.max(DailySnapshot.date)).filter(
        DailySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < today - timedelta(days=1):
        today = latest_snap
    start = today - timedelta(days=days)

    rows = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= start)
        .order_by(DailySnapshot.date)
        .all()
    )

    if len(rows) < 14:
        return []

    revenues = [float(r.total_revenue) for r in rows]
    mean_rev = statistics.mean(revenues)
    std_rev = statistics.stdev(revenues) if len(revenues) > 1 else 0

    anomalies = []
    if std_rev > 0:
        for r in rows:
            rev = float(r.total_revenue)
            deviation = (rev - mean_rev) / std_rev
            if abs(deviation) >= 2.0:
                anomalies.append({
                    "date": r.date.isoformat(),
                    "revenue": rev,
                    "expected": round(mean_rev, 2),
                    "deviation": round(deviation, 2),
                    "type": "spike" if deviation > 0 else "dip",
                })

    return anomalies


# ── Moving Averages ──────────────────────────────────────────────────────────

def get_moving_averages(db: Session, shop_id: str, days: int = 90) -> dict:
    """Calculate 7-day and 30-day moving averages."""
    today = _today()
    latest_snap = db.query(func.max(DailySnapshot.date)).filter(
        DailySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < today - timedelta(days=1):
        today = latest_snap
    start = today - timedelta(days=days + 30)  # Extra days for 30d MA warmup

    rows = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= start)
        .order_by(DailySnapshot.date)
        .all()
    )

    data = [(r.date, float(r.total_revenue)) for r in rows]
    result_7d = []
    result_30d = []

    for i, (d, rev) in enumerate(data):
        if d < today - timedelta(days=days):
            continue
        # 7-day MA
        if i >= 6:
            window = [data[j][1] for j in range(i - 6, i + 1)]
            result_7d.append({"date": d.isoformat(), "value": round(statistics.mean(window), 2)})
        # 30-day MA
        if i >= 29:
            window = [data[j][1] for j in range(i - 29, i + 1)]
            result_30d.append({"date": d.isoformat(), "value": round(statistics.mean(window), 2)})

    return {"ma_7d": result_7d, "ma_30d": result_30d}


# ── Financial Analytics ──────────────────────────────────────────────────────

def get_financial_summary(db: Session, shop_id: str) -> dict:
    today = _today()
    latest_snap = db.query(func.max(DailySnapshot.date)).filter(
        DailySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < today - timedelta(days=1):
        today = latest_snap
    thirty_days_ago = today - timedelta(days=30)

    # Revenue last 30 days
    rev_30d = _revenue_range(db, shop_id, thirty_days_ago, today)

    # Get settings
    shop_settings = db.query(ShopSettings).filter(ShopSettings.shop_id == shop_id).first()
    shop = db.query(Shop).filter(Shop.id == shop_id).first()

    cogs_pct = shop_settings.avg_cogs_percentage / 100 if shop_settings else 0.38
    tax_rate = shop_settings.tax_rate / 100 if shop_settings else 0.0825
    staff_rate = float(shop_settings.staff_hourly_rate) if shop_settings else 17.50

    estimated_cogs = round(rev_30d * cogs_pct, 2)
    gross_profit = round(rev_30d - estimated_cogs, 2)
    gross_margin = round(gross_profit / rev_30d * 100, 1) if rev_30d > 0 else 0

    # Get expenses
    expenses = db.query(Expense).filter(Expense.shop_id == shop_id).all()
    total_monthly_expenses = sum(float(e.amount) for e in expenses if e.is_monthly)

    net_profit = round(gross_profit - total_monthly_expenses, 2)

    # Break-even
    avg_tx_value = db.query(func.avg(Transaction.total)).filter(
        Transaction.shop_id == shop_id,
        func.date(Transaction.timestamp) >= thirty_days_ago,
    ).scalar()
    avg_tx_val = float(avg_tx_value) if avg_tx_value else 50
    daily_fixed = total_monthly_expenses / 30
    margin_per_tx = avg_tx_val * (1 - cogs_pct)
    break_even_tx = math.ceil(daily_fixed / margin_per_tx) if margin_per_tx > 0 else 0

    # Revenue per sqft
    rev_per_sqft = None
    if shop and shop.store_size_sqft and shop.store_size_sqft > 0:
        rev_per_sqft = round(rev_30d / shop.store_size_sqft, 2)

    # Revenue per staff hour (assuming 8hr days, 26 working days)
    staff_count = shop.staff_count if shop else 1
    total_staff_hours = staff_count * 8 * 26
    rev_per_staff_hour = round(rev_30d / total_staff_hours, 2) if total_staff_hours > 0 else 0

    # Tax collected
    tax_collected = db.query(func.coalesce(func.sum(Transaction.tax), 0)).filter(
        Transaction.shop_id == shop_id,
        func.date(Transaction.timestamp) >= thirty_days_ago,
    ).scalar()

    # Cash flow projection (next 30 days based on recent trend)
    daily_snaps = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= thirty_days_ago)
        .order_by(DailySnapshot.date)
        .all()
    )
    daily_revs = [float(s.total_revenue) for s in daily_snaps]
    avg_daily = statistics.mean(daily_revs) if daily_revs else 0
    daily_expense = total_monthly_expenses / 30

    cash_flow = []
    running = 0
    for i in range(30):
        d = today + timedelta(days=i + 1)
        running += avg_daily - daily_expense
        cash_flow.append({"date": d.isoformat(), "projected_cash": round(running, 2)})

    # Monthly P&L (last 6 months)
    monthly_pnl = []
    for m in range(6):
        m_end = today.replace(day=1) - timedelta(days=30 * m)
        m_start = m_end.replace(day=1)
        m_rev = _revenue_range(db, shop_id, m_start, m_end)
        m_cogs = m_rev * cogs_pct
        m_gross = m_rev - m_cogs
        m_net = m_gross - total_monthly_expenses
        monthly_pnl.append({
            "month": m_start.strftime("%Y-%m"),
            "revenue": round(m_rev, 2),
            "cogs": round(m_cogs, 2),
            "gross_profit": round(m_gross, 2),
            "expenses": round(total_monthly_expenses, 2),
            "net_profit": round(m_net, 2),
        })
    monthly_pnl.reverse()

    expense_list = [
        {"id": e.id, "category": e.category, "name": e.name, "amount": float(e.amount), "is_monthly": e.is_monthly}
        for e in expenses
    ]

    return {
        "total_revenue_30d": round(rev_30d, 2),
        "total_expenses_monthly": round(total_monthly_expenses, 2),
        "estimated_cogs": estimated_cogs,
        "gross_profit": gross_profit,
        "gross_margin": gross_margin,
        "net_profit_estimate": net_profit,
        "break_even_daily_transactions": break_even_tx,
        "revenue_per_sqft": rev_per_sqft,
        "revenue_per_staff_hour": rev_per_staff_hour,
        "estimated_tax_collected": round(float(tax_collected), 2),
        "cash_flow_projection": cash_flow,
        "monthly_pnl": monthly_pnl,
        "expenses": expense_list,
    }


# ── Marketing Analytics ──────────────────────────────────────────────────────

def get_marketing_insights(db: Session, shop_id: str) -> dict:
    from app.models import MarketingCampaign

    # Use effective "today" based on latest data
    today = _today()
    latest_snap = db.query(func.max(DailySnapshot.date)).filter(
        DailySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < today - timedelta(days=1):
        today = latest_snap

    campaigns = db.query(MarketingCampaign).filter(MarketingCampaign.shop_id == shop_id).all()

    campaign_list = []
    total_spend = 0
    total_rev = 0
    for c in campaigns:
        spend = float(c.spend)
        rev = float(c.revenue_attributed)
        roi = round((rev - spend) / spend * 100, 1) if spend > 0 else 0
        total_spend += spend
        total_rev += rev
        campaign_list.append({
            "id": c.id,
            "name": c.name,
            "channel": c.channel,
            "spend": spend,
            "start_date": c.start_date.isoformat(),
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "revenue_attributed": rev,
            "roi": roi,
        })

    overall_roi = round((total_rev - total_spend) / total_spend * 100, 1) if total_spend > 0 else 0

    # Customer acquisition cost
    new_30d = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        func.date(Customer.first_seen) >= today - timedelta(days=30),
    ).scalar() or 1
    cac = round(total_spend / new_30d, 2) if new_30d > 0 else 0

    # Best posting times from peak transaction hours
    hourly = (
        db.query(
            HourlySnapshot.hour,
            func.avg(HourlySnapshot.transaction_count).label("avg_tx"),
        )
        .filter(HourlySnapshot.shop_id == shop_id, HourlySnapshot.date >= today - timedelta(days=30))
        .group_by(HourlySnapshot.hour)
        .order_by(func.avg(HourlySnapshot.transaction_count).desc())
        .limit(5)
        .all()
    )
    best_times = [
        {"hour": h.hour, "label": f"{h.hour % 12 or 12}{'pm' if h.hour >= 12 else 'am'}", "reason": "High customer activity"}
        for h in hourly
    ]

    # Content suggestions based on top products
    top_prods = (
        db.query(Product.name)
        .join(TransactionItem)
        .join(Transaction)
        .filter(Product.shop_id == shop_id, Transaction.timestamp >= datetime.combine(today - timedelta(days=14), datetime.min.time()))
        .group_by(Product.name)
        .order_by(func.sum(TransactionItem.total).desc())
        .limit(3)
        .all()
    )
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    content = [
        {"suggestion": f"Post about your best-selling {p.name} this {random.choice(day_names)}", "type": "product_highlight"}
        for p in top_prods
    ]
    content.extend([
        {"suggestion": "Share a behind-the-scenes look at your shop on Instagram Stories", "type": "engagement"},
        {"suggestion": "Run a limited-time flash sale announcement on social media", "type": "promotion"},
    ])

    # Promotional effectiveness placeholder
    promo_effectiveness = [
        {"type": "Percentage Off", "avg_revenue_lift": 22, "best_for": "Clearing inventory"},
        {"type": "Buy One Get One", "avg_revenue_lift": 35, "best_for": "Increasing basket size"},
        {"type": "Free Shipping/Gift", "avg_revenue_lift": 18, "best_for": "Customer acquisition"},
    ]

    return {
        "campaigns": campaign_list,
        "total_spend": round(total_spend, 2),
        "total_attributed_revenue": round(total_rev, 2),
        "overall_roi": overall_roi,
        "avg_customer_acquisition_cost": cac,
        "best_posting_times": best_times,
        "content_suggestions": content,
        "promotional_effectiveness": promo_effectiveness,
    }




# ── AI Action Items (legacy compat) ──────────────────────────────────────────

def get_ai_actions(db: Session, shop_id: str) -> list[dict]:
    """Quick AI actions for the overview page (delegates to recommendation engine)."""
    from app.models import Recommendation
    recs = (
        db.query(Recommendation)
        .filter(Recommendation.shop_id == shop_id, Recommendation.status == "active")
        .order_by(
            case(
                (Recommendation.priority == "critical", 0),
                (Recommendation.priority == "high", 1),
                (Recommendation.priority == "medium", 2),
                else_=3,
            ),
            Recommendation.created_at.desc(),
        )
        .limit(7)
        .all()
    )

    if recs:
        return [
            {
                "id": r.id,
                "type": r.category,
                "priority": r.priority,
                "emoji": r.emoji,
                "title": r.title,
                "description": r.description,
                "estimated_impact": r.estimated_impact,
                "action_steps": r.action_steps,
                "status": r.status,
            }
            for r in recs
        ]

    # Fallback: generate on-the-fly if no stored recommendations
    return _generate_fallback_actions(db, shop_id)


def _generate_fallback_actions(db: Session, shop_id: str) -> list[dict]:
    """Generate basic actions if recommendation engine hasn't run yet."""
    today = _today()
    latest_tx = db.query(func.max(func.date(Transaction.timestamp))).filter(
        Transaction.shop_id == shop_id,
    ).scalar()
    if latest_tx and latest_tx < today - timedelta(days=1):
        today = latest_tx
    actions = []

    # Lapsed customers
    thirty_ago = datetime.combine(today - timedelta(days=30), datetime.min.time())
    lapsed = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.visit_count > 1, Customer.last_seen < thirty_ago,
    ).scalar() or 0
    if lapsed > 0:
        actions.append({
            "type": "customers", "priority": "high", "emoji": "1f4e9",
            "title": f"{lapsed} repeat customers haven't returned in 30+ days",
            "description": "Send a personalized win-back email with a 15% discount code.",
            "estimated_impact": f"Could recover ${lapsed * 45}/month in revenue",
        })

    # Peak hour staffing
    peak = (
        db.query(HourlySnapshot.hour, func.avg(HourlySnapshot.revenue).label("avg_rev"))
        .filter(HourlySnapshot.shop_id == shop_id, HourlySnapshot.date >= today - timedelta(days=14))
        .group_by(HourlySnapshot.hour)
        .order_by(func.avg(HourlySnapshot.revenue).desc())
        .first()
    )
    if peak:
        h = peak.hour
        label = f"{h % 12 or 12}{'pm' if h >= 12 else 'am'}"
        actions.append({
            "type": "operations", "priority": "medium", "emoji": "23f0",
            "title": f"Your peak hour is {label} — ensure full staffing",
            "description": f"Average revenue at {label} is ${float(peak.avg_rev):,.0f}.",
            "estimated_impact": "Proper staffing can increase conversion by 15%",
        })

    return actions[:5]


# ── Product Recommendations ──────────────────────────────────────────────


def get_product_recommendations(db: Session, shop_id: str) -> dict:
    """Generate product recommendations: bundling, markdown, timing, restocking."""
    today = _today()
    latest_tx = db.query(func.max(func.date(Transaction.timestamp))).filter(
        Transaction.shop_id == shop_id,
    ).scalar()
    if latest_tx and latest_tx < today - timedelta(days=1):
        today = latest_tx

    since_30 = datetime.combine(today - timedelta(days=30), datetime.min.time())
    since_14 = datetime.combine(today - timedelta(days=14), datetime.min.time())
    since_60 = datetime.combine(today - timedelta(days=60), datetime.min.time())
    since_prev = datetime.combine(today - timedelta(days=60), datetime.min.time())

    # Get all products with sales data
    products = (
        db.query(
            Product.id, Product.name, Product.category, Product.price, Product.cost,
            Product.stock_quantity,
            func.coalesce(func.sum(TransactionItem.total), 0).label("revenue_30d"),
            func.coalesce(func.sum(TransactionItem.quantity), 0).label("units_30d"),
        )
        .outerjoin(TransactionItem, TransactionItem.product_id == Product.id)
        .outerjoin(Transaction, and_(
            Transaction.id == TransactionItem.transaction_id,
            Transaction.timestamp >= since_30,
        ))
        .filter(Product.shop_id == shop_id, Product.is_active.is_(True))
        .group_by(Product.id, Product.name, Product.category, Product.price, Product.cost, Product.stock_quantity)
        .all()
    )

    recommendations = []

    # 1. Bundling suggestions (from co-purchase)
    bundles = _get_bundling_suggestions(db, shop_id, since_30)
    for b in bundles[:3]:
        recommendations.append({
            "type": "bundle",
            "icon": "1F381",
            "title": f"Bundle: {b['product_a']} + {b['product_b']}",
            "description": f"Purchased together {b['co_purchase_count']} times in the last 30 days. Create a bundle discount to increase AOV.",
            "action": f"Create a bundle display and offer 10% off when bought together.",
            "priority": "high" if b["co_purchase_count"] >= 5 else "medium",
            "estimated_impact": f"+${b['co_purchase_count'] * 8} monthly revenue from bundle upsells",
        })

    # 2. Markdown suggestions (slow movers with stock)
    for p in products:
        units = int(p.units_30d)
        stock = p.stock_quantity or 0
        if units <= 1 and stock >= 5 and float(p.price) > 10:
            discount_price = round(float(p.price) * 0.75, 2)
            recommendations.append({
                "type": "markdown",
                "icon": "1F3F7",
                "title": f"Mark down {p.name}",
                "description": f"Only {units} sold in 30 days with {stock} in stock. Consider marking down from ${float(p.price):.0f} to ${discount_price:.0f}.",
                "action": f"25% markdown to ${discount_price:.0f} to clear inventory.",
                "priority": "medium",
                "estimated_impact": f"Clear ${stock * discount_price:.0f} in stagnant inventory",
            })
            if len([r for r in recommendations if r["type"] == "markdown"]) >= 3:
                break

    # 3. Timing recommendations (best day/time to promote each top product)
    top_prods = sorted(products, key=lambda p: float(p.revenue_30d), reverse=True)[:5]
    for p in top_prods:
        if int(p.units_30d) < 3:
            continue
        # Find when this product sells most
        dow_sales = (
            db.query(
                extract("dow", Transaction.timestamp).label("dow"),
                func.sum(TransactionItem.quantity).label("qty"),
            )
            .join(TransactionItem, TransactionItem.transaction_id == Transaction.id)
            .filter(
                TransactionItem.product_id == p.id,
                Transaction.shop_id == shop_id,
                Transaction.timestamp >= since_30,
            )
            .group_by("dow")
            .order_by(func.sum(TransactionItem.quantity).desc())
            .first()
        )
        if dow_sales:
            day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            best_dow = int(dow_sales.dow)
            day_name = day_names[best_dow] if 0 <= best_dow < 7 else "weekdays"
            recommendations.append({
                "type": "timing",
                "icon": "23F0",
                "title": f"Promote {p.name} on {day_name}s",
                "description": f"{p.name} sells best on {day_name}s ({int(dow_sales.qty)} units). Schedule social posts and feature it on that day.",
                "action": f"Create a '{day_name} Special' featuring {p.name}.",
                "priority": "medium",
                "estimated_impact": f"+15% sales for {p.name} with targeted timing",
            })
            if len([r for r in recommendations if r["type"] == "timing"]) >= 3:
                break

    # 4. Restocking alerts
    for p in products:
        units = int(p.units_30d)
        stock = p.stock_quantity or 0
        if units >= 10 and stock <= 5 and stock > 0:
            days_left = round(stock / (units / 30), 1) if units > 0 else 99
            recommendations.append({
                "type": "restock",
                "icon": "1F4E6",
                "title": f"Restock {p.name} soon",
                "description": f"Only {stock} left in stock, selling ~{units} per month. Estimated {days_left} days until stockout.",
                "action": f"Order more {p.name} immediately to avoid missed sales.",
                "priority": "high",
                "estimated_impact": f"Prevent ~${float(p.price) * units * 0.5:.0f} in lost sales",
            })
            if len([r for r in recommendations if r["type"] == "restock"]) >= 3:
                break

    # Sort: high priority first
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda r: priority_order.get(r["priority"], 3))

    return {
        "recommendations": recommendations,
        "total": len(recommendations),
        "summary": {
            "bundles": len([r for r in recommendations if r["type"] == "bundle"]),
            "markdowns": len([r for r in recommendations if r["type"] == "markdown"]),
            "timing": len([r for r in recommendations if r["type"] == "timing"]),
            "restock": len([r for r in recommendations if r["type"] == "restock"]),
        },
    }


# ── Break-Even Analysis ──────────────────────────────────────────────────


def get_break_even_analysis(db: Session, shop_id: str) -> dict:
    """Detailed break-even analysis with scenario modeling."""
    today = _today()
    latest_snap = db.query(func.max(DailySnapshot.date)).filter(
        DailySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < today - timedelta(days=1):
        today = latest_snap

    thirty_ago = today - timedelta(days=30)
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    settings = db.query(ShopSettings).filter(ShopSettings.shop_id == shop_id).first()

    # Revenue data
    rev_30d = float(
        db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0))
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= thirty_ago)
        .scalar() or 0
    )

    # Transaction metrics
    avg_tx = float(
        db.query(func.avg(Transaction.total))
        .filter(Transaction.shop_id == shop_id, func.date(Transaction.timestamp) >= thirty_ago)
        .scalar() or 50
    )
    daily_tx = float(
        db.query(func.avg(DailySnapshot.transaction_count))
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= thirty_ago)
        .scalar() or 40
    )

    # Costs
    cogs_pct = (settings.avg_cogs_percentage / 100) if settings else 0.38
    monthly_rent = float(settings.monthly_rent) if settings else 2500
    staff_rate = float(settings.staff_hourly_rate) if settings else 17.50
    staff_count = shop.staff_count if shop else 2

    # Calculate fixed & variable costs
    expenses = db.query(Expense).filter(Expense.shop_id == shop_id, Expense.is_monthly.is_(True)).all()
    total_fixed_monthly = sum(float(e.amount) for e in expenses) if expenses else monthly_rent + (staff_rate * 8 * 26 * staff_count)
    daily_fixed = total_fixed_monthly / 30

    # Margin per transaction
    margin_per_tx = avg_tx * (1 - cogs_pct)

    # Break-even calculations
    break_even_daily_tx = math.ceil(daily_fixed / margin_per_tx) if margin_per_tx > 0 else 0
    break_even_daily_rev = round(daily_fixed / (1 - cogs_pct), 2) if cogs_pct < 1 else 0
    break_even_monthly_rev = round(break_even_daily_rev * 30, 2)

    # Current status
    daily_avg_rev = rev_30d / 30 if rev_30d > 0 else 0
    surplus = round(daily_avg_rev - break_even_daily_rev, 2)
    status = "above" if surplus > 0 else ("at" if abs(surplus) < 50 else "below")
    cushion_pct = round((surplus / break_even_daily_rev) * 100, 1) if break_even_daily_rev > 0 else 0

    # Scenario modeling
    scenarios = []
    # Scenario 1: 10% price increase
    new_avg_tx_10 = avg_tx * 1.1
    new_margin_10 = new_avg_tx_10 * (1 - cogs_pct)
    be_tx_10 = math.ceil(daily_fixed / new_margin_10) if new_margin_10 > 0 else 0
    scenarios.append({
        "name": "10% Price Increase",
        "description": "If you raise prices by 10%, how many fewer sales do you need?",
        "break_even_tx": be_tx_10,
        "change_from_current": be_tx_10 - break_even_daily_tx,
        "insight": f"You'd need {be_tx_10} daily transactions instead of {break_even_daily_tx} — {break_even_daily_tx - be_tx_10} fewer sales needed.",
    })

    # Scenario 2: Reduce COGS by 5%
    new_cogs = max(0, cogs_pct - 0.05)
    new_margin_cogs = avg_tx * (1 - new_cogs)
    be_tx_cogs = math.ceil(daily_fixed / new_margin_cogs) if new_margin_cogs > 0 else 0
    scenarios.append({
        "name": "5% Lower COGS",
        "description": "Negotiate better supplier prices to reduce cost of goods by 5%.",
        "break_even_tx": be_tx_cogs,
        "change_from_current": be_tx_cogs - break_even_daily_tx,
        "insight": f"Lower COGS saves ${daily_fixed * 0.05 * 30:,.0f}/month and reduces break-even to {be_tx_cogs} daily transactions.",
    })

    # Scenario 3: 20% revenue increase
    new_daily_rev = daily_avg_rev * 1.2
    new_daily_profit = new_daily_rev * (1 - cogs_pct) - daily_fixed
    scenarios.append({
        "name": "20% Revenue Growth",
        "description": "What if you increase revenue by 20% through marketing?",
        "break_even_tx": break_even_daily_tx,
        "change_from_current": 0,
        "insight": f"At 20% growth, daily profit jumps to ${new_daily_profit:,.0f} (${new_daily_profit * 30:,.0f}/month). Invest in marketing!",
    })

    # Scenario 4: Add 1 staff member
    extra_staff_cost = staff_rate * 8 * 26
    new_fixed = total_fixed_monthly + extra_staff_cost
    new_be_rev = round(new_fixed / 30 / (1 - cogs_pct), 2) if cogs_pct < 1 else 0
    new_be_tx = math.ceil((new_fixed / 30) / margin_per_tx) if margin_per_tx > 0 else 0
    scenarios.append({
        "name": "Hire 1 More Staff",
        "description": f"Adding another employee at ${staff_rate}/hr adds ${extra_staff_cost:,.0f}/month in costs.",
        "break_even_tx": new_be_tx,
        "change_from_current": new_be_tx - break_even_daily_tx,
        "insight": f"Break-even rises to {new_be_tx} daily transactions (+{new_be_tx - break_even_daily_tx}). Only hire if traffic justifies it.",
    })

    return {
        "current": {
            "daily_avg_revenue": round(daily_avg_rev, 2),
            "daily_avg_transactions": round(daily_tx, 1),
            "avg_transaction_value": round(avg_tx, 2),
            "margin_per_transaction": round(margin_per_tx, 2),
            "cogs_percentage": round(cogs_pct * 100, 1),
        },
        "costs": {
            "total_fixed_monthly": round(total_fixed_monthly, 2),
            "daily_fixed": round(daily_fixed, 2),
        },
        "break_even": {
            "daily_transactions": break_even_daily_tx,
            "daily_revenue": break_even_daily_rev,
            "monthly_revenue": break_even_monthly_rev,
        },
        "status": {
            "position": status,
            "daily_surplus": surplus,
            "cushion_pct": cushion_pct,
            "monthly_profit_estimate": round(surplus * 30, 2),
        },
        "scenarios": scenarios,
    }
