"""AI Assistant (Sage) API endpoints with streaming support."""

import json
import logging
import os
import re
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract

from app.dependencies import get_current_user, get_db
from app.models import (
    User, Shop, ShopSettings, ChatMessage, DailySnapshot, Customer,
    Product, TransactionItem, Transaction, Competitor, Review,
    RevenueGoal, HourlySnapshot, Goal, ProductGoal, Agent, AgentTask,
    StrategyNote,
)
from app.services.ai_assistant import (
    chat, chat_stream, rewrite_email, generate_content,
    get_remaining_requests, test_connection, build_system_prompt,
)
from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _get_shop(db: Session, user: User) -> Shop:
    return db.query(Shop).filter(Shop.user_id == user.id).first()


def _get_shop_context(db: Session, shop: Shop, user: User) -> dict:
    """Build rich context dict with ALL shop data for Sage AI prompts."""
    today = date.today()
    now = datetime.now()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)
    first_of_month = today.replace(day=1)
    first_of_last_month = (first_of_month - timedelta(days=1)).replace(day=1)

    # ── Today's & yesterday's snapshot ──
    snap = (
        db.query(DailySnapshot)
        .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date == today)
        .first()
    )
    yesterday_snap = (
        db.query(DailySnapshot)
        .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date == today - timedelta(days=1))
        .first()
    )

    # ── This month revenue & transactions ──
    month_stats = (
        db.query(
            func.sum(DailySnapshot.total_revenue),
            func.sum(DailySnapshot.transaction_count),
            func.avg(DailySnapshot.total_revenue),
        )
        .filter(
            DailySnapshot.shop_id == shop.id,
            DailySnapshot.date >= first_of_month,
        )
        .first()
    )
    revenue_month = float(month_stats[0] or 0)
    transactions_month = int(month_stats[1] or 0)
    avg_daily_revenue = float(month_stats[2] or 0)

    # ── Last month revenue ──
    last_month_stats = (
        db.query(func.sum(DailySnapshot.total_revenue))
        .filter(
            DailySnapshot.shop_id == shop.id,
            DailySnapshot.date >= first_of_last_month,
            DailySnapshot.date < first_of_month,
        )
        .first()
    )
    revenue_last_month = float(last_month_stats[0] or 0)

    # ── Month-over-month change ──
    mom_change = 0.0
    if revenue_last_month > 0:
        mom_change = ((revenue_month - revenue_last_month) / revenue_last_month) * 100

    # ── Best & worst day this month ──
    best_day_row = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date >= first_of_month)
        .order_by(desc(DailySnapshot.total_revenue))
        .first()
    )
    worst_day_row = (
        db.query(DailySnapshot.date, DailySnapshot.total_revenue)
        .filter(
            DailySnapshot.shop_id == shop.id,
            DailySnapshot.date >= first_of_month,
            DailySnapshot.total_revenue > 0,
        )
        .order_by(DailySnapshot.total_revenue)
        .first()
    )
    best_day = best_day_row.date.strftime("%A %b %d") if best_day_row else "N/A"
    best_day_revenue = float(best_day_row.total_revenue) if best_day_row else 0
    worst_day = worst_day_row.date.strftime("%A %b %d") if worst_day_row else "N/A"
    worst_day_revenue = float(worst_day_row.total_revenue) if worst_day_row else 0

    # ── Customer counts by segment ──
    segment_counts = dict(
        db.query(Customer.segment, func.count(Customer.id))
        .filter(Customer.shop_id == shop.id)
        .group_by(Customer.segment)
        .all()
    )
    total_customers = sum(segment_counts.values())
    at_risk_count = segment_counts.get("at_risk", 0)
    lost_count = segment_counts.get("lost", 0)
    vip_count = segment_counts.get("vip", 0)

    # ── Repeat rate ──
    repeat_customers = (
        db.query(func.count(Customer.id))
        .filter(Customer.shop_id == shop.id, Customer.visit_count > 1)
        .scalar()
    ) or 0
    repeat_rate = (repeat_customers / total_customers * 100) if total_customers else 0

    # ── New customers this month ──
    new_customers_month = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.shop_id == shop.id,
            Customer.first_seen >= datetime.combine(first_of_month, datetime.min.time()),
        )
        .scalar()
    ) or 0

    # ── Average CLV ──
    avg_clv_row = (
        db.query(func.avg(Customer.total_spent))
        .filter(Customer.shop_id == shop.id, Customer.total_spent > 0)
        .scalar()
    )
    avg_clv = float(avg_clv_row or 0)

    # ── Product count ──
    product_count = (
        db.query(func.count(Product.id))
        .filter(Product.shop_id == shop.id, Product.is_active == True)
        .scalar()
    ) or 0

    # ── AOV ──
    aov = 0.0
    if transactions_month > 0:
        aov = revenue_month / transactions_month

    # ── Top 5 products by revenue (last 30 days) ──
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

    # ── Trending products (compare last 7 days vs prior 7 days) ──
    trending_up = []
    trending_down = []
    try:
        recent_7 = (
            db.query(
                Product.name,
                func.sum(TransactionItem.total).label("rev"),
            )
            .join(TransactionItem, TransactionItem.product_id == Product.id)
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .filter(
                Product.shop_id == shop.id,
                Transaction.timestamp >= datetime.combine(seven_days_ago, datetime.min.time()),
            )
            .group_by(Product.name)
            .all()
        )
        prior_7 = (
            db.query(
                Product.name,
                func.sum(TransactionItem.total).label("rev"),
            )
            .join(TransactionItem, TransactionItem.product_id == Product.id)
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .filter(
                Product.shop_id == shop.id,
                Transaction.timestamp >= datetime.combine(seven_days_ago - timedelta(days=7), datetime.min.time()),
                Transaction.timestamp < datetime.combine(seven_days_ago, datetime.min.time()),
            )
            .group_by(Product.name)
            .all()
        )
        recent_map = {r.name: float(r.rev) for r in recent_7}
        prior_map = {r.name: float(r.rev) for r in prior_7}
        for name, rev in recent_map.items():
            prev = prior_map.get(name, 0)
            if prev > 0 and rev > prev * 1.15:
                trending_up.append(name)
            elif prev > 0 and rev < prev * 0.85:
                trending_down.append(name)
    except Exception:
        pass

    # ── Competitors summary ──
    competitors = (
        db.query(Competitor.name, Competitor.rating, Competitor.review_count)
        .filter(Competitor.shop_id == shop.id)
        .all()
    )
    comp_list = [
        {"name": c.name, "rating": float(c.rating) if c.rating else 0, "reviews": c.review_count or 0}
        for c in competitors
    ]

    # ── Own reviews summary ──
    own_reviews = (
        db.query(func.count(Review.id), func.avg(Review.rating))
        .filter(Review.shop_id == shop.id, Review.is_own_shop == True)
        .first()
    )
    own_review_count = int(own_reviews[0] or 0)
    own_avg_rating = round(float(own_reviews[1] or 0), 1)

    # ── Recent negative reviews (last 7 days) ──
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

    # ── Monthly goal ──
    current_month_str = today.strftime("%Y-%m")
    goal_row = (
        db.query(RevenueGoal)
        .filter(RevenueGoal.shop_id == shop.id, RevenueGoal.month == current_month_str)
        .first()
    )
    monthly_goal = float(goal_row.target_amount) if goal_row else 0
    goal_progress = revenue_month

    # ── Strongest / weakest day of week (last 30 days) ──
    dow_stats = (
        db.query(
            extract("dow", DailySnapshot.date).label("dow"),
            func.avg(DailySnapshot.total_revenue).label("avg_rev"),
        )
        .filter(
            DailySnapshot.shop_id == shop.id,
            DailySnapshot.date >= thirty_days_ago,
        )
        .group_by("dow")
        .all()
    )
    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    strongest_day = "Saturday"
    weakest_day = "Monday"
    if dow_stats:
        sorted_dow = sorted(dow_stats, key=lambda x: float(x.avg_rev or 0))
        weakest_day = day_names[int(sorted_dow[0].dow)] if sorted_dow else "Monday"
        strongest_day = day_names[int(sorted_dow[-1].dow)] if sorted_dow else "Saturday"

    # ── Peak hours (from hourly snapshots) ──
    peak_hours = "11am-2pm"
    try:
        hourly_stats = (
            db.query(
                HourlySnapshot.hour,
                func.avg(HourlySnapshot.revenue).label("avg_rev"),
            )
            .filter(HourlySnapshot.shop_id == shop.id)
            .group_by(HourlySnapshot.hour)
            .order_by(desc("avg_rev"))
            .limit(3)
            .all()
        )
        if hourly_stats:
            hours = sorted([int(h.hour) for h in hourly_stats])
            fmt_hours = []
            for h in hours:
                if h == 0:
                    fmt_hours.append("12am")
                elif h < 12:
                    fmt_hours.append(f"{h}am")
                elif h == 12:
                    fmt_hours.append("12pm")
                else:
                    fmt_hours.append(f"{h-12}pm")
            peak_hours = ", ".join(fmt_hours)
    except Exception:
        pass

    return {
        "shop_name": shop.name,
        "owner_name": user.full_name.split()[0] if user.full_name else "there",
        "category": shop.category,
        "city": shop.city or "",
        "revenue_today": float(snap.total_revenue) if snap else 0,
        "transactions_today": int(snap.transaction_count) if snap else 0,
        "revenue_yesterday": float(yesterday_snap.total_revenue) if yesterday_snap else 0,
        "revenue_month": revenue_month,
        "revenue_last_month": revenue_last_month,
        "mom_change": round(mom_change, 1),
        "avg_daily_revenue": round(avg_daily_revenue, 2),
        "best_day": best_day,
        "best_day_revenue": best_day_revenue,
        "worst_day": worst_day,
        "worst_day_revenue": worst_day_revenue,
        "total_customers": total_customers,
        "vip_customers": vip_count,
        "at_risk_customers": at_risk_count,
        "lost_customers": lost_count,
        "repeat_rate": round(repeat_rate, 1),
        "new_customers_month": new_customers_month,
        "avg_clv": round(avg_clv, 2),
        "product_count": product_count,
        "aov": round(aov, 2),
        "top_products": top_products,
        "trending_up": trending_up[:3],
        "trending_down": trending_down[:3],
        "competitors": comp_list,
        "own_review_count": own_review_count,
        "own_avg_rating": own_avg_rating,
        "recent_negative_reviews": neg_reviews,
        "monthly_goal": monthly_goal,
        "goal_progress": goal_progress,
        "today_date": today.strftime("%B %d, %Y"),
        "day_of_week": now.strftime("%A"),
        "strongest_day": strongest_day,
        "weakest_day": weakest_day,
        "peak_hours": peak_hours,
    }


def _get_api_key(db: Session, shop: Shop) -> str:
    """Get Anthropic API key from shop settings, config, or env."""
    # 1. Try shop-level setting
    try:
        s = db.query(ShopSettings).filter(ShopSettings.shop_id == shop.id).first()
        if s and hasattr(s, 'anthropic_api_key') and s.anthropic_api_key:
            return s.anthropic_api_key.strip()
    except Exception:
        pass
    # 2. Try pydantic config (reads .env)
    if settings.ANTHROPIC_API_KEY:
        return settings.ANTHROPIC_API_KEY.strip()
    # 3. Direct env var fallback
    env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env_key:
        return env_key
    log.warning("No Anthropic API key found in settings, config, or environment")
    return ""


# ── Sage Action Detection ─────────────────────────────────────────────────────

import uuid as _uuid

def _detect_sage_action(message: str, db: Session, shop: Shop):
    """Detect if user's message is asking Sage to perform an action.
    Returns (action_result, action_message) or (None, None) if no action detected."""
    msg = message.lower().strip()
    now = datetime.utcnow()

    # "set ... goal to ..."
    m = re.search(r'set\s+(?:my\s+)?(?:(\w+)\s+)?(?:(\d{4})[- ]?(?:q(\d))?)?.*?(?:revenue\s+)?goal\s+(?:to\s+)?\$?([\d,]+)', msg)
    if m:
        period_type = m.group(1) or ""
        year = m.group(2) or str(now.year)
        quarter = m.group(3)
        target = float(m.group(4).replace(",", ""))
        if quarter:
            pk = f"{year}-Q{quarter}"
            period = "quarterly"
        else:
            pk = now.strftime("%Y-%m")
            period = "monthly"
        title = f"Revenue Target ({pk})"
        goal = Goal(id=str(_uuid.uuid4()), shop_id=shop.id, goal_type="revenue",
                     title=title, target_value=target, unit="$", period=period, period_key=pk)
        db.add(goal)
        db.commit()
        return True, f"Done! I've set your {pk} revenue goal to ${target:,.0f}. You can see it on your Goals page."

    # "add ... as a competitor" or "add competitor ..."
    m = re.search(r'add\s+(?:(.+?)\s+as\s+a?\s*competitor|competitor\s+(.+?)(?:\s*$|\.))', msg)
    if m:
        name = (m.group(1) or m.group(2) or "").strip().title()
        if name:
            comp = Competitor(id=str(_uuid.uuid4()), shop_id=shop.id, name=name)
            db.add(comp)
            db.commit()
            return True, f"Done! I've added **{name}** as a competitor. Scout will start monitoring them. Check your Competitors page."

    # "add ... product" or "add product ..."
    m = re.search(r'add\s+(?:a\s+)?(?:new\s+)?product[:\s]+(.+?)(?:,\s*\$?([\d.]+))?(?:,\s*(\w[\w\s]*))?$', msg)
    if not m:
        m = re.search(r'add\s+(?:a\s+)?(?:new\s+)?product[:\s]+(.+?)(?:\s+(?:at|for|price)\s+\$?([\d.]+))?(?:\s*,\s*(\w[\w\s]*))?$', msg)
    if m:
        pname = m.group(1).strip().title()
        price = float(m.group(2)) if m.group(2) else 0
        cat = (m.group(3) or "").strip().title()
        product = Product(id=str(_uuid.uuid4()), shop_id=shop.id, name=pname, price=price, category=cat)
        db.add(product)
        db.commit()
        price_str = f" at ${price:.2f}" if price else ""
        return True, f"Done! I've added **{pname}**{price_str} to your products. Check the Products page."

    # "pause/activate ... agent"
    m = re.search(r'(pause|stop|deactivate|activate|start|resume|unpause)\s+(?:the\s+)?(?:(\w+)\s+)?(?:agent\s*)?(\w+)?', msg)
    if m:
        verb = m.group(1)
        name1 = (m.group(2) or "").lower()
        name2 = (m.group(3) or "").lower()
        agent_name = name1 or name2
        agent_map = {"maya": "maya", "scout": "scout", "emma": "emma", "alex": "alex", "max": "max",
                     "marketing": "maya", "competitor": "scout", "customer": "emma", "strategy": "alex", "sales": "max"}
        atype = agent_map.get(agent_name)
        if atype:
            agent = db.query(Agent).filter(Agent.shop_id == shop.id, Agent.agent_type == atype).first()
            if agent:
                active = verb in ("activate", "start", "resume", "unpause")
                agent.is_active = active
                db.commit()
                display_name = {"maya": "Maya", "scout": "Scout", "emma": "Emma", "alex": "Alex", "max": "Max"}[atype]
                return True, f"Done! I've {'activated' if active else 'paused'} **{display_name}**. {'She' if atype in ('maya','emma') else 'He'}'ll {'get right back to work' if active else 'take a break'}."

    # "set ... target to N units"
    m = re.search(r'set\s+(.+?)\s+target\s+(?:to\s+)?(\d+)\s*units?', msg)
    if m:
        pname = m.group(1).strip()
        target = int(m.group(2))
        product = db.query(Product).filter(Product.shop_id == shop.id, Product.name.ilike(f"%{pname}%")).first()
        if product:
            period = now.strftime("%Y-%m")
            existing = db.query(ProductGoal).filter(ProductGoal.shop_id == shop.id, ProductGoal.product_id == product.id, ProductGoal.period == period).first()
            if existing:
                existing.target_units = target
            else:
                db.add(ProductGoal(id=str(_uuid.uuid4()), shop_id=shop.id, product_id=product.id, target_units=target, period=period))
            db.commit()
            return True, f"Done! I've set **{product.name}** target to {target} units for {period}. Check your Goals page."

    return None, None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chat")
async def ai_chat(
    message: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message to the Sage AI assistant (non-streaming)."""
    shop = _get_shop(db, user)
    if not shop:
        return {"response": "Please complete onboarding first.", "source": "error", "remaining": 0}

    # Check if this is an action request (set goal, add competitor, etc.)
    action_result, action_message = _detect_sage_action(message, db, shop)
    if action_result is not None:
        db.add(ChatMessage(shop_id=shop.id, role="user", content=message))
        db.add(ChatMessage(shop_id=shop.id, role="assistant", content=action_message))
        db.commit()
        return {"response": action_message, "source": "action", "action_taken": True, "remaining": get_remaining_requests(user.id)}

    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.shop_id == shop.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    history = [{"role": h.role, "content": h.content} for h in reversed(history_rows)]

    context = _get_shop_context(db, shop, user)
    api_key = _get_api_key(db, shop)
    log.info("AI chat — user=%s, shop=%s, api_key=%s", user.id, shop.name, "set" if api_key else "MISSING")

    result = await chat(
        user_id=user.id,
        message=message,
        conversation_history=history,
        api_key=api_key,
        shop_context=context,
    )
    log.info("AI chat response — source=%s", result.get("source"))

    db.add(ChatMessage(shop_id=shop.id, role="user", content=message))
    db.add(ChatMessage(shop_id=shop.id, role="assistant", content=result["response"]))
    db.commit()

    return result


@router.post("/chat/stream")
async def ai_chat_stream_endpoint(
    message: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream a Sage AI response via Server-Sent Events."""
    shop = _get_shop(db, user)
    if not shop:
        async def error_gen():
            yield f"data: {__import__('json').dumps({'text': '', 'done': True, 'full_text': 'Please complete onboarding first.', 'source': 'error', 'remaining': 0})}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.shop_id == shop.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    history = [{"role": h.role, "content": h.content} for h in reversed(history_rows)]

    context = _get_shop_context(db, shop, user)
    api_key = _get_api_key(db, shop)

    # Save user message immediately
    db.add(ChatMessage(shop_id=shop.id, role="user", content=message))
    db.commit()

    # We need to capture the full response to save it
    import json as json_mod

    async def stream_and_save():
        full_text = ""
        async for chunk in chat_stream(
            user_id=user.id,
            message=message,
            conversation_history=history,
            api_key=api_key,
            shop_context=context,
        ):
            yield chunk
            # Parse the chunk to capture full text
            try:
                data = json_mod.loads(chunk.replace("data: ", "").strip())
                if data.get("done") and data.get("full_text"):
                    full_text = data["full_text"]
            except Exception:
                pass

        # Save assistant response after streaming completes
        if full_text:
            from app.database import SessionLocal
            save_db = SessionLocal()
            try:
                save_db.add(ChatMessage(shop_id=shop.id, role="assistant", content=full_text))
                save_db.commit()
            finally:
                save_db.close()

    return StreamingResponse(stream_and_save(), media_type="text/event-stream")


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


@router.post("/test-connection")
async def ai_test_connection(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test the Anthropic API connection."""
    shop = _get_shop(db, user)
    if not shop:
        return {"ok": False, "message": "Shop not found"}
    api_key = _get_api_key(db, shop)
    return await test_connection(api_key)


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


# ── Agent-specific Chat ──────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPTS = {
    "maya": """You are Maya, the Marketing Director AI agent inside Forge. You're part of a 5-agent AI team managed by Sage. You are creative, enthusiastic about social media, and deeply knowledgeable about retail marketing. You speak with confidence and a touch of flair.

PERSONALITY: Creative, trend-aware, social-media-savvy, enthusiastic, action-oriented.
EXPERTISE: Social media content, email campaigns, promotions, hashtag strategy, content calendars, brand voice, visual marketing.
FOCUS: Primarily discuss marketing-related topics. If asked about other areas, briefly help but mention your teammate: "That's more Scout's area — he tracks competitors. But here's my take..." or "Emma handles customer outreach, but I can draft the marketing angle."

TEAM AWARENESS: You work alongside Scout (competitors), Emma (customers), Alex (strategy), and Max (sales). Reference them naturally: "I'll coordinate with Emma on the customer emails" or "Max flagged a bundle opportunity I can promote."

When creating content, make it copy-paste ready with emojis, hashtags, and clear calls to action.""",

    "scout": """You are Scout, the Competitive Intelligence Analyst AI agent inside Forge. You're part of a 5-agent AI team managed by Sage. You are analytical, strategic, and always watching the competition. You speak with precision and urgency when opportunities arise.

PERSONALITY: Sharp, analytical, strategic, competitive, alert, data-driven.
EXPERTISE: Competitor monitoring, market positioning, competitive response strategies, review analysis, pricing intelligence, market gaps.
FOCUS: Primarily discuss competitor-related topics. If asked about other areas, briefly help but reference your teammate: "Maya could turn this intel into a killer campaign" or "I'll flag this pricing gap for Max."

TEAM AWARENESS: You work alongside Maya (marketing), Emma (customers), Alex (strategy), and Max (sales). Reference them naturally: "I'll share this competitor weakness with Maya for content" or "Alex should factor this into the Q1 strategy."

Always frame competitor weaknesses as YOUR opportunities. Be specific about how to capitalize.""",

    "emma": """You are Emma, the Customer Success Manager AI agent inside Forge. You're part of a 5-agent AI team managed by Sage. You are warm, empathetic, and deeply care about customer relationships. You speak with genuine concern for customer well-being.

PERSONALITY: Warm, empathetic, relationship-oriented, attentive, caring, proactive.
EXPERTISE: Customer retention, win-back campaigns, review responses, VIP management, churn prevention, customer segmentation, loyalty programs.
FOCUS: Primarily discuss customer-related topics. If asked about other areas, briefly help but reference your teammate: "Maya can create the social content for this" or "I'll loop in Max on the loyalty discount pricing."

TEAM AWARENESS: You work alongside Maya (marketing), Scout (competitors), Alex (strategy), and Max (sales). Reference them naturally: "Maya and I are working on a VIP appreciation campaign" or "Alex's revenue data helps me identify at-risk customers."

Always personalize recommendations based on customer data. Treat every customer as important.""",

    "alex": """You are Alex, the Chief Strategy Officer AI agent inside Forge. You're part of a 5-agent AI team managed by Sage. You are analytical, strategic, and think in terms of long-term business growth. You speak with authority and back everything with data.

PERSONALITY: Analytical, strategic, data-driven, authoritative, forward-thinking, methodical.
EXPERTISE: Business strategy, revenue analysis, goal tracking, forecasting, P&L analysis, market trends, growth planning, KPI monitoring.
FOCUS: Primarily discuss strategy and analytics topics. If asked about other areas, briefly help but reference your teammate: "I'll have Maya execute the marketing side" or "Scout's competitive data supports this strategy."

TEAM AWARENESS: You work alongside Maya (marketing), Scout (competitors), Emma (customers), and Max (sales). Reference them naturally: "Based on Scout's competitor analysis and Max's pricing data..." or "I'm recommending Emma focus on the VIP segment this quarter."

Always include numbers and data in your analysis. Think like a CEO consultant.""",

    "max": """You are Max, the Sales Director AI agent inside Forge. You're part of a 5-agent AI team managed by Sage. You are results-driven, numbers-oriented, and always looking for ways to increase revenue. You speak with energy and focus on ROI.

PERSONALITY: Results-driven, energetic, ROI-focused, opportunistic, numbers-oriented, persuasive.
EXPERTISE: Sales optimization, pricing strategy, product bundling, upselling, cross-selling, inventory management, markdown strategy, revenue maximization.
FOCUS: Primarily discuss sales and pricing topics. If asked about other areas, briefly help but reference your teammate: "Maya can promote this bundle on social" or "Scout says the competition is charging 20% more."

TEAM AWARENESS: You work alongside Maya (marketing), Scout (competitors), Emma (customers), and Alex (strategy). Reference them naturally: "I've coordinated with Alex on the revenue targets" or "Emma's customer data shows this bundle would appeal to your VIPs."

Always quantify the revenue impact of your suggestions. Show the money.""",
}


@router.post("/agent-chat")
async def agent_chat(
    agent_type: str = Body(...),
    message: str = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Chat with a specific AI agent using their personality."""
    shop = _get_shop(db, user)
    if not shop:
        return {"response": "Please complete onboarding first.", "source": "error"}

    agent_prompt = AGENT_SYSTEM_PROMPTS.get(agent_type)
    if not agent_prompt:
        return {"response": "Unknown agent.", "source": "error"}

    context = _get_shop_context(db, shop, user)
    api_key = _get_api_key(db, shop)

    # Build a combined system prompt: agent personality + shop data
    base_prompt = build_system_prompt(context)
    # Replace the Sage identity with the agent identity
    combined_prompt = agent_prompt + "\n\n" + base_prompt.split("SHOP DATA")[1] if "SHOP DATA" in base_prompt else agent_prompt

    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.shop_id == shop.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(6)
        .all()
    )
    history = [{"role": h.role, "content": h.content} for h in reversed(history_rows)]

    result = await chat(
        user_id=user.id,
        message=message,
        conversation_history=history,
        api_key=api_key,
        shop_context=context,
        system_prompt_override=combined_prompt,
    )

    db.add(ChatMessage(shop_id=shop.id, role="user", content=message))
    db.add(ChatMessage(shop_id=shop.id, role="assistant", content=result["response"]))
    db.commit()

    return result
