"""OpenClaw Engine — Autonomous AI operations engine for Forge.

Inspired by OpenClaw's architecture:
- Heartbeat daemon: periodic autonomous agent runs
- Memory system: agents learn from past interactions
- Task chaining: one agent's output feeds another
- Proactive insights: detect opportunities/threats automatically
- Scheduling: tasks run on configured schedules
- Web browsing: real competitor research via web scraping
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.models import (
    Shop, Agent, AgentMemory, ScheduledTask, ProactiveInsight,
    DailySnapshot, Customer, Competitor, Review, AgentDeliverable,
    ExecutionGoal, AgentOutput, AgentRun, User,
)

log = logging.getLogger(__name__)

# Heartbeat interval (seconds)
HEARTBEAT_INTERVAL = 900  # 15 minutes
INSIGHT_CHECK_INTERVAL = 3600  # 1 hour


class OpenClawEngine:
    """Autonomous engine that runs agents on schedule and generates proactive insights."""

    _instance = None
    _running = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._heartbeat_task = None
        self._insight_task = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self):
        """Start the autonomous engine (called on app startup)."""
        if self._running:
            return
        self._running = True
        log.info("[OpenClaw] Engine starting — heartbeat every %ds, insights every %ds",
                 HEARTBEAT_INTERVAL, INSIGHT_CHECK_INTERVAL)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._insight_task = asyncio.create_task(self._insight_loop())

    async def stop(self):
        """Stop the autonomous engine."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._insight_task:
            self._insight_task.cancel()
        log.info("[OpenClaw] Engine stopped")

    # ── Heartbeat Loop ────────────────────────────────────────────────────

    async def _heartbeat_loop(self):
        """Periodic loop that checks for scheduled tasks and runs them."""
        # Wait a bit after startup before first heartbeat
        await asyncio.sleep(30)
        while self._running:
            try:
                await self._heartbeat()
            except Exception as e:
                log.exception("[OpenClaw] Heartbeat error: %s", e)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _heartbeat(self):
        """Single heartbeat — check schedules and run due tasks."""
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            due_tasks = (
                db.query(ScheduledTask)
                .filter(
                    ScheduledTask.is_active == True,
                    ScheduledTask.next_run_at <= now,
                )
                .all()
            )
            if not due_tasks:
                return

            log.info("[OpenClaw] Heartbeat: %d scheduled task(s) due", len(due_tasks))

            for task in due_tasks:
                try:
                    await self._run_scheduled_task(db, task)
                except Exception as e:
                    log.exception("[OpenClaw] Scheduled task %s failed: %s", task.id, e)
                    task.last_status = "failed"
                    task.last_result_summary = str(e)
                    task.next_run_at = self._calculate_next_run(task)
                    db.commit()

        finally:
            db.close()

    async def _run_scheduled_task(self, db: Session, task: ScheduledTask):
        """Execute a single scheduled task."""
        log.info("[OpenClaw] Running scheduled task: %s (agent: %s)", task.task_name, task.agent_type)

        shop = db.query(Shop).filter(Shop.id == task.shop_id).first()
        if not shop:
            return

        api_key = self._get_api_key(db, shop)
        if not api_key:
            log.warning("[OpenClaw] No API key for shop %s, skipping", shop.id)
            return

        # Get user for context
        user = db.query(User).filter(User.id == shop.user_id).first()
        if not user:
            return

        # Build context and run
        from app.routers.ai import _get_shop_context
        from app.services.claw_bot import ClawBot
        context = _get_shop_context(db, shop, user)

        # Inject memory into instructions
        enhanced_instructions = await self.enhance_with_memory(
            db, task.shop_id, task.agent_type or "alex", task.instructions
        )

        bot = ClawBot(db, shop, api_key, context)

        if task.agent_type:
            result = await bot.execute_single_agent(task.agent_type, enhanced_instructions)
        else:
            result = await bot.execute_goal(enhanced_instructions)

        # Update task
        task.last_run_at = datetime.utcnow()
        task.run_count = (task.run_count or 0) + 1
        task.last_status = result.get("status", "completed") if "status" in result else "completed"
        task.last_result_summary = result.get("summary", "Completed.")
        task.next_run_at = self._calculate_next_run(task)
        db.commit()

        # Extract and save memories from the run
        await self.extract_memories(db, task.shop_id, task.agent_type or "alex", result)

        log.info("[OpenClaw] Scheduled task complete: %s — %s", task.task_name, task.last_status)

    # ── Insight Loop ──────────────────────────────────────────────────────

    async def _insight_loop(self):
        """Periodic loop that checks data and generates proactive insights."""
        await asyncio.sleep(60)  # Wait 1 min after startup
        while self._running:
            try:
                await self._generate_insights()
            except Exception as e:
                log.exception("[OpenClaw] Insight generation error: %s", e)
            await asyncio.sleep(INSIGHT_CHECK_INTERVAL)

    async def _generate_insights(self):
        """Analyze data across all shops and generate proactive insights."""
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            shops = db.query(Shop).all()
            for shop in shops:
                try:
                    await self._check_shop_insights(db, shop)
                except Exception as e:
                    log.warning("[OpenClaw] Insight check failed for shop %s: %s", shop.id, e)
        finally:
            db.close()

    async def _check_shop_insights(self, db: Session, shop: Shop):
        """Check for insight-worthy patterns in a shop's data."""
        now = datetime.utcnow()
        today = now.date()

        # Don't generate too many insights — check if we already have recent ones
        recent_count = (
            db.query(func.count(ProactiveInsight.id))
            .filter(
                ProactiveInsight.shop_id == shop.id,
                ProactiveInsight.created_at >= now - timedelta(hours=6),
            )
            .scalar()
        )
        if recent_count >= 3:
            return  # Already have enough recent insights

        # ── Check 1: Revenue anomaly ──
        yesterday = today - timedelta(days=1)
        snap_yesterday = (
            db.query(DailySnapshot)
            .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date == yesterday)
            .first()
        )
        avg_30d = (
            db.query(func.avg(DailySnapshot.total_revenue))
            .filter(
                DailySnapshot.shop_id == shop.id,
                DailySnapshot.date >= today - timedelta(days=30),
            )
            .scalar()
        )
        if snap_yesterday and avg_30d and float(avg_30d) > 0:
            rev = float(snap_yesterday.total_revenue)
            avg = float(avg_30d)
            if rev > avg * 1.3:
                pct = ((rev - avg) / avg) * 100
                self._create_insight(
                    db, shop.id, "alex", "milestone", "success",
                    f"Revenue spike: ${rev:,.0f} yesterday ({pct:+.0f}% above average)",
                    f"Yesterday's revenue of ${rev:,.0f} was {pct:.0f}% above your 30-day average of ${avg:,.0f}. "
                    f"Alex recommends analyzing what drove this spike — was it a specific product, promotion, or traffic source? "
                    f"Replicating this pattern could add ${(rev - avg) * 20:,.0f}/month to revenue.",
                    {"yesterday_revenue": rev, "avg_30d": avg, "pct_above": pct},
                )
            elif rev < avg * 0.6:
                pct = ((avg - rev) / avg) * 100
                self._create_insight(
                    db, shop.id, "alex", "alert", "warning",
                    f"Revenue dip: ${rev:,.0f} yesterday ({pct:.0f}% below average)",
                    f"Yesterday's revenue of ${rev:,.0f} was {pct:.0f}% below your 30-day average of ${avg:,.0f}. "
                    f"Alex recommends checking for issues: low traffic, out-of-stock bestsellers, or competitor promotions.",
                    {"yesterday_revenue": rev, "avg_30d": avg, "pct_below": pct},
                )

        # ── Check 2: At-risk customer growth ──
        at_risk = (
            db.query(func.count(Customer.id))
            .filter(Customer.shop_id == shop.id, Customer.segment == "at_risk")
            .scalar()
        ) or 0
        total = (
            db.query(func.count(Customer.id))
            .filter(Customer.shop_id == shop.id)
            .scalar()
        ) or 1
        at_risk_pct = (at_risk / total) * 100
        if at_risk_pct > 20:
            self._create_insight(
                db, shop.id, "emma", "threat", "warning",
                f"{at_risk} customers at risk ({at_risk_pct:.0f}% of base)",
                f"Emma detected that {at_risk} customers ({at_risk_pct:.0f}% of your customer base) are at risk of churning. "
                f"A targeted win-back campaign with personalized offers could recover an estimated "
                f"${at_risk * 50:,.0f} in annual revenue. Run Emma to generate win-back emails.",
                {"at_risk_count": at_risk, "total_customers": total, "at_risk_pct": at_risk_pct},
            )

        # ── Check 3: Competitor rating changes ──
        competitors = db.query(Competitor).filter(Competitor.shop_id == shop.id).all()
        own_reviews = (
            db.query(func.avg(Review.rating))
            .filter(Review.shop_id == shop.id, Review.is_own_shop == True)
            .scalar()
        )
        for comp in competitors:
            if comp.rating and own_reviews and float(comp.rating) < float(own_reviews) - 0.5:
                self._create_insight(
                    db, shop.id, "scout", "opportunity", "info",
                    f"Competitor weakness: {comp.name} rated {comp.rating}/5",
                    f"Scout detected that {comp.name} has a {comp.rating}/5 rating, significantly lower than your "
                    f"{float(own_reviews):.1f}/5. This is an opportunity to win their dissatisfied customers. "
                    f"Run Scout for competitive response content targeting their weakness.",
                    {"competitor": comp.name, "comp_rating": float(comp.rating),
                     "our_rating": float(own_reviews)},
                )
                break  # One competitor insight per cycle

        # ── Check 4: Unresponded negative reviews ──
        unresponded = (
            db.query(func.count(Review.id))
            .filter(
                Review.shop_id == shop.id,
                Review.is_own_shop == True,
                Review.rating <= 3,
                Review.response_text.is_(None),
            )
            .scalar()
        ) or 0
        if unresponded > 0:
            self._create_insight(
                db, shop.id, "emma", "suggestion", "info",
                f"{unresponded} negative review(s) need responses",
                f"Emma found {unresponded} negative review(s) (3 stars or below) without responses. "
                f"Responding to negative reviews within 24 hours can improve perception by 33%. "
                f"Run Emma to draft professional responses.",
                {"unresponded_count": unresponded},
            )

    def _create_insight(self, db: Session, shop_id: str, agent_type: str,
                        insight_type: str, severity: str, title: str,
                        content: str, data: dict):
        """Create a proactive insight if a similar one doesn't exist recently."""
        # Check for duplicate (same type and similar title in last 24h)
        exists = (
            db.query(ProactiveInsight)
            .filter(
                ProactiveInsight.shop_id == shop_id,
                ProactiveInsight.insight_type == insight_type,
                ProactiveInsight.title == title,
                ProactiveInsight.created_at >= datetime.utcnow() - timedelta(hours=24),
            )
            .first()
        )
        if exists:
            return

        db.add(ProactiveInsight(
            id=str(uuid.uuid4()),
            shop_id=shop_id,
            agent_type=agent_type,
            insight_type=insight_type,
            severity=severity,
            title=title,
            content=content,
            data_snapshot=data,
            expires_at=datetime.utcnow() + timedelta(hours=48),
        ))
        db.commit()
        log.info("[OpenClaw] Created insight: %s — %s", insight_type, title[:60])

    # ── Memory System ─────────────────────────────────────────────────────

    async def enhance_with_memory(self, db: Session, shop_id: str,
                                   agent_type: str, instructions: str) -> str:
        """Inject relevant memories into agent instructions."""
        memories = (
            db.query(AgentMemory)
            .filter(
                AgentMemory.shop_id == shop_id,
                AgentMemory.agent_type == agent_type,
            )
            .order_by(desc(AgentMemory.importance), desc(AgentMemory.created_at))
            .limit(5)
            .all()
        )
        if not memories:
            return instructions

        memory_block = "\n".join(f"- {m.content}" for m in memories)

        # Update access counts
        for m in memories:
            m.access_count = (m.access_count or 0) + 1
            m.last_accessed = datetime.utcnow()
        db.commit()

        return (
            f"{instructions}\n\n"
            f"MEMORY (learnings from previous runs — use these to improve your output):\n"
            f"{memory_block}"
        )

    async def extract_memories(self, db: Session, shop_id: str,
                                agent_type: str, result: dict):
        """Extract key insights from agent output and save as memories."""
        outputs = result.get("outputs", [])
        if not outputs:
            return

        # Extract key facts from outputs
        for output in outputs[:3]:
            content = output.get("content", "")
            title = output.get("title", "")
            if not content or len(content) < 50:
                continue

            # Save concise memory about what was produced
            memory_content = f"Previously generated '{title}' — "
            if "revenue" in content.lower():
                rev_match = re.search(r'\$[\d,]+(?:\.\d{2})?', content)
                if rev_match:
                    memory_content += f"referenced revenue: {rev_match.group(0)}. "
            if "customer" in content.lower():
                memory_content += "included customer-focused content. "
            if "competitor" in content.lower():
                memory_content += "included competitive analysis. "

            memory_content = memory_content[:300]  # Keep memories concise

            # Don't save duplicate memories
            existing = (
                db.query(AgentMemory)
                .filter(
                    AgentMemory.shop_id == shop_id,
                    AgentMemory.agent_type == agent_type,
                    AgentMemory.content == memory_content,
                )
                .first()
            )
            if existing:
                continue

            db.add(AgentMemory(
                id=str(uuid.uuid4()),
                shop_id=shop_id,
                agent_type=agent_type,
                memory_type="pattern",
                content=memory_content,
                importance=0.5,
                source_goal_id=result.get("goal_id"),
                metadata_json={"output_type": output.get("type"), "title": title},
            ))

        # Prune old memories (keep top 20 per agent)
        all_memories = (
            db.query(AgentMemory)
            .filter(
                AgentMemory.shop_id == shop_id,
                AgentMemory.agent_type == agent_type,
            )
            .order_by(desc(AgentMemory.importance), desc(AgentMemory.access_count))
            .all()
        )
        if len(all_memories) > 20:
            for m in all_memories[20:]:
                db.delete(m)

        db.commit()

    # ── Task Chaining ─────────────────────────────────────────────────────

    async def chain_agents(self, db: Session, shop: Shop, api_key: str,
                           context: dict, chain: list) -> list:
        """Execute a chain of agent tasks where each feeds into the next.

        chain = [
            {"agent": "scout", "instructions": "Find competitor weaknesses"},
            {"agent": "maya", "instructions": "Create content targeting {prior_output}"},
        ]
        """
        from app.services.claw_bot import ClawBot

        results = []
        prior_output = ""

        for step in chain:
            agent = step["agent"]
            instructions = step["instructions"]

            # Inject prior agent's output
            if prior_output and "{prior_output}" in instructions:
                instructions = instructions.replace("{prior_output}", prior_output[:2000])
            elif prior_output:
                instructions += f"\n\nCONTEXT FROM PREVIOUS AGENT:\n{prior_output[:2000]}"

            # Enhance with memory
            instructions = await self.enhance_with_memory(db, shop.id, agent, instructions)

            bot = ClawBot(db, shop, api_key, context)
            result = await bot.execute_single_agent(agent, instructions)
            results.append(result)

            # Collect output for next step
            outputs = result.get("outputs", [])
            if outputs:
                prior_output = "\n\n".join(
                    f"[{o.get('type', 'output')}] {o.get('title', '')}: {o.get('content', '')[:500]}"
                    for o in outputs[:3]
                )

            # Save memories from this step
            await self.extract_memories(db, shop.id, agent, result)

        return results

    # ── Scheduling ────────────────────────────────────────────────────────

    def create_schedule(self, db: Session, shop_id: str, task_name: str,
                        agent_type: str, instructions: str,
                        schedule_type: str, schedule_config: dict) -> ScheduledTask:
        """Create a new scheduled task."""
        task = ScheduledTask(
            id=str(uuid.uuid4()),
            shop_id=shop_id,
            task_name=task_name,
            agent_type=agent_type,
            instructions=instructions,
            schedule_type=schedule_type,
            schedule_config=schedule_config,
            is_active=True,
            next_run_at=self._calculate_next_run_from_config(schedule_type, schedule_config),
        )
        db.add(task)
        db.commit()
        log.info("[OpenClaw] Created schedule: %s — %s (%s)", task_name, schedule_type, agent_type)
        return task

    def seed_default_schedules(self, db: Session, shop_id: str):
        """Seed default scheduled tasks for a shop."""
        existing = db.query(ScheduledTask).filter(ScheduledTask.shop_id == shop_id).first()
        if existing:
            return  # Already seeded

        defaults = [
            {
                "task_name": "Morning Briefing",
                "agent_type": "alex",
                "instructions": "Create today's executive briefing with revenue performance, key metrics, and top 3 action items.",
                "schedule_type": "daily",
                "schedule_config": {"hour": 8, "minute": 0},
            },
            {
                "task_name": "Weekly Content Package",
                "agent_type": "maya",
                "instructions": "Create this week's complete social media content package with 5 Instagram posts, 2 Facebook posts, and 1 email campaign.",
                "schedule_type": "weekly",
                "schedule_config": {"day": "monday", "hour": 9, "minute": 0},
            },
            {
                "task_name": "Competitor Check",
                "agent_type": "scout",
                "instructions": "Run a competitive intelligence scan. Check competitor ratings, recent reviews, and any new promotions or threats.",
                "schedule_type": "weekly",
                "schedule_config": {"day": "wednesday", "hour": 10, "minute": 0},
            },
            {
                "task_name": "Customer Health Check",
                "agent_type": "emma",
                "instructions": "Check for at-risk customers, unresponded reviews, and VIP engagement opportunities. Draft win-back emails for anyone inactive 30+ days.",
                "schedule_type": "weekly",
                "schedule_config": {"day": "tuesday", "hour": 9, "minute": 0},
            },
            {
                "task_name": "Revenue Optimization Scan",
                "agent_type": "max",
                "instructions": "Analyze current pricing, identify slow movers, suggest bundle opportunities, and estimate revenue impact of recommendations.",
                "schedule_type": "weekly",
                "schedule_config": {"day": "thursday", "hour": 10, "minute": 0},
            },
        ]

        for d in defaults:
            self.create_schedule(db, shop_id, **d)

        log.info("[OpenClaw] Seeded %d default schedules for shop %s", len(defaults), shop_id)

    def _calculate_next_run(self, task: ScheduledTask) -> datetime:
        """Calculate the next run time for a scheduled task."""
        return self._calculate_next_run_from_config(task.schedule_type, task.schedule_config)

    def _calculate_next_run_from_config(self, schedule_type: str, config: dict) -> datetime:
        """Calculate next run time from schedule config."""
        now = datetime.utcnow()
        hour = config.get("hour", 9)
        minute = config.get("minute", 0)

        if schedule_type == "hourly":
            return now + timedelta(hours=1)
        elif schedule_type == "daily":
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run
        elif schedule_type == "weekly":
            day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                       "friday": 4, "saturday": 5, "sunday": 6}
            target_day = day_map.get(config.get("day", "monday"), 0)
            days_ahead = target_day - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_run = (now + timedelta(days=days_ahead)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            return next_run
        elif schedule_type == "interval":
            interval_minutes = config.get("interval_minutes", 60)
            return now + timedelta(minutes=interval_minutes)
        else:
            return now + timedelta(hours=24)

    # ── Web Research Integration ──────────────────────────────────────────

    async def run_web_research(self, db: Session, shop: Shop) -> dict:
        """Run comprehensive web research for a shop."""
        from app.services.web_researcher import WebResearcher
        researcher = WebResearcher(db, shop.id)

        results = {"competitor_research": [], "market_trends": None}

        # Research competitors
        competitors = db.query(Competitor).filter(Competitor.shop_id == shop.id).all()
        if competitors:
            comp_list = [{"name": c.name} for c in competitors]
            results["competitor_research"] = await researcher.search_all_competitors(
                comp_list, shop.city or ""
            )

        # Research market trends
        if shop.category:
            results["market_trends"] = await researcher.search_market_trends(
                shop.category, shop.city or ""
            )

        return results

    # ── Helpers ───────────────────────────────────────────────────────────

    def _get_api_key(self, db: Session, shop: Shop) -> str:
        """Get API key for a shop."""
        from app.models import ShopSettings
        from app.config import settings
        try:
            s = db.query(ShopSettings).filter(ShopSettings.shop_id == shop.id).first()
            if s and hasattr(s, 'anthropic_api_key') and s.anthropic_api_key:
                return s.anthropic_api_key.strip()
        except Exception:
            pass
        if settings.ANTHROPIC_API_KEY:
            return settings.ANTHROPIC_API_KEY.strip()
        return os.environ.get("ANTHROPIC_API_KEY", "").strip()
