"""Email API endpoints for sending real emails via SMTP."""

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.dependencies import get_current_user, get_db
from app.models import User, Shop, SentEmail
from app.services.email_service import email_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email", tags=["email"])


def _get_shop(db: Session, user: User) -> Shop:
    return db.query(Shop).filter(Shop.user_id == user.id).first()


@router.get("/status")
def email_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if email is configured and return stats."""
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    sent_count = (
        db.query(func.count(SentEmail.id))
        .filter(SentEmail.shop_id == shop.id, SentEmail.status == "sent", SentEmail.created_at >= month_start)
        .scalar() or 0
    )
    failed_count = (
        db.query(func.count(SentEmail.id))
        .filter(SentEmail.shop_id == shop.id, SentEmail.status == "failed", SentEmail.created_at >= month_start)
        .scalar() or 0
    )

    return {
        "configured": email_service.is_configured,
        "smtp_host": email_service.smtp_host,
        "smtp_port": email_service.smtp_port,
        "smtp_user": email_service.smtp_user[:3] + "***" if email_service.smtp_user else "",
        "sent_this_month": sent_count,
        "failed_this_month": failed_count,
    }


@router.post("/send")
def send_email(
    to: str = Body(...),
    subject: str = Body(...),
    body: str = Body(...),
    template: str = Body("plain"),
    sent_by: str = Body("user"),
    agent_output_id: str = Body(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a real email via SMTP and log it."""
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}

    if template == "marketing":
        result = email_service.send_marketing_email(to, subject, body, shop.name)
    else:
        # Plain HTML email
        html = f"<html><body style='font-family:Arial,sans-serif;'>{body.replace(chr(10), '<br>')}</body></html>"
        result = email_service.send_email(to, subject, html, body)

    # Log the email
    email_log = SentEmail(
        id=str(uuid.uuid4()),
        shop_id=shop.id,
        to_email=to,
        subject=subject,
        body_preview=body[:500],
        template=template,
        status="sent" if result["success"] else "failed",
        error_message=result.get("error"),
        sent_by=sent_by,
        agent_output_id=agent_output_id,
    )
    db.add(email_log)
    db.commit()

    return result


@router.post("/test")
def send_test_email(
    to: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a test email to verify SMTP configuration."""
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}

    result = email_service.send_test_email(to)

    # Log it
    email_log = SentEmail(
        id=str(uuid.uuid4()),
        shop_id=shop.id,
        to_email=to,
        subject="Forge Email Test",
        body_preview="Test email to verify SMTP configuration",
        template="test",
        status="sent" if result["success"] else "failed",
        error_message=result.get("error"),
        sent_by="system",
    )
    db.add(email_log)
    db.commit()

    return result


@router.get("/history")
def email_history(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get email sending history."""
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}

    emails = (
        db.query(SentEmail)
        .filter(SentEmail.shop_id == shop.id)
        .order_by(desc(SentEmail.created_at))
        .limit(limit)
        .all()
    )

    return {
        "emails": [
            {
                "id": e.id,
                "to_email": e.to_email,
                "subject": e.subject,
                "body_preview": e.body_preview,
                "template": e.template,
                "status": e.status,
                "error_message": e.error_message,
                "sent_by": e.sent_by,
                "created_at": e.created_at.isoformat(),
            }
            for e in emails
        ],
    }
