"""AI Recommendations Engine for Forge.

Analyzes all available data to generate 5-7 daily action items across categories:
Revenue, Customers, Products, Marketing, Operations, Competitors.

Each recommendation has: title, description, category, priority, estimated_impact,
action_steps, emoji, and is stored in the database for tracking.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from collections import defaultdict
import statistics

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Customer, Competitor, CompetitorSnapshot, DailySnapshot, HourlySnapshot,
    Product, Recommendation, Review, Shop, Transaction, TransactionItem,
)


def _today() -> date:
    return date.today()


def generate_recommendations(db: Session, shop_id: str) -> list[dict]:
    """Generate fresh recommendations and store them in the database.

    Marks old active recommendations as dismissed, then creates new ones.
    """
    # Dismiss old active recommendations
    db.query(Recommendation).filter(
        Recommendation.shop_id == shop_id,
        Recommendation.status == "active",
    ).update({"status": "dismissed"})
    db.flush()

    actions: list[dict] = []

    # Gather all recommendation types
    actions.extend(_revenue_recommendations(db, shop_id))
    actions.extend(_customer_recommendations(db, shop_id))
    actions.extend(_product_recommendations(db, shop_id))
    actions.extend(_marketing_recommendations(db, shop_id))
    actions.extend(_operations_recommendations(db, shop_id))
    actions.extend(_competitor_recommendations(db, shop_id))

    # Sort by priority and take top 7
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    actions.sort(key=lambda a: priority_order.get(a.get("priority", "medium"), 2))
    actions = actions[:7]

    # Store in database
    for a in actions:
        rec = Recommendation(
            shop_id=shop_id,
            title=a["title"],
            description=a["description"],
            category=a["category"],
            priority=a["priority"],
            estimated_impact=a.get("estimated_impact"),
            action_steps=a.get("action_steps"),
            emoji=a.get("emoji", "1f4a1"),
            status="active",
        )
        db.add(rec)

    db.commit()
    return actions


def _revenue_recommendations(db: Session, shop_id: str) -> list[dict]:
    """Revenue-focused recommendations."""
    today = _today()
    actions = []

    # 1. Trending product — compare last 7d vs prior 7d
    week_ago = today - timedelta(days=7)
    two_weeks_ago = today - timedelta(days=14)

    this_week = dict(
        db.query(
            Product.name,
            func.coalesce(func.sum(TransactionItem.total), 0),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(Product.shop_id == shop_id, func.date(Transaction.timestamp) >= week_ago)
        .group_by(Product.name)
        .all()
    )
    last_week = dict(
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
    for name, curr in this_week.items():
        prev = float(last_week.get(name, 0))
        curr_f = float(curr)
        if prev > 30:
            pct = (curr_f - prev) / prev * 100
            if pct > best_growth_pct:
                best_growth_pct = pct
                best_growth_name = name

    if best_growth_name and best_growth_pct > 15:
        actions.append({
            "category": "revenue",
            "priority": "high",
            "emoji": "1f4c8",
            "title": f"{best_growth_name} sales are up {best_growth_pct:.0f}% this week",
            "description": "Feature this product in your window display and social media to ride the momentum.",
            "estimated_impact": f"Could add ${best_growth_pct * 5:.0f}/week in additional revenue",
            "action_steps": [
                "Move product to front display",
                "Post product photo on Instagram",
                "Consider bundling with complementary items",
            ],
        })

    # 2. Weakest day promotion
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    snaps = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= today - timedelta(days=28))
        .all()
    )
    day_totals: dict[int, list[float]] = defaultdict(list)
    for snap in snaps:
        day_totals[snap.date.weekday()].append(float(snap.total_revenue))

    if day_totals:
        weakest_dow = min(day_totals, key=lambda d: statistics.mean(day_totals[d]) if day_totals[d] else 0)
        weakest_avg = statistics.mean(day_totals[weakest_dow]) if day_totals[weakest_dow] else 0
        all_avgs = [statistics.mean(v) for v in day_totals.values() if v]
        overall_avg = statistics.mean(all_avgs) if all_avgs else 0
        if overall_avg > 0 and weakest_avg < overall_avg * 0.85:
            gap = overall_avg - weakest_avg
            actions.append({
                "category": "revenue",
                "priority": "medium",
                "emoji": "1f4b0",
                "title": f"{day_names[weakest_dow]} is your weakest day (${weakest_avg:,.0f} avg)",
                "description": f"That's {((overall_avg - weakest_avg) / overall_avg * 100):.0f}% below your daily average. Try a {day_names[weakest_dow]}-only promotion.",
                "estimated_impact": f"Closing this gap could add ${gap * 4:,.0f}/month",
                "action_steps": [
                    f"Create a '{day_names[weakest_dow]} Special' promotion",
                    "Offer 10-15% discount on select items",
                    "Promote on social media the day before",
                ],
            })

    # 3. Revenue milestone or drop alert
    rev_today_row = db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0)).filter(
        DailySnapshot.shop_id == shop_id, DailySnapshot.date == today
    ).scalar()
    rev_yesterday_row = db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0)).filter(
        DailySnapshot.shop_id == shop_id, DailySnapshot.date == today - timedelta(days=1)
    ).scalar()
    rev_today = float(rev_today_row) if rev_today_row else 0
    rev_yesterday = float(rev_yesterday_row) if rev_yesterday_row else 0

    if rev_yesterday > 0 and rev_today > 0:
        change = (rev_today - rev_yesterday) / rev_yesterday * 100
        if change < -20:
            actions.append({
                "category": "revenue",
                "priority": "critical",
                "emoji": "1f6a8",
                "title": f"Revenue dropped {abs(change):.0f}% compared to yesterday",
                "description": f"Today: ${rev_today:,.0f} vs Yesterday: ${rev_yesterday:,.0f}. Investigate possible causes.",
                "estimated_impact": f"${abs(rev_today - rev_yesterday):,.0f} potential daily loss",
                "action_steps": [
                    "Check if any external events affected foot traffic",
                    "Review if a competitor ran a promotion",
                    "Consider running a flash sale to recover",
                ],
            })

    return actions


def _customer_recommendations(db: Session, shop_id: str) -> list[dict]:
    """Customer-focused recommendations."""
    today = _today()
    actions = []

    # 1. Lapsed repeat customers
    thirty_ago = datetime.combine(today - timedelta(days=30), datetime.min.time())
    lapsed = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        Customer.visit_count > 1,
        Customer.last_seen < thirty_ago,
    ).scalar() or 0

    if lapsed > 0:
        est_rev = lapsed * 45  # Avg order value estimate
        actions.append({
            "category": "customers",
            "priority": "high",
            "emoji": "1f4e9",
            "title": f"{lapsed} repeat customers haven't returned in 30+ days",
            "description": "Send a personalized win-back email with a 15% discount code to re-engage them.",
            "estimated_impact": f"Could recover ${est_rev:,}/month in revenue",
            "action_steps": [
                "Export at-risk customer list",
                "Create personalized email with 15% off code",
                "Follow up with non-responders after 7 days",
            ],
        })

    # 2. VIP recognition
    vip_count = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.segment == "vip"
    ).scalar() or 0
    if vip_count > 0:
        actions.append({
            "category": "customers",
            "priority": "medium",
            "emoji": "1f451",
            "title": f"Reward your {vip_count} VIP customers",
            "description": "Your top spenders drive a disproportionate share of revenue. Show them appreciation.",
            "estimated_impact": "VIP retention increases revenue by 25-30%",
            "action_steps": [
                "Send a personalized thank-you note",
                "Offer early access to new arrivals",
                "Consider a VIP-only shopping event",
            ],
        })

    # 3. Churn prevention
    at_risk = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.segment == "at_risk"
    ).scalar() or 0
    if at_risk > 5:
        actions.append({
            "category": "customers",
            "priority": "high",
            "emoji": "26a0",
            "title": f"{at_risk} customers are at risk of churning",
            "description": "These customers' visit frequency has dropped significantly. Act now before they leave.",
            "estimated_impact": f"Preventing churn could save ${at_risk * 120:,}/year",
            "action_steps": [
                "Review the at-risk customer list",
                "Send a 'We miss you' campaign",
                "Offer a compelling incentive to return",
            ],
        })

    return actions


def _product_recommendations(db: Session, shop_id: str) -> list[dict]:
    """Product-focused recommendations."""
    today = _today()
    actions = []

    # 1. Slow movers
    fourteen_ago = datetime.combine(today - timedelta(days=14), datetime.min.time())
    all_products = db.query(Product).filter(Product.shop_id == shop_id, Product.is_active.is_(True)).all()
    recent_sellers = set(
        r[0] for r in db.query(TransactionItem.product_id)
        .join(Transaction)
        .filter(Transaction.shop_id == shop_id, Transaction.timestamp >= fourteen_ago)
        .distinct()
        .all()
    )
    slow = [p for p in all_products if p.id not in recent_sellers and p.category != "Gift Cards"]

    if len(slow) >= 3:
        names = ", ".join(p.name for p in slow[:3])
        actions.append({
            "category": "products",
            "priority": "medium",
            "emoji": "1f4e6",
            "title": f"{len(slow)} products haven't sold in 14+ days",
            "description": f"Including: {names}. Consider discounting or bundling these items.",
            "estimated_impact": f"Clearance could free up ${sum(float(p.price) for p in slow):,.0f} in inventory value",
            "action_steps": [
                "Markdown slow movers by 20-30%",
                "Bundle with popular items",
                "Move to a more visible display location",
            ],
        })

    # 2. Stock alert for best sellers
    best = (
        db.query(Product.name, Product.stock_quantity, func.sum(TransactionItem.quantity).label("sold"))
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(Product.shop_id == shop_id, Transaction.timestamp >= fourteen_ago)
        .group_by(Product.name, Product.stock_quantity)
        .order_by(func.sum(TransactionItem.quantity).desc())
        .limit(5)
        .all()
    )
    low_stock = [b for b in best if b.stock_quantity and b.stock_quantity < 20]
    if low_stock:
        actions.append({
            "category": "products",
            "priority": "high",
            "emoji": "1f4cb",
            "title": f"Restock alert: {low_stock[0].name} running low",
            "description": f"Only {low_stock[0].stock_quantity} units left and it's selling {int(low_stock[0].sold)} per 2 weeks.",
            "estimated_impact": "Stockouts on best sellers cost 15-20% in lost revenue",
            "action_steps": [
                "Place reorder with supplier immediately",
                "Consider ordering extra for seasonal demand",
            ],
        })

    return actions


def _marketing_recommendations(db: Session, shop_id: str) -> list[dict]:
    """Marketing-focused recommendations."""
    today = _today()
    actions = []

    # Best posting time
    peak = (
        db.query(HourlySnapshot.hour, func.avg(HourlySnapshot.transaction_count).label("avg_tx"))
        .filter(HourlySnapshot.shop_id == shop_id, HourlySnapshot.date >= today - timedelta(days=14))
        .group_by(HourlySnapshot.hour)
        .order_by(func.avg(HourlySnapshot.transaction_count).desc())
        .first()
    )
    if peak:
        post_hour = max(9, peak.hour - 2)  # Post 2 hours before peak
        label = f"{post_hour % 12 or 12}{'pm' if post_hour >= 12 else 'am'}"
        actions.append({
            "category": "marketing",
            "priority": "low",
            "emoji": "1f4f1",
            "title": f"Best time to post on social media: {label}",
            "description": "Post 2 hours before your peak traffic to capture customers planning their visit.",
            "estimated_impact": "Social posts at peak times get 3x more engagement",
            "action_steps": [
                f"Schedule daily social posts for {label}",
                "Share new arrivals and customer favorites",
                "Use location tags and relevant hashtags",
            ],
        })

    # Seasonal suggestion
    month = today.month
    if month in [10, 11]:
        actions.append({
            "category": "marketing",
            "priority": "medium",
            "emoji": "1f384",
            "title": "Holiday season is approaching — plan your campaigns",
            "description": "Nov-Dec typically sees 25-40% revenue increase. Make sure you're ready.",
            "estimated_impact": "Well-planned holiday campaigns can boost revenue by 35%",
            "action_steps": [
                "Plan holiday window display",
                "Create gift guide content for social media",
                "Stock up on gift-ready items and gift cards",
                "Schedule Black Friday / holiday sale",
            ],
        })

    return actions


def _operations_recommendations(db: Session, shop_id: str) -> list[dict]:
    """Operations-focused recommendations."""
    today = _today()
    actions = []

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
            "category": "operations",
            "priority": "medium",
            "emoji": "23f0",
            "title": f"Peak hour is {label} — ensure you're fully staffed",
            "description": f"Average revenue at {label} is ${float(peak.avg_rev):,.0f}. Make sure your best team is on the floor.",
            "estimated_impact": "Proper peak staffing increases conversion by 15-20%",
            "action_steps": [
                f"Schedule your strongest salespeople at {label}",
                "Ensure all displays are stocked before peak",
                "Consider adding a greeter during peak hours",
            ],
        })

    return actions


def _competitor_recommendations(db: Session, shop_id: str) -> list[dict]:
    """Competitor-focused recommendations."""
    actions = []

    # Check for competitor rating drops
    competitors = db.query(Competitor).filter(Competitor.shop_id == shop_id).all()
    for comp in competitors:
        snaps = (
            db.query(CompetitorSnapshot)
            .filter(CompetitorSnapshot.competitor_id == comp.id)
            .order_by(CompetitorSnapshot.date.desc())
            .limit(4)
            .all()
        )
        if len(snaps) >= 2:
            current = float(snaps[0].rating) if snaps[0].rating else 0
            previous = float(snaps[1].rating) if snaps[1].rating else 0
            if previous > 0 and current < previous - 0.3:
                actions.append({
                    "category": "competitors",
                    "priority": "medium",
                    "emoji": "1f50d",
                    "title": f"{comp.name} dropped to {current:.1f} stars",
                    "description": f"Down from {previous:.1f}. Their customers may be looking for alternatives — this is your chance.",
                    "estimated_impact": "Competitor drops create a 10-15% opportunity window",
                    "action_steps": [
                        f"Run a targeted campaign near {comp.address or 'their location'}",
                        "Highlight your strengths in areas where they're getting complaints",
                        "Consider a special offer for new customers",
                    ],
                })
                break  # One competitor rec is enough

    # Negative review response
    neg_reviews = db.query(func.count(Review.id)).filter(
        Review.shop_id == shop_id,
        Review.is_own_shop.is_(True),
        Review.rating <= 2,
        Review.response_text.is_(None),
    ).scalar() or 0

    if neg_reviews > 0:
        actions.append({
            "category": "competitors",
            "priority": "high",
            "emoji": "2b50",
            "title": f"{neg_reviews} negative reviews need a response",
            "description": "Responding to negative reviews within 24 hours improves your rating by up to 0.3 stars.",
            "estimated_impact": "Unanswered negative reviews cost ~30 potential customers each",
            "action_steps": [
                "Go to Reviews page and respond to each negative review",
                "Acknowledge the issue and offer to make it right",
                "Keep responses professional and empathetic",
            ],
        })

    return actions
