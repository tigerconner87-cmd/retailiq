"""AI Assistant (Sage) API endpoints."""

from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.dependencies import get_current_user, get_db
from app.models import (
    User, Shop, ShopSettings, ChatMessage, DailySnapshot, Customer,
    Product, TransactionItem, Transaction, Competitor, Review, CompetitorReview,
)
from app.services.ai_assistant import chat, rewrite_email, generate_content, get_remaining_requests
from app.config import settings

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _get_shop(db: Session, user: User) -> Shop:
    return db.query(Shop).filter(Shop.user_id == user.id).first()


def _get_shop_context(db: Session, shop: Shop) -> dict:
    """Build rich context dict about the shop for Sage AI prompts."""
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)

    # --- Today's snapshot ---
    snap = (
        db.query(DailySnapshot)
        .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date == today)
        .first()
    )
    # Yesterday's snapshot for comparison
    yesterday_snap = (
        db.query(DailySnapshot)
        .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date == today - timedelta(days=1))
        .first()
    )

    # --- 30-day revenue & transactions ---
    thirty_day_stats = (
        db.query(
            func.sum(DailySnapshot.total_revenue),
            func.sum(DailySnapshot.transaction_count),
            func.avg(DailySnapshot.total_revenue),
        )
        .filter(
            DailySnapshot.shop_id == shop.id,
            DailySnapshot.date >= thirty_days_ago,
        )
        .first()
    )
    revenue_30d = float(thirty_day_stats[0] or 0)
    transactions_30d = int(thirty_day_stats[1] or 0)
    avg_daily_revenue = float(thirty_day_stats[2] or 0)

    # --- Customer counts by segment ---
    segment_counts = dict(
        db.query(Customer.segment, func.count(Customer.id))
        .filter(Customer.shop_id == shop.id)
        .group_by(Customer.segment)
        .all()
    )
    total_customers = sum(segment_counts.values())

    # --- Top 5 products by revenue (last 30 days) ---
    top_products_q = (
        db.query(
            Product.name,
            Product.category,
            func.sum(TransactionItem.total).label("revenue"),
            func.sum(TransactionItem.quantity).label("units"),
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .filter(
            Product.shop_id == shop.id,
            Transaction.timestamp >= datetime.combine(thirty_days_ago, datetime.min.time()),
        )
        .group_by(Product.name, Product.category)
        .order_by(desc("revenue"))
        .limit(5)
        .all()
    )
    top_products = [
        {"name": p.name, "category": p.category, "revenue": float(p.revenue), "units": int(p.units)}
        for p in top_products_q
    ]

    # --- Competitors summary ---
    competitors = (
        db.query(Competitor.name, Competitor.rating, Competitor.review_count)
        .filter(Competitor.shop_id == shop.id)
        .all()
    )
    comp_list = [
        {"name": c.name, "rating": float(c.rating) if c.rating else 0, "reviews": c.review_count or 0}
        for c in competitors
    ]

    # --- Own reviews summary ---
    own_reviews = (
        db.query(
            func.count(Review.id),
            func.avg(Review.rating),
        )
        .filter(Review.shop_id == shop.id, Review.is_own_shop == True)
        .first()
    )
    own_review_count = int(own_reviews[0] or 0)
    own_avg_rating = round(float(own_reviews[1] or 0), 1)

    # --- Recent negative reviews (last 7 days) ---
    recent_neg = (
        db.query(Review.text, Review.rating)
        .filter(
            Review.shop_id == shop.id,
            Review.is_own_shop == True,
            Review.rating <= 3,
            Review.review_date >= datetime.combine(seven_days_ago, datetime.min.time()),
        )
        .limit(3)
        .all()
    )
    neg_reviews = [{"text": r.text[:100] if r.text else "", "rating": r.rating} for r in recent_neg]

    # --- At-risk & lost customers ---
    at_risk_count = segment_counts.get("at_risk", 0)
    lost_count = segment_counts.get("lost", 0)
    vip_count = segment_counts.get("vip", 0)

    return {
        "shop_name": shop.name,
        "category": shop.category,
        "city": shop.city or "",
        "revenue_today": float(snap.total_revenue) if snap else 0,
        "transactions_today": int(snap.transaction_count) if snap else 0,
        "revenue_yesterday": float(yesterday_snap.total_revenue) if yesterday_snap else 0,
        "revenue_30d": revenue_30d,
        "transactions_30d": transactions_30d,
        "avg_daily_revenue": round(avg_daily_revenue, 2),
        "total_customers": total_customers,
        "vip_customers": vip_count,
        "at_risk_customers": at_risk_count,
        "lost_customers": lost_count,
        "top_products": top_products,
        "competitors": comp_list,
        "own_review_count": own_review_count,
        "own_avg_rating": own_avg_rating,
        "recent_negative_reviews": neg_reviews,
    }


def _get_api_key(db: Session, shop: Shop) -> str:
    """Get Anthropic API key from settings or env."""
    s = db.query(ShopSettings).filter(ShopSettings.shop_id == shop.id).first()
    key = (s.anthropic_api_key if s and hasattr(s, 'anthropic_api_key') and s.anthropic_api_key else "") or settings.ANTHROPIC_API_KEY
    return key or ""


@router.post("/chat")
async def ai_chat(
    message: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message to the Sage AI assistant."""
    shop = _get_shop(db, user)
    if not shop:
        return {"response": "Please complete onboarding first.", "source": "error", "remaining": 0}

    # Load recent conversation history
    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.shop_id == shop.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    history = [{"role": h.role, "content": h.content} for h in reversed(history_rows)]

    # Get rich shop context and API key
    context = _get_shop_context(db, shop)
    api_key = _get_api_key(db, shop)

    # Call AI service
    result = await chat(
        user_id=user.id,
        message=message,
        conversation_history=history,
        api_key=api_key,
        shop_context=context,
    )

    # Save conversation to database
    db.add(ChatMessage(shop_id=shop.id, role="user", content=message))
    db.add(ChatMessage(shop_id=shop.id, role="assistant", content=result["response"]))
    db.commit()

    return result


@router.post("/rewrite-email")
async def ai_rewrite_email(
    subject: str = Body(...),
    body: str = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rewrite an email campaign with AI."""
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "Shop not found"}
    api_key = _get_api_key(db, shop)
    return await rewrite_email(subject=subject, body=body, api_key=api_key, shop_name=shop.name)


@router.post("/generate-content")
async def ai_generate_content(
    content_type: str = Body(...),
    prompt: str = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate marketing content with AI."""
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "Shop not found"}
    api_key = _get_api_key(db, shop)
    return await generate_content(content_type=content_type, prompt=prompt, api_key=api_key, shop_name=shop.name)


@router.get("/history")
def ai_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get AI conversation history."""
    shop = _get_shop(db, user)
    if not shop:
        return {"messages": []}
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.shop_id == shop.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "messages": [
            {"role": r.role, "content": r.content, "created_at": r.created_at.isoformat()}
            for r in reversed(rows)
        ],
        "remaining": get_remaining_requests(user.id),
    }


@router.delete("/history")
def ai_clear_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Clear AI conversation history."""
    shop = _get_shop(db, user)
    if not shop:
        return {"detail": "ok"}
    db.query(ChatMessage).filter(ChatMessage.shop_id == shop.id).delete()
    db.commit()
    return {"detail": "Conversation history cleared"}
