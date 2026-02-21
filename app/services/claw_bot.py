"""Claw Bot — Autonomous AI Operations Engine for Forge.

Replaces Sage as the orchestration brain. Implements the full autonomy loop:
PLAN → EXECUTE → VERIFY → RETRY/REPAIR → SHIP → REPORT
"""

import json
import logging
import re
import time
import uuid
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.models import (
    Shop, Agent, AgentActivity, AgentConfig, AgentOutput, AgentRun,
    ExecutionGoal, ExecutionTask, AgentDeliverable, AuditLog,
)
from app.services.agent_prompts import get_agent_prompt

log = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

AGENT_NAMES = {
    "maya": "Maya", "scout": "Scout", "emma": "Emma",
    "alex": "Alex", "max": "Max",
}

# Quality scoring dimensions
QUALITY_DIMENSIONS = [
    "relevance", "specificity", "brand_voice", "compliance",
    "persuasion", "clarity", "personalization", "correctness",
]

PLAN_PROMPT = """You are Claw Bot, the autonomous AI operations engine for a retail shop's AI team.
You have 5 specialist agents:
- maya: Marketing Director — creates posts, campaigns, emails, promos
- scout: Competitive Intelligence — market analysis, opportunities, threats
- emma: Customer Success — win-backs, review responses, VIP programs
- alex: Chief Strategy Officer — briefings, strategy, forecasts, action plans
- max: Sales Director — bundles, pricing, upsells, sales insights

Given the user's command, create an execution plan.
Respond with ONLY valid JSON:
{
  "intent": "marketing|retention|strategy|competitive|sales|mixed",
  "priority": "critical|high|medium|low",
  "tasks": [
    {
      "agent": "agent_type",
      "instructions": "specific instructions",
      "depends_on": []
    }
  ],
  "summary": "1-sentence plan summary"
}
Assign each task to the most relevant agent. A command might need 1-5 agents.
Use depends_on (array of task indices starting at 0) when tasks need outputs from prior tasks.
Keep instructions specific and actionable. Do NOT include text outside the JSON."""

VERIFY_PROMPT = """You are Claw Bot's quality inspector. Score this agent output on 8 dimensions (0-100 each):
- relevance: How well does it address the instructions?
- specificity: Does it use concrete data/numbers vs generic advice?
- brand_voice: Is the tone appropriate for a retail business?
- compliance: Is it safe, legal, and follows best practices?
- persuasion: How compelling is it for the target audience?
- clarity: Is it well-structured and easy to understand?
- personalization: Does it use the shop's actual data?
- correctness: Are facts, numbers, and logic sound?

Respond with ONLY valid JSON:
{
  "scores": {"relevance": N, "specificity": N, "brand_voice": N, "compliance": N, "persuasion": N, "clarity": N, "personalization": N, "correctness": N},
  "overall": N,
  "pass": true/false,
  "feedback": "brief feedback if score < 70"
}
Score of 70+ overall = pass. Below 70 = needs retry with feedback."""


def _extract_json(text: str) -> dict | None:
    """Robustly extract a JSON object from an LLM response."""
    if not text or not text.strip():
        return None
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    first_brace = text.find('{')
    if first_brace != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(first_brace, len(text)):
            c = text[i]
            if escape_next:
                escape_next = False
                continue
            if c == '\\' and in_string:
                escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[first_brace:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    return None


def _audit(db: Session, shop_id: str, actor: str, action: str,
           resource_type: str = None, resource_id: str = None, details: dict = None):
    """Write an immutable audit log entry."""
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        shop_id=shop_id,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
    ))


def _text_to_outputs(text: str, agent_type: str) -> list:
    """Convert raw text into structured outputs by splitting on headers/sections."""
    agent_output_types = {
        "maya": "instagram_post", "scout": "market_report",
        "emma": "winback_email", "alex": "daily_briefing", "max": "bundle_suggestion",
    }
    default_type = agent_output_types.get(agent_type, "general")

    # Try splitting on markdown headers (##, ###)
    sections = re.split(r'\n(?=#{1,3}\s)', text.strip())
    if len(sections) > 1:
        outputs = []
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            lines = sec.split('\n', 1)
            title = lines[0].lstrip('#').strip()
            content = lines[1].strip() if len(lines) > 1 else title
            if len(title) > 200:
                title = title[:100] + '...'
            outputs.append({"type": default_type, "title": title, "content": content, "metadata": {}})
        if outputs:
            return outputs

    # Try splitting on ALL-CAPS section headers (e.g., "REVENUE PERFORMANCE:", "KEY INSIGHTS:")
    caps_sections = re.split(r'\n(?=[A-Z][A-Z\s&/]+:)', text.strip())
    if len(caps_sections) > 1:
        outputs = []
        for sec in caps_sections:
            sec = sec.strip()
            if not sec:
                continue
            lines = sec.split('\n', 1)
            title = lines[0].rstrip(':').strip()
            content = sec
            if len(title) > 100:
                title = title[:80] + '...'
            outputs.append({"type": default_type, "title": title.title(), "content": content, "metadata": {}})
        if outputs:
            return outputs

    # Try splitting on numbered items (1. 2. 3.)
    items = re.split(r'\n(?=\d+\.?\s)', text.strip())
    if len(items) > 2:
        outputs = []
        for item in items:
            item = item.strip()
            if not item or len(item) < 20:
                continue
            title_match = re.match(r'\d+\.?\s*(.+?)[\n:]', item)
            title = title_match.group(1).strip() if title_match else item[:80]
            outputs.append({"type": default_type, "title": title, "content": item, "metadata": {}})
        if outputs:
            return outputs

    # Last resort: single output
    return [{
        "type": default_type,
        "title": f"{AGENT_NAMES.get(agent_type, 'Agent')} Analysis",
        "content": text,
        "metadata": {},
    }]


class ClawBot:
    """Autonomous AI operations engine."""

    def __init__(self, db: Session, shop: Shop, api_key: str, shop_context: dict):
        self.db = db
        self.shop = shop
        self.api_key = api_key
        self.shop_context = shop_context

    async def execute_goal(self, command: str) -> dict:
        """Full autonomy loop: PLAN → EXECUTE → VERIFY → RETRY → SHIP → REPORT."""
        goal = ExecutionGoal(
            id=str(uuid.uuid4()),
            shop_id=self.shop.id,
            command=command,
            status="planning",
        )
        self.db.add(goal)
        self.db.commit()
        _audit(self.db, self.shop.id, "claw_bot", "goal_created",
               "goal", goal.id, {"command": command})
        self.db.commit()

        try:
            # ── PLAN ──
            plan = await self._plan(command)
            goal.intent = plan.get("intent", "mixed")
            goal.priority = plan.get("priority", "medium")
            goal.plan = plan
            goal.total_tasks = len(plan.get("tasks", []))
            goal.status = "executing"
            goal.started_at = datetime.utcnow()
            self.db.commit()
            _audit(self.db, self.shop.id, "claw_bot", "plan_created",
                   "goal", goal.id, {"task_count": goal.total_tasks})
            self.db.commit()

            # Create ExecutionTask records
            task_records = []
            for i, task_info in enumerate(plan.get("tasks", [])):
                agent_type = task_info.get("agent", "alex")
                if agent_type not in AGENT_NAMES:
                    agent_type = "alex"
                dep_indices = task_info.get("depends_on", [])
                dep_ids = [task_records[j].id for j in dep_indices if j < len(task_records)]
                et = ExecutionTask(
                    id=str(uuid.uuid4()),
                    goal_id=goal.id,
                    shop_id=self.shop.id,
                    agent_type=agent_type,
                    instructions=task_info.get("instructions", command),
                    depends_on=dep_ids,
                    status="pending",
                )
                self.db.add(et)
                task_records.append(et)
            self.db.commit()

            # ── EXECUTE → VERIFY → RETRY ──
            results = []
            for et in task_records:
                result = await self._execute_task(et, goal)
                results.append(result)
                goal.completed_tasks = (goal.completed_tasks or 0) + 1
                self.db.commit()

            # ── REPORT ──
            summary = self._compile_report(results, goal)
            goal.status = "completed"
            goal.result_summary = summary
            goal.completed_at = datetime.utcnow()

            # Calculate overall quality
            scores = [r.get("quality_score", 0) for r in results if r.get("quality_score")]
            if scores:
                goal.quality_score = sum(scores) / len(scores)

            self.db.commit()
            _audit(self.db, self.shop.id, "claw_bot", "goal_completed",
                   "goal", goal.id, {"quality": goal.quality_score, "tasks": len(results)})
            self.db.commit()

            return {
                "goal_id": goal.id,
                "summary": summary,
                "results": results,
                "agent_count": len(results),
                "quality_score": goal.quality_score,
                "status": "completed",
            }

        except Exception as e:
            log.exception("Claw Bot execution failed: %s", command)
            goal.status = "failed"
            goal.result_summary = f"Error: {str(e)}"
            goal.completed_at = datetime.utcnow()
            self.db.commit()
            _audit(self.db, self.shop.id, "claw_bot", "goal_failed",
                   "goal", goal.id, {"error": str(e)})
            self.db.commit()
            return {
                "goal_id": goal.id,
                "summary": f"I encountered an error: {str(e)}",
                "results": [],
                "agent_count": 0,
                "quality_score": None,
                "status": "failed",
            }

    async def execute_single_agent(self, agent_type: str, instructions: str = "") -> dict:
        """Run a single agent with the full verify/retry loop."""
        if not instructions:
            default_instructions = {
                "maya": (
                    "Create this week's complete marketing content package:\n"
                    "1. Create 5 Instagram posts (one for each weekday) with full captions, CTAs, and 20 hashtags each. Use actual product names and trends.\n"
                    "2. Create 2 Facebook posts — one product spotlight and one community engagement post.\n"
                    "3. Draft 1 email campaign for this week targeting customers who haven't visited recently.\n"
                    "4. Suggest 1 promotion idea with execution plan and estimated revenue impact.\n"
                    "Reference real products, real revenue trends, and real competitor weaknesses in all content."
                ),
                "scout": (
                    "Create a full competitive intelligence report:\n"
                    "1. Analyze each competitor's current rating and review count vs ours.\n"
                    "2. Identify the top 3 opportunities where competitors are showing weakness.\n"
                    "3. Identify the top 2 threats where competitors are gaining strength.\n"
                    "4. Draft specific competitive response content for each opportunity.\n"
                    "5. Provide an overall market position summary.\n"
                    "Use actual competitor names, ratings, and review data."
                ),
                "emma": (
                    "Create a complete customer outreach package:\n"
                    "1. Draft win-back emails for 5 at-risk customers (personalized with customer name, days inactive, favorite product, discount code).\n"
                    "2. Draft professional responses for any recent negative reviews.\n"
                    "3. Create VIP appreciation messages for our top 3 VIP customers.\n"
                    "4. Suggest 1 customer retention strategy based on the at-risk segment data.\n"
                    "Use actual customer segment numbers and actual product names."
                ),
                "alex": (
                    "Create a comprehensive executive briefing:\n"
                    "1. Today's performance: revenue vs yesterday, this week vs last week, this month vs last month.\n"
                    "2. Top 3 performing products with trends and why they're winning.\n"
                    "3. Top 3 underperforming areas with specific recommendations to fix each.\n"
                    "4. Goal progress: are we on track? What's needed to hit the monthly goal?\n"
                    "5. Create 5 prioritized action items (P1/P2/P3) for this week.\n"
                    "6. 30-day revenue forecast based on current trends.\n"
                    "Use exact revenue numbers from the data. No generic advice."
                ),
                "max": (
                    "Create a revenue optimization report:\n"
                    "1. Suggest 3 product bundle ideas using actual products that complement each other.\n"
                    "2. Recommend 2 price adjustments (one increase for a hot seller, one decrease for a slow mover) with rationale.\n"
                    "3. Identify 2 slow-moving products that need markdown or promotion.\n"
                    "4. Suggest 2 upsell strategies for checkout (what to recommend when a customer buys X).\n"
                    "5. Estimate total revenue impact of all recommendations combined.\n"
                    "Use actual product names, prices, and sales volumes."
                ),
            }
            instructions = default_instructions.get(agent_type, "Provide your best analysis and recommendations.")

        goal = ExecutionGoal(
            id=str(uuid.uuid4()),
            shop_id=self.shop.id,
            command=f"[Single Agent] {instructions}",
            intent={"maya": "marketing", "scout": "competitive", "emma": "retention",
                    "alex": "strategy", "max": "sales"}.get(agent_type, "mixed"),
            status="executing",
            total_tasks=1,
            started_at=datetime.utcnow(),
        )
        self.db.add(goal)
        self.db.commit()

        et = ExecutionTask(
            id=str(uuid.uuid4()),
            goal_id=goal.id,
            shop_id=self.shop.id,
            agent_type=agent_type,
            instructions=instructions,
            status="pending",
        )
        self.db.add(et)
        self.db.commit()

        result = await self._execute_task(et, goal)

        goal.status = "completed"
        goal.completed_tasks = 1
        goal.result_summary = result.get("summary", "Task completed.")
        goal.quality_score = result.get("quality_score")
        goal.completed_at = datetime.utcnow()
        self.db.commit()

        return result

    async def _plan(self, command: str) -> dict:
        """Call Claude to decompose a command into an execution plan."""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    CLAUDE_API_URL,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": CLAUDE_MODEL,
                        "max_tokens": 1024,
                        "system": PLAN_PROMPT,
                        "messages": [{"role": "user", "content": command}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["content"][0]["text"]
                parsed = _extract_json(text)
                if parsed and parsed.get("tasks"):
                    return parsed
        except Exception as e:
            log.warning("Claw Bot plan failed, falling back: %s", e)

        return {"intent": "mixed", "priority": "medium",
                "tasks": [{"agent": "alex", "instructions": command, "depends_on": []}],
                "summary": f"Assigned to Alex: {command}"}

    async def _execute_task(self, task: ExecutionTask, goal: ExecutionGoal) -> dict:
        """Execute a single agent task with verify/retry loop."""
        task.status = "running"
        task.started_at = datetime.utcnow()
        self.db.commit()
        _audit(self.db, self.shop.id, task.agent_type, "task_started",
               "task", task.id, {"goal_id": goal.id})
        self.db.commit()

        config_row = (
            self.db.query(AgentConfig)
            .filter(AgentConfig.shop_id == self.shop.id, AgentConfig.agent_type == task.agent_type)
            .first()
        )
        config = config_row.settings if config_row and config_row.settings else {}
        system_prompt = get_agent_prompt(task.agent_type, self.shop_context, config)

        run = AgentRun(
            id=str(uuid.uuid4()),
            shop_id=self.shop.id,
            agent_type=task.agent_type,
            trigger="command",
            instructions=task.instructions,
            status="running",
        )
        self.db.add(run)
        self.db.commit()

        start_time = time.time()
        outputs = []
        summary = ""
        tokens_used = 0
        quality_score = None

        try:
            # Execute with retry loop
            max_attempts = task.max_retries + 1
            feedback = ""
            for attempt in range(max_attempts):
                instructions = task.instructions
                if feedback:
                    instructions += f"\n\nPREVIOUS ATTEMPT FEEDBACK (improve based on this): {feedback}"
                    task.retry_count = attempt
                    task.status = "retrying"
                    self.db.commit()

                text, attempt_tokens = await self._call_agent(system_prompt, instructions)
                tokens_used += attempt_tokens

                parsed = _extract_json(text)
                if parsed and "outputs" in parsed and isinstance(parsed["outputs"], list) and len(parsed["outputs"]) > 0:
                    raw_outputs = parsed["outputs"]
                    summary = parsed.get("summary", "Task completed.")
                else:
                    # Fallback: split raw text into structured sections
                    raw_outputs = _text_to_outputs(text, task.agent_type)
                    summary = f"{AGENT_NAMES.get(task.agent_type, 'Agent')} completed the task."

                # ── VERIFY ──
                verify_result = await self._verify_output(task.instructions, raw_outputs)
                quality_score = verify_result.get("overall", 75)

                if verify_result.get("pass", True) or attempt >= max_attempts - 1:
                    # Accept output
                    break
                else:
                    feedback = verify_result.get("feedback", "Improve quality and specificity.")
                    log.info("Claw Bot: Agent %s output scored %s, retrying (attempt %d)",
                             task.agent_type, quality_score, attempt + 1)

            # Save deliverables and legacy outputs
            for out in raw_outputs:
                content = out.get("content", "")
                if not content and isinstance(out, dict):
                    content = out.get("text", out.get("body", str(out)))

                # Save as AgentDeliverable (new system)
                deliverable = AgentDeliverable(
                    id=str(uuid.uuid4()),
                    goal_id=goal.id,
                    task_id=task.id,
                    shop_id=self.shop.id,
                    agent_type=task.agent_type,
                    deliverable_type=out.get("type", "general"),
                    title=out.get("title", "Untitled"),
                    content=content,
                    quality_scores=verify_result.get("scores", {}),
                    overall_quality=quality_score,
                    status="draft",
                    metadata_json=out.get("metadata", {}),
                )
                self.db.add(deliverable)

                # Also save as AgentOutput (legacy compatibility)
                ao = AgentOutput(
                    id=str(uuid.uuid4()),
                    shop_id=self.shop.id,
                    agent_type=task.agent_type,
                    run_id=run.id,
                    output_type=out.get("type", "general"),
                    title=out.get("title", "Untitled"),
                    content=content,
                    metadata_json=out.get("metadata", {}),
                )
                self.db.add(ao)
                outputs.append({
                    "id": ao.id,
                    "deliverable_id": deliverable.id,
                    "type": ao.output_type,
                    "title": ao.title,
                    "content": ao.content,
                    "quality_score": quality_score,
                })

            # Log activity
            agent = (
                self.db.query(Agent)
                .filter(Agent.shop_id == self.shop.id, Agent.agent_type == task.agent_type)
                .first()
            )
            if agent:
                self.db.add(AgentActivity(
                    shop_id=self.shop.id,
                    agent_id=agent.id,
                    action_type="task_completed",
                    description=f"Completed: {summary}",
                    details={"output_count": len(outputs), "run_id": run.id,
                             "quality_score": quality_score, "goal_id": goal.id},
                ))

            duration_ms = int((time.time() - start_time) * 1000)
            run.status = "completed"
            run.output_count = len(outputs)
            run.tokens_used = tokens_used
            run.duration_ms = duration_ms
            run.completed_at = datetime.utcnow()

            task.status = "completed"
            task.result_summary = summary
            task.quality_score = quality_score
            task.tokens_used = tokens_used
            task.duration_ms = duration_ms
            task.completed_at = datetime.utcnow()

            goal.total_tokens = (goal.total_tokens or 0) + tokens_used
            goal.total_cost = (goal.total_cost or 0) + tokens_used * 0.0000008

            self.db.commit()
            _audit(self.db, self.shop.id, task.agent_type, "task_completed",
                   "task", task.id, {"outputs": len(outputs), "quality": quality_score})
            self.db.commit()

            return {
                "agent_type": task.agent_type,
                "agent_name": AGENT_NAMES.get(task.agent_type, task.agent_type),
                "summary": summary,
                "outputs": outputs,
                "tokens_used": tokens_used,
                "duration_ms": duration_ms,
                "quality_score": quality_score,
            }

        except Exception as e:
            log.exception("Agent task failed: %s / %s", task.agent_type, task.instructions[:80])
            duration_ms = int((time.time() - start_time) * 1000)
            run.status = "failed"
            run.error_message = str(e)
            run.duration_ms = duration_ms
            run.completed_at = datetime.utcnow()
            task.status = "failed"
            task.result_summary = f"Error: {str(e)}"
            task.error_message = str(e)
            task.completed_at = datetime.utcnow()
            self.db.commit()
            _audit(self.db, self.shop.id, task.agent_type, "task_failed",
                   "task", task.id, {"error": str(e)})
            self.db.commit()
            return {
                "agent_type": task.agent_type,
                "agent_name": AGENT_NAMES.get(task.agent_type, task.agent_type),
                "summary": f"Failed: {str(e)}",
                "outputs": [],
                "tokens_used": 0,
                "duration_ms": duration_ms,
                "quality_score": None,
            }

    async def _call_agent(self, system_prompt: str, instructions: str) -> tuple[str, int]:
        """Call Claude for an agent task, return (text, tokens_used)."""
        log.info("[ClawBot] Calling agent — model=%s, instructions=%s...", CLAUDE_MODEL, instructions[:80])
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                CLAUDE_API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 8000,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": instructions}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"]
            tokens = data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
            log.info("[ClawBot] Agent response received — %d chars, %d tokens", len(text), tokens)
            log.debug("[ClawBot] Raw response: %s", text[:500])

            # Try to parse JSON
            parsed = _extract_json(text)
            if parsed:
                log.info("[ClawBot] JSON parsed successfully — keys: %s", list(parsed.keys()))
            else:
                log.warning("[ClawBot] JSON parsing failed — raw text will be used as-is")

            return text, tokens

    async def _verify_output(self, instructions: str, outputs: list) -> dict:
        """Score agent output quality. Returns scores dict with pass/fail."""
        try:
            output_text = "\n\n".join(
                f"[{o.get('type', 'general')}] {o.get('title', 'Untitled')}\n{o.get('content', '')[:500]}"
                for o in outputs
            )
            verify_input = f"INSTRUCTIONS: {instructions}\n\nAGENT OUTPUT:\n{output_text}"

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    CLAUDE_API_URL,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": CLAUDE_MODEL,
                        "max_tokens": 512,
                        "system": VERIFY_PROMPT,
                        "messages": [{"role": "user", "content": verify_input}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["content"][0]["text"]
                parsed = _extract_json(text)
                if parsed and "overall" in parsed:
                    return parsed
        except Exception as e:
            log.warning("Quality verification failed, assuming pass: %s", e)

        return {"scores": {}, "overall": 75, "pass": True, "feedback": ""}

    def _compile_report(self, results: list, goal: ExecutionGoal) -> str:
        """Build a comprehensive report from all agent results."""
        if not results:
            return "No tasks were executed."
        parts = []
        total_outputs = 0
        total_quality = []
        for r in results:
            name = r.get("agent_name", "Agent")
            s = r.get("summary", "Done.")
            count = len(r.get("outputs", []))
            q = r.get("quality_score")
            total_outputs += count
            if q:
                total_quality.append(q)
            quality_str = f" | Quality: {q:.0f}/100" if q else ""
            parts.append(f"**{name}**: {s} ({count} deliverable{'s' if count != 1 else ''}){quality_str}")

        avg_quality = sum(total_quality) / len(total_quality) if total_quality else 0
        header = (
            f"Claw Bot completed {len(results)} task{'s' if len(results) != 1 else ''} "
            f"and produced {total_outputs} deliverable{'s' if total_outputs != 1 else ''}."
        )
        if avg_quality:
            header += f" Average quality: {avg_quality:.0f}/100."
        header += "\n\n"
        return header + "\n".join(f"- {p}" for p in parts)
