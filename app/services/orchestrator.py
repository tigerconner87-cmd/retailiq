"""Task orchestrator — decomposes commands via Sage, dispatches to agents, compiles results."""

import json
import logging
import re
import time
import uuid
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.models import (
    Shop, Agent, AgentActivity, AgentConfig,
    AgentOutput, AgentRun, TaskGroup, OrchestratedTask,
)
from app.services.agent_prompts import get_agent_prompt

log = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

AGENT_NAMES = {
    "maya": "Maya", "scout": "Scout", "emma": "Emma",
    "alex": "Alex", "max": "Max",
}

DECOMPOSE_PROMPT = """You are Sage, the AI orchestrator for a retail shop's AI team.
You have 5 agents:
- maya: Marketing Director — creates posts, campaigns, emails, promos
- scout: Competitive Intelligence — market analysis, opportunities, threats
- emma: Customer Success — win-backs, review responses, VIP programs
- alex: Chief Strategy Officer — briefings, strategy, forecasts, action plans
- max: Sales Director — bundles, pricing, upsells, sales insights

Given the user's command, decompose it into tasks for the appropriate agents.
Respond with ONLY valid JSON:
{
  "tasks": [
    {"agent": "agent_type", "instructions": "specific instructions for this agent"}
  ]
}
Assign each task to the most relevant agent. A command might need 1-5 agents.
Keep instructions specific and actionable. Do NOT include text outside the JSON."""


def _extract_json(text: str) -> dict | None:
    """Robustly extract a JSON object from an LLM response.

    Handles:
    - Pure JSON
    - JSON wrapped in ```json ... ``` code blocks
    - JSON preceded/followed by explanatory text
    - Multiple code blocks (takes the first)
    """
    if not text or not text.strip():
        return None

    # 1. Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from markdown code blocks
    code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Find the outermost JSON object by brace matching
    first_brace = text.find('{')
    if first_brace != -1:
        # Find the matching closing brace
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


class TaskOrchestrator:
    def __init__(self, db: Session, shop: Shop, api_key: str, shop_context: dict):
        self.db = db
        self.shop = shop
        self.api_key = api_key
        self.shop_context = shop_context

    async def process_command(self, command: str) -> dict:
        """Decompose a command via Sage, execute agent tasks, return compiled summary."""
        # Create task group
        group = TaskGroup(
            id=str(uuid.uuid4()),
            shop_id=self.shop.id,
            command=command,
            status="running",
        )
        self.db.add(group)
        self.db.commit()

        try:
            # Decompose command
            task_list = await self._decompose_command(command)
            group.agent_count = len(task_list)
            self.db.commit()

            # Create orchestrated tasks
            results = []
            for task_info in task_list:
                agent_type = task_info.get("agent", "alex")
                # Validate agent type
                if agent_type not in AGENT_NAMES:
                    agent_type = "alex"
                instructions = task_info.get("instructions", command)
                ot = OrchestratedTask(
                    id=str(uuid.uuid4()),
                    group_id=group.id,
                    shop_id=self.shop.id,
                    agent_type=agent_type,
                    instructions=instructions,
                    status="pending",
                )
                self.db.add(ot)
                self.db.commit()

                # Execute task
                result = await self._run_agent_task(ot)
                results.append(result)
                group.completed_count += 1
                self.db.commit()

            # Compile summary
            summary = self._compile_summary(results)
            group.status = "completed"
            group.summary = summary
            group.completed_at = datetime.utcnow()
            self.db.commit()

            return {
                "group_id": group.id,
                "summary": summary,
                "results": results,
                "agent_count": len(results),
            }

        except Exception as e:
            log.exception("Orchestration failed for command: %s", command)
            group.status = "failed"
            group.summary = f"Error: {str(e)}"
            self.db.commit()
            return {
                "group_id": group.id,
                "summary": f"I encountered an error while coordinating the team: {str(e)}",
                "results": [],
                "agent_count": 0,
            }

    async def execute_single_agent(self, agent_type: str, instructions: str = "") -> dict:
        """Run a single agent with default or custom instructions."""
        if not instructions:
            default_instructions = {
                "maya": "Create 3 engaging social media posts for our shop based on current products and trends.",
                "scout": "Provide a competitive intelligence briefing with opportunities and threats.",
                "emma": "Identify at-risk customers and draft win-back emails. Also draft responses to any recent negative reviews.",
                "alex": "Create a daily business briefing with key metrics, trends, and recommended actions.",
                "max": "Analyze current product performance and suggest 2 bundles and 2 pricing optimizations.",
            }
            instructions = default_instructions.get(agent_type, "Provide your best analysis and recommendations.")

        # Create a single-task group
        group = TaskGroup(
            id=str(uuid.uuid4()),
            shop_id=self.shop.id,
            command=f"[Single Agent] {instructions}",
            status="running",
            agent_count=1,
        )
        self.db.add(group)
        self.db.commit()

        ot = OrchestratedTask(
            id=str(uuid.uuid4()),
            group_id=group.id,
            shop_id=self.shop.id,
            agent_type=agent_type,
            instructions=instructions,
            status="pending",
        )
        self.db.add(ot)
        self.db.commit()

        result = await self._run_agent_task(ot)

        group.status = "completed"
        group.completed_count = 1
        group.summary = result.get("summary", "Task completed.")
        group.completed_at = datetime.utcnow()
        self.db.commit()

        return result

    async def _decompose_command(self, command: str) -> list:
        """Call Claude to decompose a multi-agent command into individual tasks."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
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
                        "system": DECOMPOSE_PROMPT,
                        "messages": [{"role": "user", "content": command}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["content"][0]["text"]
                parsed = _extract_json(text)
                if parsed:
                    tasks = parsed.get("tasks", [])
                    if tasks:
                        return tasks
        except Exception as e:
            log.warning("Decompose failed, falling back to alex: %s", e)

        # Fallback: assign to alex
        return [{"agent": "alex", "instructions": command}]

    async def _run_agent_task(self, task: OrchestratedTask) -> dict:
        """Execute a single agent task — call Claude, parse output, save records."""
        task.status = "running"
        task.started_at = datetime.utcnow()
        self.db.commit()

        # Get agent config
        config_row = (
            self.db.query(AgentConfig)
            .filter(AgentConfig.shop_id == self.shop.id, AgentConfig.agent_type == task.agent_type)
            .first()
        )
        config = config_row.settings if config_row and config_row.settings else {}

        # Build prompt
        system_prompt = get_agent_prompt(task.agent_type, self.shop_context, config)

        # Create run record
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
                        "max_tokens": 4096,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": task.instructions}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["content"][0]["text"]
                tokens_used = data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)

                log.info("Agent %s raw response length: %d chars", task.agent_type, len(text))

                # Robust JSON extraction
                parsed = _extract_json(text)
                if parsed and "outputs" in parsed and isinstance(parsed["outputs"], list) and len(parsed["outputs"]) > 0:
                    raw_outputs = parsed["outputs"]
                    summary = parsed.get("summary", "Task completed.")
                else:
                    # Fallback: wrap entire response as a single output
                    log.warning("Agent %s: Could not parse structured outputs, using raw text fallback", task.agent_type)
                    raw_outputs = [{
                        "type": "general",
                        "title": f"{AGENT_NAMES.get(task.agent_type, 'Agent')} Response",
                        "content": text,
                        "metadata": {},
                    }]
                    summary = f"{AGENT_NAMES.get(task.agent_type, 'Agent')} completed the task."

                # Save outputs
                for out in raw_outputs:
                    content = out.get("content", "")
                    if not content and isinstance(out, dict):
                        # Some models may use 'text' or 'body' instead
                        content = out.get("text", out.get("body", str(out)))
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
                        "type": ao.output_type,
                        "title": ao.title,
                        "content": ao.content,
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
                        details={"output_count": len(outputs), "run_id": run.id},
                    ))

                duration_ms = int((time.time() - start_time) * 1000)
                run.status = "completed"
                run.output_count = len(outputs)
                run.tokens_used = tokens_used
                run.duration_ms = duration_ms
                run.completed_at = datetime.utcnow()

                task.status = "completed"
                task.result_summary = summary
                task.tokens_used = tokens_used
                task.completed_at = datetime.utcnow()
                self.db.commit()

                return {
                    "agent_type": task.agent_type,
                    "agent_name": AGENT_NAMES.get(task.agent_type, task.agent_type),
                    "summary": summary,
                    "outputs": outputs,
                    "tokens_used": tokens_used,
                    "duration_ms": duration_ms,
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
            task.completed_at = datetime.utcnow()
            self.db.commit()
            return {
                "agent_type": task.agent_type,
                "agent_name": AGENT_NAMES.get(task.agent_type, task.agent_type),
                "summary": f"Failed: {str(e)}",
                "outputs": [],
                "tokens_used": 0,
                "duration_ms": duration_ms,
            }

    def _compile_summary(self, results: list) -> str:
        """Build a readable summary from all agent results."""
        if not results:
            return "No tasks were executed."
        parts = []
        total_outputs = 0
        for r in results:
            name = r.get("agent_name", "Agent")
            s = r.get("summary", "Done.")
            count = len(r.get("outputs", []))
            total_outputs += count
            parts.append(f"**{name}**: {s} ({count} output{'s' if count != 1 else ''})")
        header = f"Team completed {len(results)} task{'s' if len(results) != 1 else ''} and produced {total_outputs} output{'s' if total_outputs != 1 else ''}:\n\n"
        return header + "\n".join(f"- {p}" for p in parts)
