"""Daily Briefing service — generates a morning briefing for the shop owner."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Shop, Customer, Competitor, CompetitorReview, DailySnapshot,
    Goal, RevenueGoal, Review, Transaction, Alert,
)


def get_briefing(db: Session, shop_id: str, user_full_name: str):
    """Build the daily briefing data."""
    today = datetime.utcnow().date()

    # If no recent snapshot data, use the latest available date as reference
    latest_snap = db.query(func.max(DailySnapshot.date)).filter(
        DailySnapshot.shop_id == shop_id,
    ).scalar()
    if latest_snap and latest_snap < today - timedelta(days=1):
        today = latest_snap + timedelta(days=1)  # Pretend "today" is the day after last data

    yesterday = today - timedelta(days=1)
    same_day_last_week = today - timedelta(days=7)
    month_start = today.replace(day=1)

    hour = datetime.utcnow().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    first_name = user_full_name.split()[0] if user_full_name else "there"

    # ── Numbers Today (yesterday's actuals) ──
    yesterday_snap = (
        db.query(DailySnapshot)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date == yesterday)
        .first()
    )
    last_week_snap = (
        db.query(DailySnapshot)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date == same_day_last_week)
        .first()
    )

    yesterday_rev = float(yesterday_snap.total_revenue) if yesterday_snap else 0
    yesterday_txn = yesterday_snap.transaction_count if yesterday_snap else 0
    yesterday_aov = float(yesterday_snap.avg_transaction_value) if yesterday_snap else 0

    last_week_rev = float(last_week_snap.total_revenue) if last_week_snap else 0
    last_week_txn = last_week_snap.transaction_count if last_week_snap else 0

    rev_change = round(((yesterday_rev - last_week_rev) / last_week_rev * 100) if last_week_rev > 0 else 0, 1)
    txn_change = round(((yesterday_txn - last_week_txn) / last_week_txn * 100) if last_week_txn > 0 else 0, 1)

    # Running monthly total
    monthly_rev = (
        db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0))
        .filter(
            DailySnapshot.shop_id == shop_id,
            DailySnapshot.date >= month_start,
            DailySnapshot.date <= yesterday,
        )
        .scalar()
    )
    monthly_rev = float(monthly_rev) if monthly_rev else 0

    # Monthly goal (use the month of the reference date)
    current_month_str = yesterday.strftime("%Y-%m")
    rev_goal = (
        db.query(RevenueGoal)
        .filter(RevenueGoal.shop_id == shop_id, RevenueGoal.month == current_month_str)
        .first()
    )
    goal_target = float(rev_goal.target_amount) if rev_goal else 0
    goal_pct = round((monthly_rev / goal_target * 100) if goal_target > 0 else 0, 1)

    numbers = {
        "yesterday_revenue": yesterday_rev,
        "yesterday_transactions": yesterday_txn,
        "yesterday_aov": yesterday_aov,
        "rev_change_vs_last_week": rev_change,
        "txn_change_vs_last_week": txn_change,
        "monthly_total": monthly_rev,
        "monthly_goal": goal_target,
        "goal_progress_pct": goal_pct,
    }

    # ── Top 3 Things To Do ──
    todos = _generate_todos(db, shop_id, yesterday_snap, monthly_rev, goal_target, ref_today=today)

    # ── Competitor Watch ──
    competitors = db.query(Competitor).filter(Competitor.shop_id == shop_id).all()
    comp_watch = []
    week_ago = datetime.utcnow() - timedelta(days=7)
    for comp in competitors[:5]:
        new_reviews = (
            db.query(func.count(CompetitorReview.id))
            .filter(
                CompetitorReview.competitor_id == comp.id,
                CompetitorReview.created_at >= week_ago,
            )
            .scalar()
        )
        neg_reviews = (
            db.query(func.count(CompetitorReview.id))
            .filter(
                CompetitorReview.competitor_id == comp.id,
                CompetitorReview.created_at >= week_ago,
                CompetitorReview.sentiment == "negative",
            )
            .scalar()
        )
        comp_watch.append({
            "name": comp.name,
            "rating": float(comp.rating) if comp.rating else None,
            "new_reviews": new_reviews or 0,
            "negative_reviews": neg_reviews or 0,
        })

    # ── This Week's Marketing ──
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    today_name = day_names[today.weekday()]
    marketing_tips = _get_marketing_tip(today_name, db, shop_id)

    # ── Customer Pulse ──
    week_ago_date = today - timedelta(days=7)
    new_custs_7d = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.shop_id == shop_id,
            Customer.first_seen >= datetime.combine(week_ago_date, datetime.min.time()),
        )
        .scalar()
    ) or 0

    at_risk_count = (
        db.query(func.count(Customer.id))
        .filter(Customer.shop_id == shop_id, Customer.segment == "at_risk")
        .scalar()
    ) or 0

    vip_count = (
        db.query(func.count(Customer.id))
        .filter(Customer.shop_id == shop_id, Customer.segment == "vip")
        .scalar()
    ) or 0

    total_custs = (
        db.query(func.count(Customer.id))
        .filter(Customer.shop_id == shop_id)
        .scalar()
    ) or 0

    customer_pulse = {
        "new_customers_7d": new_custs_7d,
        "at_risk_count": at_risk_count,
        "vip_count": vip_count,
        "total_customers": total_custs,
    }

    return {
        "greeting": greeting,
        "first_name": first_name,
        "date": today.strftime("%A, %B %d, %Y"),
        "numbers": numbers,
        "todos": todos,
        "competitor_watch": comp_watch,
        "marketing": marketing_tips,
        "customer_pulse": customer_pulse,
    }


def _generate_todos(db, shop_id, yesterday_snap, monthly_rev, goal_target, ref_today=None):
    """Generate top 3 prioritized action items."""
    todos = []

    # Check if behind on goal
    today = ref_today or datetime.utcnow().date()
    days_in_month = 30
    days_passed = today.day
    expected_pct = (days_passed / days_in_month) * 100
    actual_pct = (monthly_rev / goal_target * 100) if goal_target > 0 else 100

    if goal_target > 0 and actual_pct < expected_pct - 10:
        daily_needed = (goal_target - monthly_rev) / max(1, days_in_month - days_passed)
        todos.append({
            "title": f"Push for ${daily_needed:,.0f}/day to hit your monthly goal",
            "description": f"You're at {actual_pct:.0f}% of your ${goal_target:,.0f} goal. Consider running a flash promotion or featuring your best sellers.",
            "priority": "high",
            "impact": f"+${daily_needed:,.0f}/day",
            "link": "goals",
        })

    # Check for at-risk customers
    at_risk = (
        db.query(func.count(Customer.id))
        .filter(Customer.shop_id == shop_id, Customer.segment == "at_risk")
        .scalar()
    ) or 0
    if at_risk > 0:
        todos.append({
            "title": f"Reach out to {at_risk} at-risk customers",
            "description": "These customers haven't visited recently. A personalized email or special offer could bring them back.",
            "priority": "high" if at_risk > 5 else "medium",
            "impact": f"Save {at_risk} customers",
            "link": "winback",
        })

    # Check for unread reviews
    unread_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.shop_id == shop_id, Alert.is_read.is_(False))
        .scalar()
    ) or 0
    if unread_alerts > 0:
        todos.append({
            "title": f"Review {unread_alerts} unread alert{'s' if unread_alerts != 1 else ''}",
            "description": "Stay on top of your alerts to catch important trends and issues early.",
            "priority": "medium",
            "impact": "Stay informed",
            "link": "alerts",
        })

    # Check recent negative reviews
    week_ago = datetime.utcnow() - timedelta(days=7)
    neg_reviews = (
        db.query(func.count(Review.id))
        .filter(
            Review.shop_id == shop_id,
            Review.rating <= 2,
            Review.created_at >= week_ago,
            Review.response_text.is_(None),
        )
        .scalar()
    ) or 0
    if neg_reviews > 0:
        todos.append({
            "title": f"Respond to {neg_reviews} negative review{'s' if neg_reviews != 1 else ''}",
            "description": "Responding to negative reviews shows customers you care and can improve your rating.",
            "priority": "high",
            "impact": "Protect reputation",
            "link": "reviews",
        })

    # If we have fewer than 3, add general tips
    if len(todos) < 3:
        todos.append({
            "title": "Check your marketing content calendar",
            "description": "AI-generated social media posts and email campaigns are ready for you to use this week.",
            "priority": "low",
            "impact": "Grow reach",
            "link": "marketing",
        })

    if len(todos) < 3:
        todos.append({
            "title": "Review your competitor landscape",
            "description": "See how your competitors are performing and find opportunities to differentiate.",
            "priority": "low",
            "impact": "Stay competitive",
            "link": "competitors",
        })

    # Sort by priority and take top 3
    priority_order = {"high": 0, "medium": 1, "low": 2}
    todos.sort(key=lambda t: priority_order.get(t["priority"], 2))
    return todos[:3]


def _get_marketing_tip(day_name, db, shop_id):
    """Get today's marketing suggestion."""
    tips = {
        "Monday": {
            "title": "Start the Week Strong",
            "content": "Post a 'New Week, New Deals' story on Instagram. Highlight your top-selling product from last week with a fresh angle.",
            "platform": "instagram",
        },
        "Tuesday": {
            "title": "Customer Spotlight Tuesday",
            "content": "Feature a loyal customer story or testimonial. Tag them (with permission) to boost engagement and social proof.",
            "platform": "instagram",
        },
        "Wednesday": {
            "title": "Mid-Week Email Blast",
            "content": "Send a mid-week email to your subscriber list with a 'Hump Day Special' or new product highlight.",
            "platform": "email",
        },
        "Thursday": {
            "title": "Behind the Scenes",
            "content": "Share a behind-the-scenes look at your store. Show new inventory, your team, or how you prepare for the weekend rush.",
            "platform": "instagram",
        },
        "Friday": {
            "title": "Weekend Preview",
            "content": "Post about weekend hours, special events, or limited-time offers to drive weekend foot traffic.",
            "platform": "facebook",
        },
        "Saturday": {
            "title": "Live From the Shop",
            "content": "Go live on Instagram or Facebook showing the weekend energy. Feature products, customers, and any in-store events.",
            "platform": "instagram",
        },
        "Sunday": {
            "title": "Week in Review",
            "content": "Share your wins from the week: best sellers, happy customers, and what's coming next week. Build anticipation!",
            "platform": "facebook",
        },
    }
    return tips.get(day_name, tips["Monday"])
