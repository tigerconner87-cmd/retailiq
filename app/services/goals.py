"""Goals & Strategy service for RetailIQ.

Tracks revenue goals, product targets, quarterly strategy,
and generates AI strategy recommendations based on performance.
"""

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    DailySnapshot, Goal, Product, ProductGoal, StrategyNote,
    Transaction, TransactionItem,
)


# ── Goals Overview ───────────────────────────────────────────────────────────


def get_goals_overview(db: Session, shop_id: str) -> dict:
    """Get all active goals with current progress."""
    today = date.today()

    goals = (
        db.query(Goal)
        .filter(Goal.shop_id == shop_id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .all()
    )

    result = []
    for g in goals:
        current_value = _calculate_progress(db, shop_id, g, today)
        target = float(g.target_value) if g.target_value else 1
        pct = round(current_value / target * 100, 1) if target > 0 else 0

        period_start, period_end = _parse_period(g.period_key, g.period)
        days_elapsed = max(1, (today - period_start).days)
        days_total = max(1, (period_end - period_start).days)
        days_remaining = max(0, (period_end - today).days)
        expected_pct = round(days_elapsed / days_total * 100, 1)

        if pct >= expected_pct * 0.9:
            pacing = "on_track"
        elif pct >= expected_pct * 0.7:
            pacing = "behind"
        else:
            pacing = "at_risk"

        daily_needed = 0.0
        if days_remaining > 0:
            remaining = max(0, target - current_value)
            daily_needed = round(remaining / days_remaining, 2)

        result.append({
            "id": g.id,
            "goal_type": g.goal_type,
            "title": g.title,
            "target_value": target,
            "current_value": round(current_value, 2),
            "unit": g.unit,
            "period": g.period,
            "period_key": g.period_key,
            "progress_pct": min(100, pct),
            "pacing": pacing,
            "days_remaining": days_remaining,
            "daily_needed": daily_needed,
            "expected_pct": expected_pct,
        })

    return {"goals": result, "total": len(result)}


# ── Product Goals ────────────────────────────────────────────────────────────


def get_product_goals(db: Session, shop_id: str) -> dict:
    """Get product-level goals with progress."""
    today = date.today()
    current_month = today.strftime("%Y-%m")
    month_start = today.replace(day=1)

    pgoals = (
        db.query(ProductGoal)
        .filter(ProductGoal.shop_id == shop_id, ProductGoal.period == current_month)
        .all()
    )

    result = []
    for pg in pgoals:
        product = db.query(Product).filter(Product.id == pg.product_id).first()
        if not product:
            continue

        sold = (
            db.query(func.coalesce(func.sum(TransactionItem.quantity), 0))
            .join(Transaction, TransactionItem.transaction_id == Transaction.id)
            .filter(
                Transaction.shop_id == shop_id,
                TransactionItem.product_id == pg.product_id,
                Transaction.timestamp >= datetime.combine(month_start, datetime.min.time()),
            )
            .scalar()
        ) or 0

        pct = round(int(sold) / pg.target_units * 100, 1) if pg.target_units > 0 else 0

        result.append({
            "id": pg.id,
            "product_name": product.name,
            "product_category": product.category,
            "target_units": pg.target_units,
            "units_sold": int(sold),
            "progress_pct": min(100, pct),
            "actual_pct": pct,
            "period": pg.period,
        })

    return {"product_goals": result, "period": current_month}


# ── Strategy Notes ───────────────────────────────────────────────────────────


def get_strategy_notes(db: Session, shop_id: str) -> dict:
    """Get quarterly strategy notes."""
    notes = (
        db.query(StrategyNote)
        .filter(StrategyNote.shop_id == shop_id)
        .order_by(StrategyNote.quarter.desc())
        .all()
    )

    return {
        "strategies": [
            {
                "id": n.id,
                "quarter": n.quarter,
                "title": n.title,
                "objectives": n.objectives or [],
                "key_results": n.key_results or [],
                "notes": n.notes,
                "status": n.status,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ]
    }


# ── Goal History ─────────────────────────────────────────────────────────────


def get_goal_history(db: Session, shop_id: str) -> dict:
    """Get past goal performance."""
    today = date.today()

    goals = (
        db.query(Goal)
        .filter(Goal.shop_id == shop_id, Goal.status.in_(["met", "missed"]))
        .order_by(Goal.period_key.desc())
        .limit(12)
        .all()
    )

    result = []
    for g in goals:
        # Calculate the final value for the past period
        _, period_end = _parse_period(g.period_key, g.period)
        achieved = _calculate_progress(db, shop_id, g, period_end)
        target = float(g.target_value) if g.target_value else 1
        pct = round(achieved / target * 100, 1) if target > 0 else 0

        result.append({
            "id": g.id,
            "goal_type": g.goal_type,
            "title": g.title,
            "target_value": target,
            "achieved_value": round(achieved, 2),
            "unit": g.unit,
            "period_key": g.period_key,
            "progress_pct": min(100, pct),
            "status": g.status,
        })

    return {"history": result}


# ── Strategy Recommendations ─────────────────────────────────────────────────


def get_strategy_recommendations(db: Session, shop_id: str) -> dict:
    """Generate AI strategy recommendations based on goal performance."""
    today = date.today()
    current_month = today.strftime("%Y-%m")

    goals = (
        db.query(Goal)
        .filter(Goal.shop_id == shop_id, Goal.status == "active")
        .all()
    )

    recommendations = []

    for g in goals:
        current_value = _calculate_progress(db, shop_id, g, today)
        target = float(g.target_value) if g.target_value else 1
        pct = round(current_value / target * 100, 1) if target > 0 else 0

        period_start, period_end = _parse_period(g.period_key, g.period)
        days_remaining = max(0, (period_end - today).days)
        days_total = max(1, (period_end - period_start).days)
        days_elapsed = max(1, (today - period_start).days)
        expected_pct = round(days_elapsed / days_total * 100, 1)

        if g.goal_type == "revenue":
            if pct >= 100:
                recommendations.append({
                    "emoji": "1f389",
                    "title": "Revenue goal achieved! Set a stretch target",
                    "description": f"You've hit ${current_value:,.0f} against your ${target:,.0f} target. Consider raising your goal or investing surplus into marketing.",
                    "priority": "low",
                    "category": "revenue",
                })
            elif pct < expected_pct * 0.7:
                daily_needed = round((target - current_value) / max(1, days_remaining), 2)
                recommendations.append({
                    "emoji": "1f4b0",
                    "title": f"Revenue goal at risk — need ${daily_needed:,.0f}/day",
                    "description": f"You're at {pct:.0f}% of your ${target:,.0f} target with {days_remaining} days left. Consider running a flash sale or promoting high-margin products.",
                    "priority": "high",
                    "category": "revenue",
                })
            elif pct < expected_pct * 0.9:
                recommendations.append({
                    "emoji": "26a0",
                    "title": "Revenue slightly behind pace — boost marketing",
                    "description": f"At {pct:.0f}% with {days_remaining} days remaining. A weekend promotion or email campaign could close the gap.",
                    "priority": "medium",
                    "category": "revenue",
                })

        elif g.goal_type == "customers":
            if pct < expected_pct * 0.8:
                recommendations.append({
                    "emoji": "1f465",
                    "title": "Customer acquisition lagging — try referrals",
                    "description": f"Only {current_value:.0f} new customers vs target of {target:.0f}. Launch a \"refer a friend\" promotion or partner with local businesses.",
                    "priority": "medium",
                    "category": "customers",
                })

        elif g.goal_type == "aov":
            if pct < expected_pct * 0.9:
                recommendations.append({
                    "emoji": "1f4c8",
                    "title": "Average order value below target — upsell more",
                    "description": f"Current AOV is ${current_value:.2f} vs target ${target:.2f}. Create bundle deals, add impulse-buy items near checkout, or train staff on upselling.",
                    "priority": "medium",
                    "category": "revenue",
                })

        elif g.goal_type == "transactions":
            if pct < expected_pct * 0.75:
                recommendations.append({
                    "emoji": "1f6d2",
                    "title": "Transaction volume below target — drive foot traffic",
                    "description": f"{current_value:.0f} transactions vs target {target:.0f}. Increase social media posting, run a door-buster deal, or extend weekend hours.",
                    "priority": "high",
                    "category": "revenue",
                })

    # Check product goals
    pgoals = (
        db.query(ProductGoal)
        .filter(ProductGoal.shop_id == shop_id, ProductGoal.period == current_month)
        .all()
    )

    underperforming = []
    for pg in pgoals:
        product = db.query(Product).filter(Product.id == pg.product_id).first()
        if not product:
            continue
        sold = (
            db.query(func.coalesce(func.sum(TransactionItem.quantity), 0))
            .join(Transaction, TransactionItem.transaction_id == Transaction.id)
            .filter(
                Transaction.shop_id == shop_id,
                TransactionItem.product_id == pg.product_id,
                Transaction.timestamp >= datetime.combine(today.replace(day=1), datetime.min.time()),
            )
            .scalar()
        ) or 0
        pct = int(sold) / pg.target_units * 100 if pg.target_units > 0 else 0
        if pct < 50:
            underperforming.append(product.name)

    if underperforming:
        recommendations.append({
            "emoji": "1f4e6",
            "title": f"{len(underperforming)} product{'s' if len(underperforming) > 1 else ''} below sales target",
            "description": f"{', '.join(underperforming[:3])} {'are' if len(underperforming) > 1 else 'is'} under 50% of target. Consider promotions, featured placement, or bundling.",
            "priority": "medium",
            "category": "products",
        })

    if not recommendations:
        recommendations.append({
            "emoji": "2705",
            "title": "All goals on track — keep up the momentum!",
            "description": "Your current performance is meeting or exceeding targets. Consider setting more ambitious goals for next month.",
            "priority": "low",
            "category": "general",
        })

    return {"recommendations": recommendations}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _calculate_progress(db: Session, shop_id: str, goal, ref_date: date) -> float:
    """Calculate current progress for a goal up to ref_date."""
    period_start, period_end = _parse_period(goal.period_key, goal.period)
    end = min(ref_date, period_end)

    if goal.goal_type == "revenue":
        result = (
            db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0))
            .filter(
                DailySnapshot.shop_id == shop_id,
                DailySnapshot.date >= period_start,
                DailySnapshot.date <= end,
            )
            .scalar()
        )
        return float(result) if result else 0.0

    elif goal.goal_type == "transactions":
        result = (
            db.query(func.coalesce(func.sum(DailySnapshot.transaction_count), 0))
            .filter(
                DailySnapshot.shop_id == shop_id,
                DailySnapshot.date >= period_start,
                DailySnapshot.date <= end,
            )
            .scalar()
        )
        return float(result) if result else 0.0

    elif goal.goal_type == "customers":
        result = (
            db.query(func.coalesce(func.sum(DailySnapshot.new_customers), 0))
            .filter(
                DailySnapshot.shop_id == shop_id,
                DailySnapshot.date >= period_start,
                DailySnapshot.date <= end,
            )
            .scalar()
        )
        return float(result) if result else 0.0

    elif goal.goal_type == "aov":
        result = (
            db.query(func.avg(DailySnapshot.avg_transaction_value))
            .filter(
                DailySnapshot.shop_id == shop_id,
                DailySnapshot.date >= period_start,
                DailySnapshot.date <= end,
            )
            .scalar()
        )
        return float(result) if result else 0.0

    return 0.0


def _parse_period(period_key: str, period_type: str):
    """Parse period key into start/end dates."""
    if period_type == "monthly":
        year, month = int(period_key[:4]), int(period_key[5:7])
        start = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end = date(year, month, last_day)
    elif period_type == "quarterly":
        year = int(period_key[:4])
        q = int(period_key[-1])
        start_month = (q - 1) * 3 + 1
        start = date(year, start_month, 1)
        end_month = start_month + 2
        _, last_day = monthrange(year, end_month)
        end = date(year, end_month, last_day)
    else:
        today = date.today()
        start = today.replace(day=1)
        _, last_day = monthrange(today.year, today.month)
        end = today.replace(day=last_day)

    return start, end
