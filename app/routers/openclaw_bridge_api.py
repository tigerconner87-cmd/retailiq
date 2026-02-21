"""OpenClaw Bridge API — Integration layer for OpenClaw to submit agent outputs to Forge.

Endpoints:
  POST /api/v1/openclaw/submit        — Submit agent deliverable for approval
  GET  /api/v1/openclaw/context        — Get shop data for personalization
  GET  /api/v1/openclaw/schedule       — Get agent schedule configuration
  POST /api/v1/openclaw/heartbeat      — Periodic health check-in
  POST /api/v1/openclaw/trigger        — Trigger an on-demand agent run
  GET  /api/v1/openclaw/queue          — List pending deliverables
  POST /api/v1/openclaw/queue/{id}/approve  — Approve a deliverable
  POST /api/v1/openclaw/queue/{id}/reject   — Reject a deliverable
"""

import logging
import os
import uuid
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import SessionLocal
from app.dependencies import get_db, get_current_user
from app.models import (
    Shop, User, Product, Customer, Competitor, Goal, RevenueGoal,
    DailySnapshot, AgentDeliverable, ScheduledTask, SentEmail,
    AgentRun, AgentOutput, Agent, Review,
)
from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/openclaw", tags=["openclaw-bridge"])

# In-memory heartbeat tracking
_last_heartbeat: dict = {}


# ── Auth ────────────────────────────────────────────────────────────────────

def _verify_bridge_token(authorization: str = Header(None)):
    """Verify the OpenClaw bridge token."""
    expected = os.environ.get("OPENCLAW_BRIDGE_TOKEN", settings.OPENCLAW_BRIDGE_TOKEN)
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != expected:
        raise HTTPException(status_code=401, detail="Invalid bridge token")
    return True


def _get_demo_shop(db: Session) -> Shop:
    """Get the first shop (demo) for bridge operations."""
    shop = db.query(Shop).first()
    if not shop:
        raise HTTPException(status_code=404, detail="No shop found")
    return shop


# ── 1. Submit Deliverable ──────────────────────────────────────────────────

@router.post("/submit")
def submit_deliverable(
    agent: str = Body(...),
    output_type: str = Body(...),
    title: str = Body(...),
    content: str = Body(...),
    summary: str = Body(""),
    confidence: float = Body(0.5),
    metadata: dict = Body({}),
    _auth: bool = Depends(_verify_bridge_token),
    db: Session = Depends(get_db),
):
    """Accept an agent deliverable from OpenClaw for approval."""
    if agent not in ("maya", "scout", "emma", "alex", "max"):
        raise HTTPException(status_code=400, detail="Invalid agent type")
    if confidence < 0 or confidence > 1:
        raise HTTPException(status_code=400, detail="Confidence must be 0-1")

    shop = _get_demo_shop(db)

    deliverable = AgentDeliverable(
        id=str(uuid.uuid4()),
        shop_id=shop.id,
        agent_type=agent,
        deliverable_type=output_type,
        title=title,
        content=content,
        summary=summary,
        confidence=confidence,
        status="pending_approval",
        source="openclaw",
        metadata_json=metadata,
    )
    db.add(deliverable)
    db.commit()

    # Queue position
    pending_count = (
        db.query(func.count(AgentDeliverable.id))
        .filter(
            AgentDeliverable.shop_id == shop.id,
            AgentDeliverable.status == "pending_approval",
        )
        .scalar()
    ) or 0

    log.info("[Bridge] Submitted deliverable from %s: %s (queue pos: %d)", agent, title, pending_count)
    return {
        "ok": True,
        "deliverable_id": deliverable.id,
        "queue_position": pending_count,
        "status": "pending_approval",
    }


# ── 2. Context ─────────────────────────────────────────────────────────────

@router.get("/context")
def get_context(
    _auth: bool = Depends(_verify_bridge_token),
    db: Session = Depends(get_db),
):
    """Return shop data for OpenClaw agent personalization."""
    shop = _get_demo_shop(db)
    user = db.query(User).filter(User.id == shop.user_id).first()
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    first_of_month = today.replace(day=1)

    # Products
    products = (
        db.query(Product)
        .filter(Product.shop_id == shop.id, Product.is_active == True)
        .limit(50)
        .all()
    )

    # Customers by segment
    segment_counts = dict(
        db.query(Customer.segment, func.count(Customer.id))
        .filter(Customer.shop_id == shop.id)
        .group_by(Customer.segment)
        .all()
    )
    total_customers = sum(segment_counts.values()) if segment_counts else 0

    # Competitors
    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop.id)
        .all()
    )

    # Revenue this month
    month_rev = (
        db.query(func.sum(DailySnapshot.total_revenue))
        .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date >= first_of_month)
        .scalar()
    ) or 0

    # Goals
    goals = db.query(Goal).filter(Goal.shop_id == shop.id, Goal.status == "active").all()
    revenue_goal = (
        db.query(RevenueGoal)
        .filter(RevenueGoal.shop_id == shop.id, RevenueGoal.month == today.strftime("%Y-%m"))
        .first()
    )

    # Recent reviews
    recent_reviews = (
        db.query(Review)
        .filter(Review.shop_id == shop.id, Review.is_own_shop == True)
        .order_by(desc(Review.review_date))
        .limit(5)
        .all()
    )

    # Emails sent today
    today_start = datetime.combine(today, datetime.min.time())
    emails_today = (
        db.query(func.count(SentEmail.id))
        .filter(SentEmail.shop_id == shop.id, SentEmail.created_at >= today_start)
        .scalar()
    ) or 0

    return {
        "shop": {
            "name": shop.name,
            "category": shop.category,
            "city": getattr(shop, "city", None) or "",
            "address": shop.address or "",
        },
        "owner": {
            "name": user.full_name if user else "",
            "email": user.email if user else "",
        },
        "products": [
            {
                "name": p.name,
                "price": float(p.price) if p.price else 0,
                "category": p.category or "",
                "sku": p.sku or "",
                "stock": p.stock_quantity,
            }
            for p in products
        ],
        "customers": {
            "total": total_customers,
            "vip": segment_counts.get("vip", 0),
            "regular": segment_counts.get("regular", 0),
            "at_risk": segment_counts.get("at_risk", 0),
            "lost": segment_counts.get("lost", 0),
        },
        "competitors": [
            {
                "name": c.name,
                "rating": float(c.rating) if c.rating else None,
                "review_count": c.review_count or 0,
            }
            for c in competitors
        ],
        "goals": [
            {
                "title": g.title,
                "target": float(g.target_value),
                "unit": g.unit,
                "period": g.period,
            }
            for g in goals
        ],
        "revenue": {
            "month_to_date": float(month_rev),
            "monthly_target": float(revenue_goal.target_amount) if revenue_goal else 0,
        },
        "recent_reviews": [
            {
                "rating": r.rating,
                "text": (r.text or "")[:200],
                "responded": r.response_text is not None,
            }
            for r in recent_reviews
        ],
        "activity": {
            "emails_sent_today": emails_today,
            "date": today.isoformat(),
        },
    }


# ── 3. Schedule ────────────────────────────────────────────────────────────

@router.get("/schedule")
def get_schedule(
    _auth: bool = Depends(_verify_bridge_token),
    db: Session = Depends(get_db),
):
    """Return the current schedule configuration for all agents."""
    shop = _get_demo_shop(db)
    tasks = (
        db.query(ScheduledTask)
        .filter(ScheduledTask.shop_id == shop.id)
        .order_by(ScheduledTask.next_run_at)
        .all()
    )
    return {
        "schedules": [
            {
                "id": t.id,
                "task_name": t.task_name,
                "agent_type": t.agent_type,
                "instructions": t.instructions,
                "schedule_type": t.schedule_type,
                "schedule_config": t.schedule_config,
                "is_active": t.is_active,
                "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
                "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
                "last_status": t.last_status,
            }
            for t in tasks
        ],
    }


# ── 4. Heartbeat ──────────────────────────────────────────────────────────

@router.post("/heartbeat")
def heartbeat(
    agent_statuses: dict = Body({}, embed=True),
    _auth: bool = Depends(_verify_bridge_token),
    db: Session = Depends(get_db),
):
    """OpenClaw periodic health check-in."""
    global _last_heartbeat
    _last_heartbeat = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent_statuses": agent_statuses,
    }

    shop = _get_demo_shop(db)

    # Check for pending triggers (deliverables that need action)
    pending_count = (
        db.query(func.count(AgentDeliverable.id))
        .filter(
            AgentDeliverable.shop_id == shop.id,
            AgentDeliverable.status == "pending_approval",
        )
        .scalar()
    ) or 0

    log.info("[Bridge] Heartbeat received — %d agents, %d pending", len(agent_statuses), pending_count)
    return {
        "ok": True,
        "pending_approvals": pending_count,
        "server_time": datetime.utcnow().isoformat(),
    }


# ── 5. Trigger Agent Run ─────────────────────────────────────────────────

@router.post("/trigger")
async def trigger_agent_run(
    agent: str = Body(...),
    task: str = Body(""),
    context: dict = Body({}),
    _auth: bool = Depends(_verify_bridge_token),
    db: Session = Depends(get_db),
):
    """Trigger an on-demand agent run via Forge's orchestrator."""
    if agent not in ("maya", "scout", "emma", "alex", "max"):
        raise HTTPException(status_code=400, detail="Invalid agent type")

    shop = _get_demo_shop(db)
    user = db.query(User).filter(User.id == shop.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="No user found")

    # Get API key
    from app.routers.ai import _get_api_key, _get_shop_context
    api_key = _get_api_key(db, shop)
    if not api_key:
        raise HTTPException(status_code=503, detail="No API key configured")

    shop_ctx = _get_shop_context(db, shop, user)
    from app.services.orchestrator import TaskOrchestrator
    orch = TaskOrchestrator(db, shop, api_key, shop_ctx)

    instructions = task or context.get("instructions", "")
    result = await orch.execute_single_agent(agent, instructions)

    return {
        "ok": True,
        "agent": agent,
        "status": result.get("status", "completed"),
        "outputs": len(result.get("outputs", [])),
        "summary": result.get("summary", ""),
    }


# ── 6. Queue ──────────────────────────────────────────────────────────────

@router.get("/queue")
def get_queue(
    _auth: bool = Depends(_verify_bridge_token),
    db: Session = Depends(get_db),
):
    """Return all pending deliverables awaiting approval."""
    shop = _get_demo_shop(db)
    deliverables = (
        db.query(AgentDeliverable)
        .filter(
            AgentDeliverable.shop_id == shop.id,
            AgentDeliverable.status == "pending_approval",
        )
        .order_by(desc(AgentDeliverable.created_at))
        .all()
    )
    return {
        "queue": [
            {
                "id": d.id,
                "agent_type": d.agent_type,
                "output_type": d.deliverable_type,
                "title": d.title,
                "content": d.content,
                "summary": d.summary,
                "confidence": d.confidence,
                "source": d.source,
                "metadata": d.metadata_json,
                "created_at": d.created_at.isoformat(),
            }
            for d in deliverables
        ],
        "total": len(deliverables),
    }


# ── 7. Approve ────────────────────────────────────────────────────────────

@router.post("/queue/{deliverable_id}/approve")
def approve_deliverable(
    deliverable_id: str,
    _auth: bool = Depends(_verify_bridge_token),
    db: Session = Depends(get_db),
):
    """Approve a deliverable. Sends email if deliverable is an email type."""
    shop = _get_demo_shop(db)
    d = db.query(AgentDeliverable).filter(
        AgentDeliverable.id == deliverable_id,
        AgentDeliverable.shop_id == shop.id,
    ).first()
    if not d:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    if d.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Cannot approve: status is {d.status}")

    d.status = "approved"
    d.approved_at = datetime.utcnow()

    # If email type, try to send
    action_result = None
    email_types = ("email_campaign", "winback_email", "email_draft", "email")
    if d.deliverable_type in email_types:
        try:
            from app.services.email_service import email_service
            user = db.query(User).filter(User.id == shop.user_id).first()
            to_email = user.email if user else ""
            if to_email:
                result = email_service.send_marketing_email(to_email, d.title, d.content, shop.name)
                if result.get("success"):
                    d.status = "sent"
                    d.shipped_via = "email"
                    d.shipped_at = datetime.utcnow()
                    db.add(SentEmail(
                        id=str(uuid.uuid4()), shop_id=shop.id, to_email=to_email,
                        subject=d.title, body_preview=d.content[:500],
                        template="openclaw_bridge", status="sent", sent_by=d.agent_type,
                    ))
                    action_result = {"email_sent": True, "to": to_email}
                else:
                    action_result = {"email_sent": False, "error": result.get("error")}
        except Exception as e:
            log.warning("[Bridge] Email send failed on approve: %s", e)
            action_result = {"email_sent": False, "error": str(e)}

    db.commit()
    log.info("[Bridge] Approved deliverable %s (%s)", deliverable_id, d.agent_type)
    return {"ok": True, "status": d.status, "action": action_result}


# ── 8. Reject ─────────────────────────────────────────────────────────────

@router.post("/queue/{deliverable_id}/reject")
def reject_deliverable(
    deliverable_id: str,
    reason: str = Body("", embed=True),
    _auth: bool = Depends(_verify_bridge_token),
    db: Session = Depends(get_db),
):
    """Reject a deliverable with feedback for OpenClaw to learn from."""
    shop = _get_demo_shop(db)
    d = db.query(AgentDeliverable).filter(
        AgentDeliverable.id == deliverable_id,
        AgentDeliverable.shop_id == shop.id,
    ).first()
    if not d:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    if d.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Cannot reject: status is {d.status}")

    d.status = "rejected"
    d.rejection_reason = reason or "No reason provided"
    db.commit()

    log.info("[Bridge] Rejected deliverable %s: %s", deliverable_id, reason[:80] if reason else "no reason")
    return {"ok": True, "status": "rejected"}


# ── Internal endpoints (for Forge dashboard — uses session auth) ──────────

@router.get("/queue/pending")
def get_pending_for_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get pending approval queue for the dashboard (session auth)."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        return {"queue": [], "total": 0}

    deliverables = (
        db.query(AgentDeliverable)
        .filter(
            AgentDeliverable.shop_id == shop.id,
            AgentDeliverable.status == "pending_approval",
        )
        .order_by(desc(AgentDeliverable.created_at))
        .all()
    )
    return {
        "queue": [
            {
                "id": d.id,
                "agent_type": d.agent_type,
                "output_type": d.deliverable_type,
                "title": d.title,
                "content": d.content,
                "summary": d.summary or "",
                "confidence": d.confidence or 0.5,
                "source": d.source or "internal",
                "created_at": d.created_at.isoformat(),
            }
            for d in deliverables
        ],
        "total": len(deliverables),
    }


@router.get("/queue/count")
def get_pending_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get pending approval count (for sidebar badge)."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        return {"count": 0}
    count = (
        db.query(func.count(AgentDeliverable.id))
        .filter(
            AgentDeliverable.shop_id == shop.id,
            AgentDeliverable.status == "pending_approval",
        )
        .scalar()
    ) or 0
    return {"count": count}


@router.post("/queue/{deliverable_id}/approve-dashboard")
def approve_from_dashboard(
    deliverable_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve from dashboard (session auth)."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="No shop")
    d = db.query(AgentDeliverable).filter(
        AgentDeliverable.id == deliverable_id,
        AgentDeliverable.shop_id == shop.id,
    ).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    if d.status != "pending_approval":
        return {"ok": False, "detail": f"Status is {d.status}"}

    d.status = "approved"
    d.approved_at = datetime.utcnow()

    action_result = None
    email_types = ("email_campaign", "winback_email", "email_draft", "email")
    if d.deliverable_type in email_types:
        try:
            from app.services.email_service import email_service
            to_email = user.email or ""
            if to_email:
                result = email_service.send_marketing_email(to_email, d.title, d.content, shop.name)
                if result.get("success"):
                    d.status = "sent"
                    d.shipped_via = "email"
                    d.shipped_at = datetime.utcnow()
                    db.add(SentEmail(
                        id=str(uuid.uuid4()), shop_id=shop.id, to_email=to_email,
                        subject=d.title, body_preview=d.content[:500],
                        template="openclaw_bridge", status="sent", sent_by=d.agent_type,
                    ))
                    action_result = {"email_sent": True, "to": to_email}
        except Exception as e:
            log.warning("[Bridge] Dashboard email send failed: %s", e)

    db.commit()
    return {"ok": True, "status": d.status, "action": action_result}


@router.post("/queue/{deliverable_id}/reject-dashboard")
def reject_from_dashboard(
    deliverable_id: str,
    reason: str = Body("", embed=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject from dashboard (session auth)."""
    shop = db.query(Shop).filter(Shop.user_id == user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="No shop")
    d = db.query(AgentDeliverable).filter(
        AgentDeliverable.id == deliverable_id,
        AgentDeliverable.shop_id == shop.id,
    ).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")

    d.status = "rejected"
    d.rejection_reason = reason or "No reason provided"
    db.commit()
    return {"ok": True, "status": "rejected"}


@router.get("/heartbeat/status")
def get_heartbeat_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the last heartbeat status (for dashboard OpenClaw status indicator)."""
    connected = False
    if _last_heartbeat.get("timestamp"):
        try:
            last = datetime.fromisoformat(_last_heartbeat["timestamp"])
            connected = (datetime.utcnow() - last).total_seconds() < 300
        except Exception:
            pass
    return {
        "connected": connected,
        "last_heartbeat": _last_heartbeat.get("timestamp"),
        "agent_statuses": _last_heartbeat.get("agent_statuses", {}),
    }
