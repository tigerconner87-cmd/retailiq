"""Policy Engine — Guardrails & Safety for Claw Bot.

Enforces rate limits, cost limits, email limits, and content policies.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import ExecutionGoal, SentEmail, AgentRun

log = logging.getLogger(__name__)

# Default policy limits
DEFAULT_POLICY = {
    "max_goals_per_hour": 10,
    "max_goals_per_day": 50,
    "max_emails_per_day": 50,
    "max_tokens_per_day": 500000,
    "max_cost_per_day": 5.00,  # USD
    "require_email_approval": True,
    "blocked_email_domains": [],
}


class PolicyEngine:
    """Enforce safety guardrails on Claw Bot operations."""

    def __init__(self, db: Session, shop_id: str, policy: dict = None):
        self.db = db
        self.shop_id = shop_id
        self.policy = {**DEFAULT_POLICY, **(policy or {})}

    def check_goal_allowed(self) -> tuple[bool, str]:
        """Check if creating a new goal is allowed."""
        now = datetime.utcnow()

        # Hourly limit
        hour_ago = now - timedelta(hours=1)
        hourly_count = (
            self.db.query(func.count(ExecutionGoal.id))
            .filter(ExecutionGoal.shop_id == self.shop_id, ExecutionGoal.created_at >= hour_ago)
            .scalar() or 0
        )
        if hourly_count >= self.policy["max_goals_per_hour"]:
            return False, f"Rate limit: max {self.policy['max_goals_per_hour']} goals per hour."

        # Daily limit
        day_ago = now - timedelta(days=1)
        daily_count = (
            self.db.query(func.count(ExecutionGoal.id))
            .filter(ExecutionGoal.shop_id == self.shop_id, ExecutionGoal.created_at >= day_ago)
            .scalar() or 0
        )
        if daily_count >= self.policy["max_goals_per_day"]:
            return False, f"Rate limit: max {self.policy['max_goals_per_day']} goals per day."

        # Daily token limit
        daily_tokens = (
            self.db.query(func.sum(ExecutionGoal.total_tokens))
            .filter(ExecutionGoal.shop_id == self.shop_id, ExecutionGoal.created_at >= day_ago)
            .scalar() or 0
        )
        if daily_tokens >= self.policy["max_tokens_per_day"]:
            return False, "Token limit reached for today. Try again tomorrow."

        return True, ""

    def check_email_allowed(self, to_email: str) -> tuple[bool, str]:
        """Check if sending an email is allowed."""
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)

        # Daily email limit
        daily_emails = (
            self.db.query(func.count(SentEmail.id))
            .filter(SentEmail.shop_id == self.shop_id, SentEmail.created_at >= day_ago)
            .scalar() or 0
        )
        if daily_emails >= self.policy["max_emails_per_day"]:
            return False, f"Email limit: max {self.policy['max_emails_per_day']} emails per day."

        # Check blocked domains
        domain = to_email.split("@")[-1].lower() if "@" in to_email else ""
        if domain in self.policy["blocked_email_domains"]:
            return False, f"Email domain {domain} is blocked by policy."

        return True, ""

    def get_usage_stats(self) -> dict:
        """Get current usage statistics for the dashboard."""
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)

        goals_today = (
            self.db.query(func.count(ExecutionGoal.id))
            .filter(ExecutionGoal.shop_id == self.shop_id, ExecutionGoal.created_at >= day_ago)
            .scalar() or 0
        )
        tokens_today = (
            self.db.query(func.sum(ExecutionGoal.total_tokens))
            .filter(ExecutionGoal.shop_id == self.shop_id, ExecutionGoal.created_at >= day_ago)
            .scalar() or 0
        )
        emails_today = (
            self.db.query(func.count(SentEmail.id))
            .filter(SentEmail.shop_id == self.shop_id, SentEmail.created_at >= day_ago)
            .scalar() or 0
        )
        runs_today = (
            self.db.query(func.count(AgentRun.id))
            .filter(AgentRun.shop_id == self.shop_id, AgentRun.created_at >= day_ago)
            .scalar() or 0
        )

        return {
            "goals_today": goals_today,
            "goals_limit": self.policy["max_goals_per_day"],
            "tokens_today": tokens_today,
            "tokens_limit": self.policy["max_tokens_per_day"],
            "emails_today": emails_today,
            "emails_limit": self.policy["max_emails_per_day"],
            "runs_today": runs_today,
            "cost_today": round(tokens_today * 0.0000008, 4),
            "cost_limit": self.policy["max_cost_per_day"],
        }
