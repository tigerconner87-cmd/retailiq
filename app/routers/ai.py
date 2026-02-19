"""AI Assistant API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User, Shop, ShopSettings, ChatMessage, DailySnapshot, Customer
from app.services.ai_assistant import chat, rewrite_email, generate_content, get_remaining_requests
from app.config import settings

from sqlalchemy import func
from datetime import date

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _get_shop(db: Session, user: User) -> Shop:
    return db.query(Shop).filter(Shop.user_id == user.id).first()


def _get_shop_context(db: Session, shop: Shop) -> dict:
    """Build context dict about the shop for AI prompts."""
    today = date.today()
    snap = (
        db.query(DailySnapshot)
        .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date == today)
        .first()
    )
    total_customers = db.query(func.count(Customer.id)).filter(Customer.shop_id == shop.id).scalar() or 0
    return {
        "shop_name": shop.name,
        "category": shop.category,
        "revenue_today": float(snap.total_revenue) if snap else 0,
        "total_customers": total_customers,
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
    """Send a message to the AI assistant."""
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

    # Get shop context and API key
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
