"""OpenClaw Bridge — Routes AI calls through the real OpenClaw gateway.

The OpenClaw gateway runs as a Docker service and provides:
- POST /v1/responses — OpenResponses API (primary)
- POST /v1/chat/completions — OpenAI-compatible chat API (fallback)
- WebSocket RPC for real-time streaming

This bridge connects Forge's ClawBot to the real OpenClaw,
falling back to direct Anthropic API calls if OpenClaw is unavailable.
"""

import json
import logging
import os
from typing import AsyncIterator

import httpx

log = logging.getLogger(__name__)

# Config from environment (set by docker-compose)
OPENCLAW_GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "http://openclaw:18789")
OPENCLAW_GATEWAY_TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")

# Direct Anthropic fallback
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


class OpenClawBridge:
    """Bridge between Forge and the real OpenClaw gateway."""

    _available: bool | None = None  # Cached availability status

    @classmethod
    async def is_available(cls) -> bool:
        """Check if the OpenClaw gateway is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # The gateway serves its UI at / — any HTTP response means it's up
                resp = await client.get(OPENCLAW_GATEWAY_URL)
                cls._available = resp.status_code in (200, 301, 302, 401, 403)
                return cls._available
        except Exception:
            cls._available = False
            return False

    @classmethod
    async def get_status(cls) -> dict:
        """Get OpenClaw gateway status information."""
        status = {
            "gateway_url": OPENCLAW_GATEWAY_URL,
            "available": False,
            "version": None,
            "features": {
                "responses_api": True,
                "chat_completions": True,
                "web_browsing": True,
                "skills": True,
                "memory": True,
                "scheduling": True,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # Gateway serves UI at root — any response means it's up
                resp = await client.get(OPENCLAW_GATEWAY_URL)
                status["available"] = resp.status_code in (200, 301, 302, 401, 403)
        except Exception as e:
            log.debug("OpenClaw status check failed: %s", e)
        return status

    @classmethod
    async def send_message(
        cls,
        message: str,
        system_prompt: str = "",
        agent_id: str = "main",
        max_tokens: int = 8000,
        api_key: str = "",
    ) -> tuple[str, int]:
        """Send a message through OpenClaw and get a response.

        Returns (response_text, tokens_used).
        Falls back to direct Anthropic API if OpenClaw is unavailable.
        """
        # Try OpenClaw gateway first
        if OPENCLAW_GATEWAY_TOKEN:
            try:
                text, tokens = await cls._call_openclaw(
                    message, system_prompt, agent_id, max_tokens
                )
                if text:
                    return text, tokens
            except Exception as e:
                log.warning("[OpenClaw Bridge] Gateway call failed, falling back: %s", e)

        # Fallback to direct Anthropic API
        key = api_key or ANTHROPIC_API_KEY
        if not key:
            raise ValueError("No API key available — OpenClaw is down and no ANTHROPIC_API_KEY set")

        return await cls._call_anthropic_direct(message, system_prompt, max_tokens, key)

    @classmethod
    async def send_message_stream(
        cls,
        message: str,
        system_prompt: str = "",
        agent_id: str = "main",
        max_tokens: int = 4096,
        api_key: str = "",
    ) -> AsyncIterator[str]:
        """Stream a response from OpenClaw (or fallback to Anthropic).

        Yields text chunks as they arrive.
        """
        # Try OpenClaw streaming
        if OPENCLAW_GATEWAY_TOKEN:
            try:
                async for chunk in cls._stream_openclaw(
                    message, system_prompt, agent_id, max_tokens
                ):
                    yield chunk
                return
            except Exception as e:
                log.warning("[OpenClaw Bridge] Stream failed, falling back: %s", e)

        # Fallback to direct Anthropic streaming
        key = api_key or ANTHROPIC_API_KEY
        if not key:
            yield "Error: No API key available."
            return

        async for chunk in cls._stream_anthropic_direct(message, system_prompt, max_tokens, key):
            yield chunk

    # ── OpenClaw Gateway Calls ─────────────────────────────────────────────

    @classmethod
    async def _call_openclaw(
        cls, message: str, system_prompt: str, agent_id: str, max_tokens: int
    ) -> tuple[str, int]:
        """Call OpenClaw's /v1/responses endpoint."""
        payload = {
            "model": f"openclaw:{agent_id}",
            "input": message,
            "stream": False,
            "max_output_tokens": max_tokens,
        }
        if system_prompt:
            payload["instructions"] = system_prompt

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OPENCLAW_GATEWAY_URL}/v1/responses",
                headers={
                    **_auth_headers(),
                    "Content-Type": "application/json",
                    "x-openclaw-agent-id": agent_id,
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            # Extract text from OpenResponses format
            text = ""
            for output in data.get("output", []):
                if output.get("type") == "output_text":
                    text += output.get("text", "")
                elif output.get("type") == "message":
                    for content in output.get("content", []):
                        if content.get("type") == "text":
                            text += content.get("text", "")

            usage = data.get("usage", {})
            tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

            log.info("[OpenClaw Bridge] Response: %d chars, %d tokens", len(text), tokens)
            return text, tokens

    @classmethod
    async def _stream_openclaw(
        cls, message: str, system_prompt: str, agent_id: str, max_tokens: int
    ) -> AsyncIterator[str]:
        """Stream from OpenClaw's /v1/responses endpoint (SSE)."""
        payload = {
            "model": f"openclaw:{agent_id}",
            "input": message,
            "stream": True,
            "max_output_tokens": max_tokens,
        }
        if system_prompt:
            payload["instructions"] = system_prompt

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{OPENCLAW_GATEWAY_URL}/v1/responses",
                headers={
                    **_auth_headers(),
                    "Content-Type": "application/json",
                    "x-openclaw-agent-id": agent_id,
                },
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data.get("delta", "")
                        if delta:
                            yield delta
                    except json.JSONDecodeError:
                        continue

    # ── Direct Anthropic API Fallback ──────────────────────────────────────

    @classmethod
    async def _call_anthropic_direct(
        cls, message: str, system_prompt: str, max_tokens: int, api_key: str
    ) -> tuple[str, int]:
        """Direct Anthropic API call (fallback when OpenClaw is down)."""
        log.info("[OpenClaw Bridge] Falling back to direct Anthropic API")
        async with httpx.AsyncClient(timeout=120) as client:
            body = {
                "model": CLAUDE_MODEL,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": message}],
            }
            if system_prompt:
                body["system"] = system_prompt

            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"]
            tokens = (
                data.get("usage", {}).get("input_tokens", 0)
                + data.get("usage", {}).get("output_tokens", 0)
            )
            return text, tokens

    @classmethod
    async def _stream_anthropic_direct(
        cls, message: str, system_prompt: str, max_tokens: int, api_key: str
    ) -> AsyncIterator[str]:
        """Stream from direct Anthropic API (fallback)."""
        log.info("[OpenClaw Bridge] Streaming via direct Anthropic API (fallback)")
        async with httpx.AsyncClient(timeout=120) as client:
            body = {
                "model": CLAUDE_MODEL,
                "max_tokens": max_tokens,
                "stream": True,
                "messages": [{"role": "user", "content": message}],
            }
            if system_prompt:
                body["system"] = system_prompt

            async with client.stream(
                "POST",
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {}).get("text", "")
                            if delta:
                                yield delta
                    except json.JSONDecodeError:
                        continue


def _auth_headers() -> dict:
    """Build auth headers for OpenClaw gateway."""
    headers = {}
    if OPENCLAW_GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {OPENCLAW_GATEWAY_TOKEN}"
    return headers
