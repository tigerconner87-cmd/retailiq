"""Forge AI Assistant Service (Sage).

Provides AI-powered chat, content generation, and email editing
using the Anthropic API with smart data-aware fallback responses.
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


SYSTEM_PROMPT = """You are Sage, the AI assistant built into Forge — a sales intelligence platform for retail shop owners.

You are knowledgeable, friendly, and practical. You speak like a smart friend who happens to be an expert in retail business, marketing, and customer engagement. You're not a generic chatbot — you have access to the shop's actual data and use it to give specific, actionable advice.

Your personality:
- Warm but efficient — respect the owner's time
- Data-driven — reference real numbers whenever possible
- Encouraging — celebrate wins, frame challenges as opportunities
- Practical — suggest actions that a small shop owner can actually do today
- Natural — don't sound robotic. Use contractions, conversational language
- Concise — aim for 100-200 words unless the user asks for detail

You can help with ANYTHING, but you specialize in:
- Sales analysis, pricing strategy, and revenue growth
- Customer retention, segmentation, and win-back strategies
- Marketing copy: social posts, emails, promotions, ad copy
- Competitor analysis and market positioning
- Product merchandising and inventory decisions
- Local SEO and Google review management
- Goal setting and business planning

When you have shop data in your context, USE IT. Reference their actual revenue, top products, customer counts, competitor ratings. Don't give generic advice when you have specific numbers.

Format responses with markdown: **bold** for emphasis, bullet lists for multiple items, and numbered lists for steps. Keep it scannable."""

EMAIL_REWRITE_PROMPT = """You are Sage, Forge's expert email copywriter for retail businesses.

Rewrite the following email to be more engaging, personal, and likely to drive action.
Keep the same core message but improve:
- Subject line (make it compelling, under 60 chars)
- Opening hook
- Call to action
- Overall tone (warm, personal, urgent but not pushy)
- Keep it concise — under 200 words for the body

Return your response in this exact JSON format:
{"subject": "new subject line", "body": "new email body text"}"""

CONTENT_GEN_PROMPT = """You are Sage, Forge's expert content creator for retail businesses.

Generate marketing content based on the user's request. Be creative, on-brand, and action-oriented.
Include relevant emojis. Keep copy punchy and engaging.

For social posts: include caption, hashtags, and best posting time.
For promotions: include headline, description, terms, and urgency element.
For ad copy: include headline, body, and call-to-action."""


# ── Data-aware fallback responses ─────────────────────────────────────────────

def _build_data_context_string(ctx: dict) -> str:
    """Build a readable summary of shop data for fallback responses."""
    parts = []
    name = ctx.get("shop_name", "your shop")

    # Revenue
    rev_today = ctx.get("revenue_today", 0)
    rev_yesterday = ctx.get("revenue_yesterday", 0)
    rev_30d = ctx.get("revenue_30d", 0)
    avg_daily = ctx.get("avg_daily_revenue", 0)

    if rev_today > 0:
        parts.append(f"Today's revenue so far: **${rev_today:,.2f}**")
    if rev_yesterday > 0:
        parts.append(f"Yesterday: **${rev_yesterday:,.2f}**")
    if rev_30d > 0:
        parts.append(f"Last 30 days: **${rev_30d:,.2f}** (avg **${avg_daily:,.0f}/day**)")

    # Customers
    total = ctx.get("total_customers", 0)
    vip = ctx.get("vip_customers", 0)
    at_risk = ctx.get("at_risk_customers", 0)
    lost = ctx.get("lost_customers", 0)
    if total > 0:
        parts.append(f"Customers: **{total}** total — {vip} VIP, {at_risk} at-risk, {lost} lost")

    # Top products
    top = ctx.get("top_products", [])
    if top:
        prod_lines = ", ".join(f"**{p['name']}** (${p['revenue']:,.0f})" for p in top[:3])
        parts.append(f"Top sellers (30d): {prod_lines}")

    # Reviews
    own_rating = ctx.get("own_avg_rating", 0)
    own_count = ctx.get("own_review_count", 0)
    if own_count > 0:
        parts.append(f"Your rating: **{own_rating}**/5 ({own_count} reviews)")

    # Competitors
    comps = ctx.get("competitors", [])
    if comps:
        comp_lines = ", ".join(f"{c['name']} ({c['rating']})" for c in comps[:3])
        parts.append(f"Competitors: {comp_lines}")

    return "\n".join(f"- {p}" for p in parts) if parts else ""


def _get_fallback_response(message: str, shop_context: dict | None = None) -> str:
    """Return a data-aware response based on message and available shop data."""
    category = _classify_query(message)
    ctx = shop_context or {}
    name = ctx.get("shop_name", "your shop")
    data_summary = _build_data_context_string(ctx)

    if category == "greeting":
        resp = (
            f"Hey there! I'm **Sage**, your AI assistant here on Forge. "
            f"I'm here to help you grow {name}.\n\n"
        )
        if data_summary:
            resp += f"Here's a quick snapshot of where things stand:\n\n{data_summary}\n\n"
        resp += "What would you like to dig into? I can help with sales, marketing, customers, competitors, or anything else."
        return resp

    if category == "sales":
        rev_30d = ctx.get("revenue_30d", 0)
        avg_daily = ctx.get("avg_daily_revenue", 0)
        top = ctx.get("top_products", [])

        resp = "Here's what I see in your sales data:\n\n"
        if rev_30d > 0:
            resp += f"- **30-day revenue:** ${rev_30d:,.2f} (avg ${avg_daily:,.0f}/day)\n"
        if top:
            resp += f"- **Top seller:** {top[0]['name']} with ${top[0]['revenue']:,.0f} in revenue\n"
            if len(top) >= 3:
                resp += f"- Your top 3 drive most of your revenue — consider bundling #{2} ({top[1]['name']}) with #{3} ({top[2]['name']}) for a combo deal\n"
        resp += (
            "\n**Quick wins to boost sales:**\n"
            "1. **Bundle slow movers** with bestsellers — lifts AOV 15-25%\n"
            "2. **Create urgency** — 'Only 3 left!' drives 40% more conversions\n"
            "3. **Upsell at checkout** — suggest complementary items\n"
            "4. **Track peak hours** — schedule top staff during high-traffic times\n\n"
            "Check your **Sales** and **Overview** tabs for detailed trends!"
        )
        return resp

    if category == "marketing":
        resp = "Here are some marketing moves you can make right now:\n\n"
        top = ctx.get("top_products", [])
        if top:
            resp += f"Your bestseller **{top[0]['name']}** is perfect for a spotlight post. Here's a quick draft:\n\n"
            resp += f"> Our {top[0]['name']} is a customer favorite — and it's easy to see why. Come grab yours before they're gone!\n\n"
        resp += (
            "**Marketing quick wins:**\n"
            "1. **Post 3-4x/week** on Instagram and Facebook\n"
            "2. **Use customer photos** — UGC gets 4x more engagement\n"
            "3. **Email weekly** — even a simple 'New This Week' drives traffic\n"
            "4. **Run flash sales** — 24-hour sales create FOMO\n"
            "5. **Cross-promote** with nearby businesses\n\n"
            "Head to your **Marketing** tab for AI-generated content ready to post!"
        )
        return resp

    if category == "customers":
        total = ctx.get("total_customers", 0)
        at_risk = ctx.get("at_risk_customers", 0)
        lost = ctx.get("lost_customers", 0)
        vip = ctx.get("vip_customers", 0)

        resp = "Here's your customer health snapshot:\n\n"
        if total > 0:
            resp += f"- **{total}** total customers\n"
            resp += f"- **{vip}** VIPs (your best customers)\n"
            resp += f"- **{at_risk}** at-risk (haven't visited recently)\n"
            resp += f"- **{lost}** lost (inactive 60+ days)\n\n"
        if at_risk > 0:
            resp += f"Those **{at_risk} at-risk customers** are your biggest opportunity. A simple 15% off 'We miss you' email can win back 10-20% of them.\n\n"
        resp += (
            "**Retention strategies:**\n"
            "1. **Win back at-risk customers** — personal 'We miss you' emails\n"
            "2. **Reward VIPs** — early access, exclusive deals\n"
            "3. **Collect emails at checkout** — your email list is gold\n"
            "4. **Follow up post-purchase** — boosts repeat visits 30%\n\n"
            "Check the **Win-Back** tab for ready-to-send campaigns!"
        )
        return resp

    if category == "competitors":
        comps = ctx.get("competitors", [])
        own_rating = ctx.get("own_avg_rating", 0)

        resp = "Here's your competitive landscape:\n\n"
        if own_rating > 0:
            resp += f"Your rating: **{own_rating}/5**\n"
        if comps:
            for c in comps[:5]:
                indicator = "ahead" if own_rating > c["rating"] else "behind" if own_rating < c["rating"] else "tied"
                resp += f"- **{c['name']}**: {c['rating']}/5 ({c['reviews']} reviews) — you're {indicator}\n"
            resp += "\n"
        neg = ctx.get("recent_negative_reviews", [])
        if neg:
            resp += f"You have **{len(neg)} recent low-rated reviews** — responding to these quickly can improve your rating.\n\n"
        resp += (
            "**Competitive moves:**\n"
            "1. **Monitor their reviews** — negative reviews reveal your opportunities\n"
            "2. **Differentiate on service** — small shops win with personal touch\n"
            "3. **Respond to every review** — shows you care\n"
            "4. **Study what they lack** — fill the gaps they leave\n\n"
            "Your **Competitors** tab has full intelligence on nearby businesses!"
        )
        return resp

    if category == "email":
        resp = (
            "Here are some email best practices for retail:\n\n"
            "**Subject line tips:**\n"
            "- Keep it under 50 characters\n"
            "- Create curiosity or urgency\n"
            "- Use numbers: '5 new arrivals you'll love'\n\n"
            "**Body tips:**\n"
            "- Personalize with the customer's name\n"
            "- One clear call-to-action\n"
            "- Include a time-limited offer\n"
            "- Send Tuesday-Thursday, 10am-2pm\n\n"
            "Use the **Email Campaigns** tab in Marketing for ready-to-send templates, "
            "or ask me to write one for you right here!"
        )
        return resp

    # Default
    resp = ""
    if data_summary:
        resp = f"Here's a quick look at {name}:\n\n{data_summary}\n\n"
    resp += (
        "I can help with a lot of things! Here are some popular topics:\n\n"
        "- **\"How can I boost sales?\"** — data-driven revenue tips\n"
        "- **\"Write a social post\"** — instant marketing content\n"
        "- **\"How are my competitors doing?\"** — competitive analysis\n"
        "- **\"Help me win back customers\"** — retention strategies\n"
        "- **\"What should I focus on this week?\"** — prioritized action items\n\n"
        "Just ask me anything — I'm here to help!"
    )
    return resp


def _classify_query(message: str) -> str:
    """Simple keyword classifier for fallback responses."""
    msg = message.lower()
    greetings = ["hello", "hi", "hey", "help", "what can you", "who are you", "start", "introduce"]
    if any(g in msg for g in greetings):
        return "greeting"
    if any(w in msg for w in ["sale", "revenue", "profit", "price", "discount", "aov", "transaction", "money", "income", "earnings"]):
        return "sales"
    if any(w in msg for w in ["market", "social", "post", "instagram", "facebook", "content", "promote", "ad ", "tiktok", "brand"]):
        return "marketing"
    if any(w in msg for w in ["customer", "retain", "churn", "loyal", "repeat", "segment", "win back", "winback", "at risk", "lost"]):
        return "customers"
    if any(w in msg for w in ["competitor", "competition", "rival", "nearby", "vs ", "versus", "other shop", "other store"]):
        return "competitors"
    if any(w in msg for w in ["email", "campaign", "newsletter", "subject line", "open rate"]):
        return "email"
    return "default"


async def chat(
    user_id: str,
    message: str,
    conversation_history: list[dict] | None = None,
    api_key: str = "",
    shop_context: dict | None = None,
) -> dict:
    """
    Process a chat message and return AI response.

    Uses Anthropic API if key is available, otherwise returns data-aware fallback.
    """
    if not _check_rate_limit(user_id):
        return {
            "response": "You've reached the daily limit of 50 Sage requests. Your limit resets in 24 hours.",
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

    # Data-aware fallback response
    response = _get_fallback_response(message, shop_context)
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
        improved_body += "\n\nVisit us today — we'd love to see you!"

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
        "social": f"New arrivals just dropped at {shop_name or 'our shop'}! Come see what's fresh this week.\n\nTag a friend who'd love this!\n\n#ShopLocal #RetailTherapy #NewArrivals #SmallBusiness #ShopSmall\n\nBest time to post: Tuesday or Thursday, 11am-1pm",
        "promotion": f"FLASH SALE at {shop_name or 'our shop'}!\n\n20% off everything this weekend only.\n\nNo code needed — discount applied at checkout.\n\nHurry — sale ends Sunday at close!",
        "ad": f"Looking for something special? {shop_name or 'We'} have curated the perfect collection just for you.\n\nVisit us today and discover your new favorite finds.\n\nOpen 7 days a week",
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
    if shop_context and not system_override:
        ctx_parts = []
        name = shop_context.get("shop_name", "")
        if name:
            ctx_parts.append(f"Shop name: {name}")
        cat = shop_context.get("category", "")
        if cat:
            ctx_parts.append(f"Category: {cat}")
        city = shop_context.get("city", "")
        if city:
            ctx_parts.append(f"Location: {city}")

        rev_today = shop_context.get("revenue_today", 0)
        if rev_today:
            ctx_parts.append(f"Today's revenue: ${rev_today:,.2f}")
        rev_yesterday = shop_context.get("revenue_yesterday", 0)
        if rev_yesterday:
            ctx_parts.append(f"Yesterday's revenue: ${rev_yesterday:,.2f}")
        rev_30d = shop_context.get("revenue_30d", 0)
        if rev_30d:
            ctx_parts.append(f"30-day revenue: ${rev_30d:,.2f}")
        avg_daily = shop_context.get("avg_daily_revenue", 0)
        if avg_daily:
            ctx_parts.append(f"Average daily revenue: ${avg_daily:,.2f}")
        txn_30d = shop_context.get("transactions_30d", 0)
        if txn_30d:
            ctx_parts.append(f"30-day transactions: {txn_30d}")

        total = shop_context.get("total_customers", 0)
        if total:
            ctx_parts.append(f"Total customers: {total}")
            vip = shop_context.get("vip_customers", 0)
            at_risk = shop_context.get("at_risk_customers", 0)
            lost = shop_context.get("lost_customers", 0)
            ctx_parts.append(f"Customer segments: {vip} VIP, {at_risk} at-risk, {lost} lost")

        top = shop_context.get("top_products", [])
        if top:
            prod_lines = [f"  {i+1}. {p['name']} ({p['category']}) — ${p['revenue']:,.0f} revenue, {p['units']} units" for i, p in enumerate(top)]
            ctx_parts.append("Top products (30d):\n" + "\n".join(prod_lines))

        comps = shop_context.get("competitors", [])
        if comps:
            comp_lines = [f"  - {c['name']}: {c['rating']}/5 ({c['reviews']} reviews)" for c in comps]
            ctx_parts.append("Competitors:\n" + "\n".join(comp_lines))

        own_rating = shop_context.get("own_avg_rating", 0)
        own_count = shop_context.get("own_review_count", 0)
        if own_count:
            ctx_parts.append(f"Your Google rating: {own_rating}/5 ({own_count} reviews)")

        neg = shop_context.get("recent_negative_reviews", [])
        if neg:
            neg_lines = [f"  - {r['rating']}/5: \"{r['text']}\"" for r in neg]
            ctx_parts.append("Recent low-rated reviews:\n" + "\n".join(neg_lines))

        if ctx_parts:
            system += "\n\n--- CURRENT SHOP DATA ---\n" + "\n".join(ctx_parts)

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
