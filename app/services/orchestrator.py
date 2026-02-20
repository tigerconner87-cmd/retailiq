"""Task orchestrator — backward-compatible wrapper around Claw Bot.

This module now delegates to ClawBot for all orchestration.
The old TaskOrchestrator class is preserved as a thin wrapper.
"""

import logging

from sqlalchemy.orm import Session

from app.models import Shop
from app.services.claw_bot import ClawBot

log = logging.getLogger(__name__)


class TaskOrchestrator:
    """Backward-compatible wrapper that delegates to ClawBot."""

    def __init__(self, db: Session, shop: Shop, api_key: str, shop_context: dict):
        log.info("[Orchestrator] Init — shop=%s, api_key=%s", shop.name, "set" if api_key else "MISSING")
        self._bot = ClawBot(db, shop, api_key, shop_context)

    async def process_command(self, command: str) -> dict:
        """Decompose a command via Claw Bot, execute agent tasks, return compiled summary."""
        log.info("[Orchestrator] process_command: %s", command[:100])
        result = await self._bot.execute_goal(command)
        log.info("[Orchestrator] Goal complete — status=%s, agents=%s", result.get("status"), result.get("agent_count"))
        return {
            "group_id": result.get("goal_id"),
            "summary": result.get("summary", ""),
            "results": result.get("results", []),
            "agent_count": result.get("agent_count", 0),
            "quality_score": result.get("quality_score"),
        }

    async def execute_single_agent(self, agent_type: str, instructions: str = "") -> dict:
        """Run a single agent with default or custom instructions."""
        log.info("[Orchestrator] execute_single_agent: %s — %s", agent_type, instructions[:80] if instructions else "(default)")
        result = await self._bot.execute_single_agent(agent_type, instructions)
        log.info("[Orchestrator] Agent done — outputs=%d", len(result.get("outputs", [])))
        return result
