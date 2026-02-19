"""RetailIQ AI Assistant Service.

Provides AI-powered chat, content generation, and email editing
using the Anthropic API with smart fallback responses.
"""

import json
import logging
import time
from datetime import datetime

import httpx

log = logging.getLogger(__name__)

# Rate limit: 50 requests per user per day
_rate_limits: dict[str, list[float]] = {}
DAILY_LIMIT = 50


def _check_rate_limit(user_id: str) -> bool:
    """Return True if user is within rate limit."""
    now = time.time()
    day_start = now - 86400
    if user_id not in _rate_limits:
        _rate_limits[user_id] = []
    _rate_limits[user_id] = [t for t in _rate_limits[user_id] if t > day_start]
    if len(_rate_limits[user_id]) >= DAILY_LIMIT:
        return False
    _rate_limits[user_id].append(now)
    return True


def get_remaining_requests(user_id: str) -> int:
    """Get remaining AI requests for the day."""
    now = time.time()
    day_start = now - 86400
    if user_id not in _rate_limits:
        return DAILY_LIMIT
    active = [t for t in _rate_limits[user_id] if t > day_start]
    return max(0, DAILY_LIMIT - len(active))


SYSTEM_PROMPT = """You are RetailIQ AI, an expert retail business assistant embedded in a sales intelligence dashboard.

You help small retail shop owners with:
- Sales analysis and strategy
- Customer retention and engagement
- Marketing content creation
- Competitor analysis
- Inventory and pricing decisions
- Business growth advice

Guidelines:
- Be concise and actionable — shop owners are busy
- Use specific numbers when possible
- Suggest practical, low-cost strategies
- Speak in a friendly, encouraging tone
- When asked about data, remind users to check their dashboard sections
- Format responses with markdown for readability
- Keep responses under 300 words unless the user asks for detail"""

EMAIL_REWRITE_PROMPT = """You are RetailIQ AI, an expert email copywriter for retail businesses.

Rewrite the following email to be more engaging, personal, and likely to drive action.
Keep the same core message but improve:
- Subject line (make it compelling, under 60 chars)
- Opening hook
- Call to action
- Overall tone (warm, personal, urgent but not pushy)
- Keep it concise — under 200 words for the body

Return your response in this exact JSON format:
{"subject": "new subject line", "body": "new email body text"}"""

CONTENT_GEN_PROMPT = """You are RetailIQ AI, an expert content creator for retail businesses.

Generate marketing content based on the user's request. Be creative, on-brand, and action-oriented.
Include relevant emojis. Keep copy punchy and engaging.

For social posts: include caption, hashtags, and best posting time.
For promotions: include headline, description, terms, and urgency element.
For ad copy: include headline, body, and call-to-action."""


# ── Fallback responses when no API key is configured ───────────────────────

_FALLBACK_RESPONSES = {
    "greeting": [
        "Hey there! 👋 I'm RetailIQ AI, your retail business assistant. I can help you with:\n\n"
        "- **Sales strategies** — boost revenue with data-driven tips\n"
        "- **Email campaigns** — rewrite and improve your marketing emails\n"
        "- **Content creation** — social posts, promotions, ad copy\n"
        "- **Customer insights** — retention, win-back, segmentation advice\n"
        "- **Competitor analysis** — understand your market position\n\n"
        "What would you like help with today?",
    ],
    "sales": [
        "📊 **Quick Sales Tips for Retail:**\n\n"
        "1. **Bundle slow movers** with bestsellers — increases AOV by 15-25%\n"
        "2. **Create urgency** — 'Only 3 left!' drives 40% more conversions\n"
        "3. **Upsell at checkout** — suggest complementary items (adds $5-15 per transaction)\n"
        "4. **Track your peak hours** — schedule your best staff during high-traffic times\n"
        "5. **Offer loyalty rewards** — repeat customers spend 67% more than new ones\n\n"
        "Check your **Sales** and **Overview** tabs for detailed data on your specific patterns!",
    ],
    "marketing": [
        "📱 **Marketing Quick Wins:**\n\n"
        "1. **Post consistently** — 3-4x per week on Instagram/Facebook\n"
        "2. **Use customer photos** — UGC gets 4x more engagement\n"
        "3. **Email your list weekly** — even a simple 'New This Week' drives traffic\n"
        "4. **Run flash sales** — 24-hour sales create FOMO and urgency\n"
        "5. **Partner locally** — cross-promote with nearby businesses\n\n"
        "Head to your **Marketing** tab to see AI-generated content ready to use!",
    ],
    "customers": [
        "👥 **Customer Retention Strategies:**\n\n"
        "1. **Segment your customers** — VIPs, regulars, at-risk, and lost\n"
        "2. **Win back lapsed customers** — a 15% off 'We miss you' email works wonders\n"
        "3. **Reward VIPs** — early access, exclusive deals, personal thank-yous\n"
        "4. **Collect emails at checkout** — your email list is your most valuable asset\n"
        "5. **Follow up after purchase** — a thank-you email boosts repeat visits by 30%\n\n"
        "Check your **Customers** tab for segment breakdowns and the **Win-Back** section for campaigns!",
    ],
    "competitors": [
        "🏆 **Competitor Analysis Tips:**\n\n"
        "1. **Monitor their reviews** — negative reviews reveal opportunities for you\n"
        "2. **Track their pricing** — know where you're competitive\n"
        "3. **Study their social** — see what content gets engagement\n"
        "4. **Differentiate on service** — small shops win with personal touch\n"
        "5. **Respond to their weaknesses** — if they're slow, emphasize your speed\n\n"
        "Your **Competitors** tab tracks nearby businesses and their review trends!",
    ],
    "email": [
        "✉️ **Email Campaign Best Practices:**\n\n"
        "1. **Subject line is everything** — keep it under 50 chars, create curiosity\n"
        "2. **Personalize** — use {{first_name}} and reference past purchases\n"
        "3. **One clear CTA** — don't give too many choices\n"
        "4. **Send at the right time** — Tuesday-Thursday, 10am-2pm typically works best\n"
        "5. **A/B test subjects** — even small changes can boost opens 20%+\n\n"
        "Use the **Email Campaigns** tab in Marketing to see ready-to-send templates!",
    ],
    "default": [
        "Great question! Here are some thoughts:\n\n"
        "As a retail business owner, the key to growth is focusing on three pillars:\n\n"
        "1. **Increase traffic** — marketing, local SEO, social media\n"
        "2. **Increase conversion** — merchandising, staff training, store layout\n"
        "3. **Increase basket size** — upselling, bundling, loyalty programs\n\n"
        "Your RetailIQ dashboard tracks all of these metrics. I'd recommend:\n"
        "- Check your **Daily Briefing** for today's action items\n"
        "- Review **Sales** trends to spot patterns\n"
        "- Use the **Marketing** tab for ready-to-use content\n\n"
        "Want me to dive deeper into any of these areas?",
    ],
}


def _classify_query(message: str) -> str:
    """Simple keyword classifier for fallback responses."""
    msg = message.lower()
    greetings = ["hello", "hi", "hey", "help", "what can you", "who are you", "start"]
    if any(g in msg for g in greetings):
        return "greeting"
    if any(w in msg for w in ["sale", "revenue", "profit", "price", "discount", "aov", "transaction"]):
        return "sales"
    if any(w in msg for w in ["market", "social", "post", "instagram", "facebook", "content", "promote", "ad "]):
        return "marketing"
    if any(w in msg for w in ["customer", "retain", "churn", "loyal", "repeat", "segment", "win back", "winback"]):
        return "customers"
    if any(w in msg for w in ["competitor", "competition", "rival", "nearby", "vs ", "versus"]):
        return "competitors"
    if any(w in msg for w in ["email", "campaign", "newsletter", "subject line", "open rate"]):
        return "email"
    return "default"


def _get_fallback_response(message: str) -> str:
    """Return a helpful pre-built response based on message classification."""
    category = _classify_query(message)
    responses = _FALLBACK_RESPONSES.get(category, _FALLBACK_RESPONSES["default"])
    return responses[0]


async def chat(
    user_id: str,
    message: str,
    conversation_history: list[dict] | None = None,
    api_key: str = "",
    shop_context: dict | None = None,
) -> dict:
    """
    Process a chat message and return AI response.

    Uses Anthropic API if key is available, otherwise returns smart fallback.
    """
    if not _check_rate_limit(user_id):
        return {
            "response": "⚠️ You've reached the daily limit of 50 AI requests. Your limit resets in 24 hours.",
            "source": "rate_limit",
            "remaining": 0,
        }

    remaining = get_remaining_requests(user_id)

    # Try Anthropic API if key is configured
    if api_key:
        try:
            result = await _call_anthropic(message, conversation_history or [], api_key, shop_context)
            return {"response": result, "source": "anthropic", "remaining": remaining}
        except Exception as e:
            log.warning("Anthropic API error: %s — falling back", e)

    # Fallback response
    response = _get_fallback_response(message)
    return {"response": response, "source": "fallback", "remaining": remaining}


async def rewrite_email(
    subject: str,
    body: str,
    api_key: str = "",
    shop_name: str = "",
) -> dict:
    """Rewrite an email campaign to be more engaging."""
    if api_key:
        try:
            prompt = f"Shop name: {shop_name}\n\nOriginal subject: {subject}\n\nOriginal body:\n{body}"
            result = await _call_anthropic(prompt, [], api_key, system_override=EMAIL_REWRITE_PROMPT)
            # Try to parse JSON response
            try:
                parsed = json.loads(result)
                return {"subject": parsed["subject"], "body": parsed["body"], "source": "anthropic"}
            except (json.JSONDecodeError, KeyError):
                return {"subject": subject, "body": result, "source": "anthropic"}
        except Exception as e:
            log.warning("Anthropic API error on email rewrite: %s", e)

    # Fallback: improve the email with simple transformations
    improved_subject = subject
    if not subject.endswith(("!", "?", "...")):
        improved_subject = subject.rstrip(".") + " ✨"

    improved_body = body
    if "{{first_name}}" not in body.lower() and "{first_name}" not in body.lower():
        improved_body = f"Hi {{{{first_name}}}},\n\n{body}"
    if not any(cta in body.lower() for cta in ["visit", "shop now", "click", "grab", "don't miss"]):
        improved_body += "\n\n👉 Visit us today — we'd love to see you!"

    return {"subject": improved_subject, "body": improved_body, "source": "fallback"}


async def generate_content(
    content_type: str,
    prompt: str,
    api_key: str = "",
    shop_name: str = "",
) -> dict:
    """Generate marketing content (social post, promotion, ad copy)."""
    if api_key:
        try:
            full_prompt = f"Shop: {shop_name}\nContent type: {content_type}\nRequest: {prompt}"
            result = await _call_anthropic(full_prompt, [], api_key, system_override=CONTENT_GEN_PROMPT)
            return {"content": result, "source": "anthropic"}
        except Exception as e:
            log.warning("Anthropic API error on content gen: %s", e)

    # Fallback content
    fallbacks = {
        "social": f"🛍️ New arrivals just dropped at {shop_name or 'our shop'}! Come see what's fresh this week.\n\n✨ Tag a friend who'd love this!\n\n#ShopLocal #RetailTherapy #NewArrivals #SmallBusiness #ShopSmall\n\nBest time to post: Tuesday or Thursday, 11am-1pm",
        "promotion": f"🏷️ FLASH SALE at {shop_name or 'our shop'}!\n\n20% off everything this weekend only.\n\nNo code needed — discount applied at checkout.\n\nHurry — sale ends Sunday at close! ⏰",
        "ad": f"Looking for something special? {shop_name or 'We'} have curated the perfect collection just for you.\n\n👉 Visit us today and discover your new favorite finds.\n\n📍 Open 7 days a week",
    }
    return {
        "content": fallbacks.get(content_type, fallbacks["social"]),
        "source": "fallback",
    }


async def _call_anthropic(
    message: str,
    history: list[dict],
    api_key: str,
    shop_context: dict | None = None,
    system_override: str | None = None,
) -> str:
    """Call the Anthropic API using httpx (no SDK dependency needed)."""
    system = system_override or SYSTEM_PROMPT
    if shop_context:
        ctx_parts = []
        if shop_context.get("shop_name"):
            ctx_parts.append(f"Shop: {shop_context['shop_name']}")
        if shop_context.get("revenue_today"):
            ctx_parts.append(f"Today's revenue: ${shop_context['revenue_today']:,.2f}")
        if shop_context.get("total_customers"):
            ctx_parts.append(f"Total customers: {shop_context['total_customers']}")
        if shop_context.get("category"):
            ctx_parts.append(f"Category: {shop_context['category']}")
        if ctx_parts:
            system += "\n\nCurrent shop context:\n" + "\n".join(ctx_parts)

    messages = []
    for h in history[-10:]:  # Last 10 messages for context
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": system,
                "messages": messages,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]
