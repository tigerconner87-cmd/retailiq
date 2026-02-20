"""Forge AI Assistant Service (Sage).

Provides AI-powered chat with streaming, content generation, and email
editing using the Anthropic Python SDK with data-aware fallback responses.
"""

import json
import logging
import time
from datetime import datetime

import anthropic

log = logging.getLogger(__name__)

# Rate limit: 100 requests per user per day
_rate_limits: dict[str, list[float]] = {}
DAILY_LIMIT = 100


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


# ── System Prompt Builder ────────────────────────────────────────────────────

def build_system_prompt(ctx: dict) -> str:
    """Build the dynamic system prompt injected with real shop data."""

    # Top products
    top_products = ctx.get("top_products", [])
    top_5_str = "\n".join(
        f"  {i+1}. {p['name']} ({p.get('category','')}) — ${p['revenue']:,.0f} revenue, {p['units']} units"
        for i, p in enumerate(top_products[:5])
    ) or "  No product data yet"

    # Trending products
    trending_up = ctx.get("trending_up", [])
    trending_up_str = ", ".join(trending_up[:3]) if trending_up else "Not enough data yet"
    trending_down = ctx.get("trending_down", [])
    trending_down_str = ", ".join(trending_down[:3]) if trending_down else "Not enough data yet"

    # Competitors
    competitors = ctx.get("competitors", [])
    comp_details = "\n".join(
        f"  - {c['name']}: {c['rating']}/5 ({c['reviews']} reviews)"
        for c in competitors
    ) or "  No competitors tracked yet"

    # Review sentiment
    neg_reviews = ctx.get("recent_negative_reviews", [])
    own_count = ctx.get("own_review_count", 0)
    if own_count == 0:
        sentiment_str = "No reviews yet"
    elif not neg_reviews:
        sentiment_str = "100% positive (recent)"
    else:
        pos_pct = max(0, 100 - len(neg_reviews) * 20)
        sentiment_str = f"~{pos_pct}% positive (recent)"

    # Goal data
    goal_target = ctx.get("monthly_goal", 0)
    goal_progress = ctx.get("goal_progress", 0)
    goal_pct = round((goal_progress / goal_target * 100) if goal_target else 0, 1)
    now = datetime.now()
    days_in_month = 30
    day_progress = now.day / days_in_month * 100
    on_track = "Yes" if goal_pct >= day_progress * 0.85 else "Needs attention"

    return f"""You are Sage, the AI business advisor inside Forge — a marketing intelligence platform for retail shop owners. You are incredibly smart, warm, and helpful. Think of yourself as the user's brilliant business partner who also happens to know everything.

CORE PERSONALITY:
- You can answer ANY question — business, math, general knowledge, creative writing, anything. You are not limited to business topics.
- When questions ARE about business, you give specific, actionable advice using the shop's real data.
- You're conversational and natural, never robotic or salesy.
- You're honest — if something is going wrong, you say it clearly but constructively.
- You're concise — get to the point, then offer to go deeper if they want.
- When writing content (posts, emails, promotions), make it ready to copy and use immediately.
- Use the shop's actual product names, revenue figures, and competitor data in your responses.
- Format responses with markdown when helpful (bold, lists, headers) but don't over-format casual answers.

SHOP DATA (use this to personalize every response):
Shop Name: {ctx.get("shop_name", "Your Shop")}
Owner: {ctx.get("owner_name", "there")}
Category: {ctx.get("category", "retail")}
Location: {ctx.get("city", "Unknown")}

REVENUE:
- Today: ${ctx.get("revenue_today", 0):,.2f}
- Yesterday: ${ctx.get("revenue_yesterday", 0):,.2f}
- This month: ${ctx.get("revenue_month", 0):,.2f}
- Last month: ${ctx.get("revenue_last_month", 0):,.2f}
- Average daily: ${ctx.get("avg_daily_revenue", 0):,.2f}
- Best day this month: {ctx.get("best_day", "N/A")} (${ctx.get("best_day_revenue", 0):,.2f})
- Worst day this month: {ctx.get("worst_day", "N/A")} (${ctx.get("worst_day_revenue", 0):,.2f})
- Month-over-month change: {ctx.get("mom_change", 0):+.1f}%

PRODUCTS:
- Total products: {ctx.get("product_count", 0)}
- Top sellers:
{top_5_str}
- Trending up: {trending_up_str}
- Trending down: {trending_down_str}
- Average order value: ${ctx.get("aov", 0):,.2f}

CUSTOMERS:
- Total customers: {ctx.get("total_customers", 0)}
- Repeat rate: {ctx.get("repeat_rate", 0):.1f}%
- New this month: {ctx.get("new_customers_month", 0)}
- At-risk (30+ days inactive): {ctx.get("at_risk_customers", 0)}
- Lost (60+ days inactive): {ctx.get("lost_customers", 0)}
- VIP customers (top 10%): {ctx.get("vip_customers", 0)}
- Average customer lifetime value: ${ctx.get("avg_clv", 0):,.2f}

COMPETITORS:
{comp_details}

YOUR REVIEWS:
- Google rating: {ctx.get("own_avg_rating", 0)}/5
- Total reviews: {own_count}
- Recent sentiment: {sentiment_str}

GOALS:
- Monthly revenue target: ${goal_target:,.2f}
- Progress: ${goal_progress:,.2f} ({goal_pct}%)
- On track: {on_track}

CALENDAR CONTEXT:
- Today is: {ctx.get("today_date", now.strftime("%B %d, %Y"))}
- Day of week: {ctx.get("day_of_week", now.strftime("%A"))}
- Strongest day: {ctx.get("strongest_day", "Saturday")}
- Weakest day: {ctx.get("weakest_day", "Monday")}
- Peak hours: {ctx.get("peak_hours", "11am-2pm")}"""


# ── Specialized Prompts ──────────────────────────────────────────────────────

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


# ── Core Chat (non-streaming) ────────────────────────────────────────────────

async def chat(
    user_id: str,
    message: str,
    conversation_history: list[dict] | None = None,
    api_key: str = "",
    shop_context: dict | None = None,
) -> dict:
    """Process a chat message and return AI response."""
    if not _check_rate_limit(user_id):
        return {
            "response": "I've reached my thinking limit for today. I'll be back tomorrow!",
            "source": "rate_limit",
            "remaining": 0,
        }

    remaining = get_remaining_requests(user_id)

    if api_key:
        try:
            result = await _call_anthropic(message, conversation_history or [], api_key, shop_context)
            return {"response": result, "source": "anthropic", "remaining": remaining}
        except anthropic.AuthenticationError:
            return {
                "response": "Sage needs a valid API key to work. Go to **Settings** to update it.",
                "source": "error",
                "remaining": remaining,
            }
        except anthropic.RateLimitError:
            return {
                "response": "I've hit the API rate limit. Try again in a moment.",
                "source": "error",
                "remaining": remaining,
            }
        except anthropic.APIConnectionError:
            return {
                "response": "I'm having trouble connecting right now. Try again in a moment.",
                "source": "error",
                "remaining": remaining,
            }
        except Exception as e:
            log.warning("Anthropic API error: %s — falling back", e)

    # Data-aware fallback
    response = _get_fallback_response(message, shop_context)
    return {"response": response, "source": "fallback", "remaining": remaining}


# ── Streaming Chat ────────────────────────────────────────────────────────────

async def chat_stream(
    user_id: str,
    message: str,
    conversation_history: list[dict] | None = None,
    api_key: str = "",
    shop_context: dict | None = None,
):
    """Yield SSE-formatted chunks for streaming chat responses."""
    if not _check_rate_limit(user_id):
        yield f"data: {json.dumps({'text': '', 'done': True, 'full_text': 'I\\'ve reached my thinking limit for today. I\\'ll be back tomorrow!', 'source': 'rate_limit', 'remaining': 0})}\n\n"
        return

    remaining = get_remaining_requests(user_id)

    if not api_key:
        response = _get_fallback_response(message, shop_context)
        yield f"data: {json.dumps({'text': '', 'done': True, 'full_text': response, 'source': 'fallback', 'remaining': remaining})}\n\n"
        return

    ctx = shop_context or {}
    system = build_system_prompt(ctx)

    messages = []
    for h in (conversation_history or [])[-10:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        full_text = ""
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                full_text += text
                yield f"data: {json.dumps({'text': text, 'done': False})}\n\n"
        yield f"data: {json.dumps({'text': '', 'done': True, 'full_text': full_text, 'source': 'anthropic', 'remaining': remaining})}\n\n"
    except anthropic.AuthenticationError:
        yield f"data: {json.dumps({'text': '', 'done': True, 'full_text': 'Sage needs a valid API key to work. Go to **Settings** to update it.', 'source': 'error', 'remaining': remaining})}\n\n"
    except anthropic.RateLimitError:
        yield f"data: {json.dumps({'text': '', 'done': True, 'full_text': 'I\\'ve hit the API rate limit. Try again in a moment.', 'source': 'error', 'remaining': remaining})}\n\n"
    except anthropic.APIConnectionError:
        yield f"data: {json.dumps({'text': '', 'done': True, 'full_text': 'I\\'m having trouble connecting right now. Try again in a moment.', 'source': 'error', 'remaining': remaining})}\n\n"
    except Exception as e:
        log.warning("Anthropic streaming error: %s", e)
        response = _get_fallback_response(message, shop_context)
        yield f"data: {json.dumps({'text': '', 'done': True, 'full_text': response, 'source': 'fallback', 'remaining': remaining})}\n\n"


# ── Non-streaming API call ────────────────────────────────────────────────────

async def _call_anthropic(
    message: str,
    history: list[dict],
    api_key: str,
    shop_context: dict | None = None,
    system_override: str | None = None,
) -> str:
    """Call the Anthropic API using the official SDK."""
    ctx = shop_context or {}
    system = system_override or build_system_prompt(ctx)

    messages = []
    for h in history[-10:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=system,
        messages=messages,
    )
    return response.content[0].text


# ── Email Rewrite ─────────────────────────────────────────────────────────────

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
            try:
                parsed = json.loads(result)
                return {"subject": parsed["subject"], "body": parsed["body"], "source": "anthropic"}
            except (json.JSONDecodeError, KeyError):
                return {"subject": subject, "body": result, "source": "anthropic"}
        except Exception as e:
            log.warning("Anthropic API error on email rewrite: %s", e)

    # Fallback
    improved_subject = subject
    if not subject.endswith(("!", "?", "...")):
        improved_subject = subject.rstrip(".") + " — Don't miss out!"
    improved_body = body
    if "{{first_name}}" not in body.lower() and "{first_name}" not in body.lower():
        improved_body = f"Hi {{{{first_name}}}},\n\n{body}"
    if not any(cta in body.lower() for cta in ["visit", "shop now", "click", "grab", "don't miss"]):
        improved_body += "\n\nVisit us today — we'd love to see you!"
    return {"subject": improved_subject, "body": improved_body, "source": "fallback"}


# ── Content Generation ────────────────────────────────────────────────────────

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

    fallbacks = {
        "social": f"New arrivals just dropped at {shop_name or 'our shop'}! Come see what's fresh this week.\n\nTag a friend who'd love this!\n\n#ShopLocal #RetailTherapy #NewArrivals #SmallBusiness #ShopSmall\n\nBest time to post: Tuesday or Thursday, 11am-1pm",
        "promotion": f"FLASH SALE at {shop_name or 'our shop'}!\n\n20% off everything this weekend only.\n\nNo code needed — discount applied at checkout.\n\nHurry — sale ends Sunday at close!",
        "ad": f"Looking for something special? {shop_name or 'We'} have curated the perfect collection just for you.\n\nVisit us today and discover your new favorite finds.\n\nOpen 7 days a week",
    }
    return {"content": fallbacks.get(content_type, fallbacks["social"]), "source": "fallback"}


# ── Test Connection ───────────────────────────────────────────────────────────

async def test_connection(api_key: str) -> dict:
    """Test if the Anthropic API key is valid."""
    if not api_key:
        return {"ok": False, "message": "No API key provided"}
    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say 'Connected!' in one word."}],
        )
        return {"ok": True, "message": response.content[0].text.strip()}
    except anthropic.AuthenticationError:
        return {"ok": False, "message": "Invalid API key"}
    except Exception as e:
        return {"ok": False, "message": str(e)[:100]}


# ── Data-Aware Fallback ──────────────────────────────────────────────────────

def _build_data_context_string(ctx: dict) -> str:
    """Build a readable summary of shop data for fallback responses."""
    parts = []
    name = ctx.get("shop_name", "your shop")
    rev_today = ctx.get("revenue_today", 0)
    rev_yesterday = ctx.get("revenue_yesterday", 0)
    rev_month = ctx.get("revenue_month", 0)
    avg_daily = ctx.get("avg_daily_revenue", 0)

    if rev_today > 0:
        parts.append(f"Today's revenue so far: **${rev_today:,.2f}**")
    if rev_yesterday > 0:
        parts.append(f"Yesterday: **${rev_yesterday:,.2f}**")
    if rev_month > 0:
        parts.append(f"This month: **${rev_month:,.2f}** (avg **${avg_daily:,.0f}/day**)")

    total = ctx.get("total_customers", 0)
    vip = ctx.get("vip_customers", 0)
    at_risk = ctx.get("at_risk_customers", 0)
    lost = ctx.get("lost_customers", 0)
    if total > 0:
        parts.append(f"Customers: **{total}** total — {vip} VIP, {at_risk} at-risk, {lost} lost")

    top = ctx.get("top_products", [])
    if top:
        prod_lines = ", ".join(f"**{p['name']}** (${p['revenue']:,.0f})" for p in top[:3])
        parts.append(f"Top sellers (30d): {prod_lines}")

    own_rating = ctx.get("own_avg_rating", 0)
    own_count = ctx.get("own_review_count", 0)
    if own_count > 0:
        parts.append(f"Your rating: **{own_rating}**/5 ({own_count} reviews)")

    comps = ctx.get("competitors", [])
    if comps:
        comp_lines = ", ".join(f"{c['name']} ({c['rating']})" for c in comps[:3])
        parts.append(f"Competitors: {comp_lines}")

    return "\n".join(f"- {p}" for p in parts) if parts else ""


def _get_fallback_response(message: str, shop_context: dict | None = None) -> str:
    """Return a data-aware response when no API key is configured."""
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
        rev_month = ctx.get("revenue_month", 0)
        avg_daily = ctx.get("avg_daily_revenue", 0)
        top = ctx.get("top_products", [])
        mom = ctx.get("mom_change", 0)
        resp = "Here's what I see in your sales data:\n\n"
        if rev_month > 0:
            resp += f"- **This month's revenue:** ${rev_month:,.2f} (avg ${avg_daily:,.0f}/day)\n"
        if mom:
            direction = "up" if mom > 0 else "down"
            resp += f"- **Month-over-month:** {direction} {abs(mom):.1f}%\n"
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
            "Want me to go deeper on any of these? Or connect your Anthropic API key in **Settings** for full AI-powered analysis!"
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
        repeat_rate = ctx.get("repeat_rate", 0)
        resp = "Here's your customer health snapshot:\n\n"
        if total > 0:
            resp += f"- **{total}** total customers\n"
            resp += f"- **{vip}** VIPs (your best customers)\n"
            resp += f"- **{at_risk}** at-risk (haven't visited recently)\n"
            resp += f"- **{lost}** lost (inactive 60+ days)\n"
            if repeat_rate > 0:
                resp += f"- **{repeat_rate:.1f}%** repeat rate\n"
            resp += "\n"
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
            resp += f"You have **{len(neg)} recent low-rated reviews** — responding quickly can improve your rating.\n\n"
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
        "Just ask me anything — I'm here to help!\n\n"
        "*Connect your Anthropic API key in **Settings** for full AI-powered conversations with Sage.*"
    )
    return resp


def _classify_query(message: str) -> str:
    """Simple keyword classifier for fallback responses."""
    msg = message.lower()
    greetings = ["hello", "hi ", "hey", "help", "what can you", "who are you", "start", "introduce", "hi!"]
    if any(g in msg for g in greetings):
        return "greeting"
    if any(w in msg for w in ["sale", "revenue", "profit", "price", "discount", "aov", "transaction",
                               "money", "income", "earnings", "how am i doing", "performance", "numbers"]):
        return "sales"
    if any(w in msg for w in ["market", "social", "post", "instagram", "facebook", "content",
                               "promote", "ad ", "tiktok", "brand", "write me", "create a"]):
        return "marketing"
    if any(w in msg for w in ["customer", "retain", "churn", "loyal", "repeat", "segment",
                               "win back", "winback", "at risk", "lost", "vip"]):
        return "customers"
    if any(w in msg for w in ["competitor", "competition", "rival", "nearby", "vs ",
                               "versus", "other shop", "other store"]):
        return "competitors"
    if any(w in msg for w in ["email", "campaign", "newsletter", "subject line", "open rate"]):
        return "email"
    return "default"
