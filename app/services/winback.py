"""Win-Back Campaign service — customer retention and re-engagement."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.models import (
    Customer, Transaction, TransactionItem, Product, WinBackCampaign, new_id,
)


def get_winback_overview(db: Session, shop_id: str):
    """Get customer status overview for win-back page."""
    total = db.query(func.count(Customer.id)).filter(Customer.shop_id == shop_id).scalar() or 0
    active = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.segment.in_(["regular", "vip"])
    ).scalar() or 0
    at_risk = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.segment == "at_risk"
    ).scalar() or 0
    lost = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.segment == "lost"
    ).scalar() or 0

    # "Won back" = customers who were at_risk/lost but came back recently
    # Approximate: customers with > 2 visits, last seen in past 14 days, avg gap > 30 days
    two_weeks_ago = datetime.utcnow() - timedelta(days=14)
    won_back = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id,
        Customer.visit_count > 2,
        Customer.last_seen >= two_weeks_ago,
        Customer.avg_days_between_visits > 30,
    ).scalar() or 0

    return {
        "total_customers": total,
        "active": active,
        "at_risk": at_risk,
        "lost": lost,
        "won_back": won_back,
        "segments": {
            "active": active,
            "at_risk": at_risk,
            "lost": lost,
            "won_back": won_back,
        },
    }


def get_at_risk_customers(db: Session, shop_id: str, sort_by: str = "days_since"):
    """Get at-risk and lost customers with details."""
    customers = (
        db.query(Customer)
        .filter(
            Customer.shop_id == shop_id,
            Customer.segment.in_(["at_risk", "lost"]),
        )
        .all()
    )

    now = datetime.utcnow()
    results = []
    for c in customers:
        days_since = (now - c.last_seen).days if c.last_seen else 999

        # Get favorite product
        fav_product = None
        fav = (
            db.query(Product.name, func.count(TransactionItem.id).label("cnt"))
            .join(TransactionItem, TransactionItem.product_id == Product.id)
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .filter(Transaction.customer_id == c.id)
            .group_by(Product.name)
            .order_by(desc("cnt"))
            .first()
        )
        if fav:
            fav_product = fav[0]

        results.append({
            "id": c.id,
            "email": c.email or f"Customer #{c.id[:8]}",
            "segment": c.segment,
            "last_seen": c.last_seen.isoformat() if c.last_seen else None,
            "days_since_visit": days_since,
            "total_spent": float(c.total_spent) if c.total_spent else 0,
            "visit_count": c.visit_count or 0,
            "favorite_product": fav_product or "N/A",
            "avg_order_value": float(c.avg_order_value) if c.avg_order_value else 0,
        })

    # Sort
    if sort_by == "days_since":
        results.sort(key=lambda x: x["days_since_visit"], reverse=True)
    elif sort_by == "total_spent":
        results.sort(key=lambda x: x["total_spent"], reverse=True)
    elif sort_by == "visit_count":
        results.sort(key=lambda x: x["visit_count"], reverse=True)

    return {"customers": results[:50], "total": len(results)}


def get_campaign_templates():
    """Return the 3 win-back campaign templates."""
    return {
        "templates": [
            {
                "id": "gentle_nudge",
                "name": "The Gentle Nudge",
                "emoji": "👋",
                "description": "A friendly reminder for customers who haven't visited in 30-60 days. No discount needed — just let them know you miss them.",
                "subject": "We miss you! Come say hi 👋",
                "body": "Hi {name},\n\nIt's been a while since we've seen you at {shop_name}! We wanted you to know we've got some exciting new arrivals that we think you'll love.\n\nStop by this week and check out what's new. We'd love to catch up!\n\nSee you soon,\n{shop_name} Team",
                "discount": 0,
                "best_for": "30-60 days inactive",
                "expected_response": "15-25%",
                "tone": "warm",
            },
            {
                "id": "sweet_deal",
                "name": "The Sweet Deal",
                "emoji": "🎁",
                "description": "A personalized discount for customers inactive 60-90 days. Include their favorite product category for maximum impact.",
                "subject": "A special {discount}% off, just for you 🎁",
                "body": "Hi {name},\n\nWe noticed it's been a while, and we wanted to sweeten things up! Here's an exclusive {discount}% off your next visit.\n\nWe know you love our {favorite_product} — and we've got even more options waiting for you.\n\nUse code: COMEBACK{discount} at checkout.\nValid for 7 days.\n\nCome back and treat yourself!\n{shop_name} Team",
                "discount": 15,
                "best_for": "60-90 days inactive",
                "expected_response": "20-35%",
                "tone": "generous",
            },
            {
                "id": "last_chance",
                "name": "The Last Chance",
                "emoji": "⏰",
                "description": "A compelling offer for customers inactive 90+ days. Create urgency with a bigger discount and time limit.",
                "subject": "We want you back — here's {discount}% off ⏰",
                "body": "Hi {name},\n\nIt's been too long! We genuinely miss having you as part of the {shop_name} family.\n\nAs a special gesture, here's {discount}% off your entire purchase — but hurry, this offer expires in 48 hours!\n\nUse code: MISSYOU{discount}\n\nWe've made some amazing changes since you last visited, and we think you'll be pleasantly surprised.\n\nHope to see you soon!\n{shop_name} Team",
                "discount": 25,
                "best_for": "90+ days inactive",
                "expected_response": "10-20%",
                "tone": "urgent",
            },
        ]
    }


def get_campaign_history(db: Session, shop_id: str):
    """Get past win-back campaigns."""
    campaigns = (
        db.query(WinBackCampaign)
        .filter(WinBackCampaign.shop_id == shop_id)
        .order_by(desc(WinBackCampaign.created_at))
        .limit(20)
        .all()
    )
    return {
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "template_type": c.template_type,
                "customers_targeted": c.customers_targeted,
                "discount_percentage": c.discount_percentage,
                "status": c.status,
                "sent_at": c.sent_at.isoformat() if c.sent_at else None,
                "open_rate": c.open_rate,
                "response_rate": c.response_rate,
                "revenue_recovered": float(c.revenue_recovered) if c.revenue_recovered else 0,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in campaigns
        ]
    }


def get_automation_settings(db: Session, shop_id: str):
    """Get win-back automation settings (defaults for now)."""
    return {
        "enabled": False,
        "gentle_nudge_days": 30,
        "sweet_deal_days": 60,
        "last_chance_days": 90,
        "sweet_deal_discount": 15,
        "last_chance_discount": 25,
        "max_emails_per_day": 10,
    }
