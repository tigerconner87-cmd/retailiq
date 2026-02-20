"""Autonomous AI Agent Operations API endpoints."""

import logging
import random
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Body, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.dependencies import get_current_user, get_db
from app.models import (
    User, Shop, ShopSettings, Agent, AgentActivity,
    TaskGroup, OrchestratedTask, AgentConfig, AgentOutput, AgentRun,
)
from app.services.orchestrator import TaskOrchestrator
from app.config import settings

import os

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _get_shop(db: Session, user: User) -> Shop:
    return db.query(Shop).filter(Shop.user_id == user.id).first()


def _get_api_key(db: Session, shop: Shop) -> str:
    try:
        s = db.query(ShopSettings).filter(ShopSettings.shop_id == shop.id).first()
        if s and hasattr(s, 'anthropic_api_key') and s.anthropic_api_key:
            return s.anthropic_api_key.strip()
    except Exception:
        pass
    if settings.ANTHROPIC_API_KEY:
        return settings.ANTHROPIC_API_KEY.strip()
    env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return env_key


def _get_shop_context(db: Session, shop: Shop, user: User) -> dict:
    """Re-use the context builder from ai.py."""
    try:
        from app.routers.ai import _get_shop_context as _ai_ctx
        return _ai_ctx(db, shop, user)
    except Exception:
        return {"shop_name": shop.name, "category": getattr(shop, "category", "retail")}


AGENT_COLORS = {
    "maya": "#ec4899", "scout": "#f59e0b", "emma": "#10b981",
    "alex": "#6366f1", "max": "#ef4444",
}

AGENT_NAMES = {
    "maya": "Maya", "scout": "Scout", "emma": "Emma",
    "alex": "Alex", "max": "Max",
}


# ── Orchestrate (multi-agent command) ────────────────────────────────────────

@router.post("/orchestrate")
async def orchestrate_command(
    command: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}
    api_key = _get_api_key(db, shop)
    if not api_key:
        return {"error": "No API key configured"}
    ctx = _get_shop_context(db, shop, user)
    orch = TaskOrchestrator(db, shop, api_key, ctx)
    result = await orch.process_command(command)
    return result


# ── Single agent run ──────────────────────────────────────────────────────────

@router.post("/{agent_type}/run")
async def run_single_agent(
    agent_type: str,
    instructions: str = Body("", embed=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if agent_type not in ("maya", "scout", "emma", "alex", "max"):
        return {"error": "Invalid agent type"}
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}
    api_key = _get_api_key(db, shop)
    if not api_key:
        return {"error": "No API key configured"}
    ctx = _get_shop_context(db, shop, user)
    orch = TaskOrchestrator(db, shop, api_key, ctx)
    result = await orch.execute_single_agent(agent_type, instructions)
    return result


# ── Agent status (with seed on first access) ─────────────────────────────────

@router.get("/status")
def get_agent_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}

    # Seed on first access
    existing = db.query(AgentRun).filter(AgentRun.shop_id == shop.id).first()
    if not existing:
        _seed_agent_operations(db, shop.id)

    agents = db.query(Agent).filter(Agent.shop_id == shop.id).all()
    result = []
    for agent in agents:
        last_run = (
            db.query(AgentRun)
            .filter(AgentRun.shop_id == shop.id, AgentRun.agent_type == agent.agent_type)
            .order_by(desc(AgentRun.created_at))
            .first()
        )
        output_count = (
            db.query(func.count(AgentOutput.id))
            .filter(AgentOutput.shop_id == shop.id, AgentOutput.agent_type == agent.agent_type)
            .scalar()
        )
        runs_30d = (
            db.query(func.count(AgentRun.id))
            .filter(
                AgentRun.shop_id == shop.id,
                AgentRun.agent_type == agent.agent_type,
                AgentRun.created_at >= datetime.utcnow() - timedelta(days=30),
            )
            .scalar()
        )
        avg_rating = (
            db.query(func.avg(AgentOutput.rating))
            .filter(
                AgentOutput.shop_id == shop.id,
                AgentOutput.agent_type == agent.agent_type,
                AgentOutput.rating.isnot(None),
            )
            .scalar()
        )
        result.append({
            "agent_type": agent.agent_type,
            "name": AGENT_NAMES.get(agent.agent_type, agent.agent_type.title()),
            "is_active": agent.is_active,
            "color": AGENT_COLORS.get(agent.agent_type, "#6366f1"),
            "output_count": output_count or 0,
            "runs_30d": runs_30d or 0,
            "avg_rating": round(float(avg_rating), 1) if avg_rating else None,
            "last_run_at": last_run.created_at.isoformat() if last_run else None,
            "last_run_status": last_run.status if last_run else None,
        })

    return {"agents": result}


# ── Agent outputs (paginated) ────────────────────────────────────────────────

@router.get("/{agent_type}/outputs")
def get_agent_outputs(
    agent_type: str,
    output_type: str = Query("", description="Filter by output type"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}
    q = db.query(AgentOutput).filter(AgentOutput.shop_id == shop.id)
    if agent_type != "all":
        q = q.filter(AgentOutput.agent_type == agent_type)
    if output_type:
        q = q.filter(AgentOutput.output_type == output_type)
    total = q.count()
    outputs = q.order_by(desc(AgentOutput.created_at)).offset(offset).limit(limit).all()
    return {
        "outputs": [
            {
                "id": o.id,
                "agent_type": o.agent_type,
                "output_type": o.output_type,
                "title": o.title,
                "content": o.content,
                "metadata": o.metadata_json,
                "rating": o.rating,
                "is_saved": o.is_saved,
                "created_at": o.created_at.isoformat(),
                "agent_color": AGENT_COLORS.get(o.agent_type, "#6366f1"),
            }
            for o in outputs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ── Unified activity feed ────────────────────────────────────────────────────

@router.get("/activity")
def get_activity(
    agent_filter: str = Query("", description="Filter by agent type"),
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}
    q = (
        db.query(AgentActivity, Agent)
        .join(Agent, AgentActivity.agent_id == Agent.id)
        .filter(AgentActivity.shop_id == shop.id)
    )
    if agent_filter:
        q = q.filter(Agent.agent_type == agent_filter)
    activities = q.order_by(desc(AgentActivity.created_at)).limit(limit).all()
    return {
        "activities": [
            {
                "id": a.id,
                "agent_type": ag.agent_type,
                "agent_name": AGENT_NAMES.get(ag.agent_type, ag.agent_type.title()),
                "agent_color": AGENT_COLORS.get(ag.agent_type, "#6366f1"),
                "activity_type": a.action_type,
                "description": a.description,
                "details": a.details,
                "created_at": a.created_at.isoformat(),
            }
            for a, ag in activities
        ],
    }


# ── Orchestrated tasks for task board ─────────────────────────────────────────

@router.get("/tasks")
def get_orchestrated_tasks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}
    groups = (
        db.query(TaskGroup)
        .filter(TaskGroup.shop_id == shop.id)
        .order_by(desc(TaskGroup.created_at))
        .limit(20)
        .all()
    )
    result = []
    for g in groups:
        tasks = db.query(OrchestratedTask).filter(OrchestratedTask.group_id == g.id).all()
        result.append({
            "id": g.id,
            "command": g.command,
            "status": g.status,
            "agent_count": g.agent_count,
            "completed_count": g.completed_count,
            "summary": g.summary,
            "created_at": g.created_at.isoformat(),
            "completed_at": g.completed_at.isoformat() if g.completed_at else None,
            "tasks": [
                {
                    "id": t.id,
                    "agent_type": t.agent_type,
                    "agent_name": {"maya": "Maya", "scout": "Scout", "emma": "Emma", "alex": "Alex", "max": "Max"}.get(t.agent_type, t.agent_type),
                    "agent_color": AGENT_COLORS.get(t.agent_type, "#6366f1"),
                    "instructions": t.instructions,
                    "status": t.status,
                    "result_summary": t.result_summary,
                    "tokens_used": t.tokens_used,
                    "created_at": t.created_at.isoformat(),
                }
                for t in tasks
            ],
        })
    return {"groups": result}


# ── Configure agent ──────────────────────────────────────────────────────────

@router.put("/{agent_type}/configure")
def configure_agent(
    agent_type: str,
    config: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}
    row = (
        db.query(AgentConfig)
        .filter(AgentConfig.shop_id == shop.id, AgentConfig.agent_type == agent_type)
        .first()
    )
    if row:
        row.settings = config
        row.updated_at = datetime.utcnow()
    else:
        row = AgentConfig(
            id=str(uuid.uuid4()),
            shop_id=shop.id,
            agent_type=agent_type,
            settings=config,
        )
        db.add(row)
    db.commit()
    return {"ok": True}


# ── Rate output ──────────────────────────────────────────────────────────────

@router.post("/output/{output_id}/rate")
def rate_output(
    output_id: str,
    rating: int = Body(..., embed=True, ge=1, le=5),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}
    output = (
        db.query(AgentOutput)
        .filter(AgentOutput.id == output_id, AgentOutput.shop_id == shop.id)
        .first()
    )
    if not output:
        return {"error": "Output not found"}
    output.rating = rating
    db.commit()
    return {"ok": True, "rating": rating}


# ── Metrics ──────────────────────────────────────────────────────────────────

@router.get("/metrics")
def get_metrics(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    if not shop:
        return {"error": "No shop found"}

    now = datetime.utcnow()
    thirty_days = now - timedelta(days=30)

    total_runs = (
        db.query(func.count(AgentRun.id))
        .filter(AgentRun.shop_id == shop.id, AgentRun.created_at >= thirty_days)
        .scalar() or 0
    )
    total_outputs = (
        db.query(func.count(AgentOutput.id))
        .filter(AgentOutput.shop_id == shop.id, AgentOutput.created_at >= thirty_days)
        .scalar() or 0
    )
    total_tokens = (
        db.query(func.sum(AgentRun.tokens_used))
        .filter(AgentRun.shop_id == shop.id, AgentRun.created_at >= thirty_days)
        .scalar() or 0
    )
    avg_rating = (
        db.query(func.avg(AgentOutput.rating))
        .filter(AgentOutput.shop_id == shop.id, AgentOutput.rating.isnot(None))
        .scalar()
    )
    total_groups = (
        db.query(func.count(TaskGroup.id))
        .filter(TaskGroup.shop_id == shop.id, TaskGroup.created_at >= thirty_days)
        .scalar() or 0
    )

    # Per-agent breakdown
    agents_breakdown = []
    for atype in ("maya", "scout", "emma", "alex", "max"):
        runs = (
            db.query(func.count(AgentRun.id))
            .filter(AgentRun.shop_id == shop.id, AgentRun.agent_type == atype, AgentRun.created_at >= thirty_days)
            .scalar() or 0
        )
        outputs = (
            db.query(func.count(AgentOutput.id))
            .filter(AgentOutput.shop_id == shop.id, AgentOutput.agent_type == atype, AgentOutput.created_at >= thirty_days)
            .scalar() or 0
        )
        agents_breakdown.append({
            "agent_type": atype,
            "runs": runs,
            "outputs": outputs,
            "color": AGENT_COLORS.get(atype, "#6366f1"),
        })

    # Estimated cost (haiku pricing ~$0.25/1M input + $1.25/1M output, rough)
    est_cost = round(total_tokens * 0.0000008, 2)
    # Estimated hours saved (each output ~15 min of human work)
    hours_saved = round(total_outputs * 0.25, 1)
    # Estimated revenue impact (rough: $50 per marketing output, $100 per strategy)
    est_value = total_outputs * 65

    return {
        "total_runs": total_runs,
        "total_outputs": total_outputs,
        "total_tokens": total_tokens,
        "total_commands": total_groups,
        "avg_rating": round(float(avg_rating), 1) if avg_rating else None,
        "estimated_cost": est_cost,
        "hours_saved": hours_saved,
        "estimated_value": est_value,
        "agents": agents_breakdown,
    }


# ── Mock Data Seeding ────────────────────────────────────────────────────────

def _seed_agent_operations(db: Session, shop_id: str):
    """Seed realistic agent operation data on first access."""
    log.info("Seeding agent operations data for shop %s", shop_id)
    now = datetime.utcnow()

    agents = db.query(Agent).filter(Agent.shop_id == shop_id).all()
    agent_map = {a.agent_type: a for a in agents}
    if not agent_map:
        return

    # Create AgentConfig records
    for atype in ("maya", "scout", "emma", "alex", "max"):
        db.add(AgentConfig(
            id=str(uuid.uuid4()),
            shop_id=shop_id,
            agent_type=atype,
            is_enabled=True,
            settings={},
        ))

    # Seed AgentRuns (30 runs over 30 days)
    run_map = {}  # agent_type -> list of run ids
    for atype in ("maya", "scout", "emma", "alex", "max"):
        run_map[atype] = []
        for i in range(6):
            days_ago = random.randint(0, 29)
            rid = str(uuid.uuid4())
            run = AgentRun(
                id=rid,
                shop_id=shop_id,
                agent_type=atype,
                trigger=random.choice(["manual", "command", "scheduled"]),
                status="completed",
                output_count=random.randint(2, 6),
                tokens_used=random.randint(800, 3500),
                duration_ms=random.randint(2000, 8000),
                created_at=now - timedelta(days=days_ago, hours=random.randint(0, 12)),
                completed_at=now - timedelta(days=days_ago, hours=random.randint(0, 12)) + timedelta(seconds=random.randint(3, 15)),
            )
            db.add(run)
            run_map[atype].append(rid)

    # Seed AgentOutputs
    maya_outputs = [
        ("instagram_post", "Weekend Sale Vibes", "Weekend flash sale! 20% off all accessories today and tomorrow. Don't miss out! #ShopLocal #WeekendDeals #RetailTherapy"),
        ("instagram_post", "New Arrivals Alert", "Fresh drops just hit the shelves! Come see what's new this week. Link in bio for sneak peeks. #NewArrivals #ShopSmall"),
        ("instagram_post", "Behind the Scenes", "Ever wonder how we curate our collection? Here's a peek behind the curtain at our buying process. #BTS #SmallBusiness"),
        ("facebook_post", "Customer Appreciation Day", "To all our amazing customers - YOU make this possible. Join us this Saturday for Customer Appreciation Day with exclusive deals and refreshments!"),
        ("facebook_post", "Product Spotlight", "Product Spotlight: Our bestselling premium collection is back in stock! Limited quantities available. Shop early for the best selection."),
        ("email_campaign", "We Miss You!", "Subject: We miss you! Here's 15% off to welcome you back\n\nHi [Name],\n\nIt's been a while since your last visit, and we've got some exciting new products we think you'll love. Use code WELCOME15 for 15% off your next purchase.\n\nSee you soon!"),
        ("email_campaign", "VIP Early Access", "Subject: VIP Early Access - New Collection Drops Tomorrow\n\nAs one of our valued VIP customers, you get first dibs on our new collection before anyone else. Shop now and enjoy free shipping on orders over $50."),
        ("promo_idea", "Bundle & Save Campaign", "Create a 'Bundle & Save' promotion: Buy any 2 items from our top sellers, get 25% off the second item. Run for 2 weeks with social media countdown."),
        ("promo_idea", "Loyalty Points Double Day", "Double loyalty points every Wednesday for the next month. Promotes mid-week traffic and rewards repeat customers."),
        ("content_calendar", "Weekly Content Plan", "Mon: Product feature post\nTue: Customer testimonial\nWed: Behind-the-scenes story\nThu: Industry tip/advice\nFri: Weekend sale teaser\nSat: User-generated content\nSun: Inspiration/lifestyle"),
    ]
    scout_outputs = [
        ("opportunity", "Underserved Afternoon Market", "Analysis shows competitors close by 6 PM on weekdays. Extending hours to 8 PM could capture the after-work shopping segment, estimated +$2,400/month."),
        ("opportunity", "Gift Bundle Gap", "No local competitor offers curated gift bundles. Creating pre-packaged gift sets at $30-$75 price points could capture the corporate gifting market."),
        ("threat", "New Competitor Opening Nearby", "A similar retail store is opening 2 blocks away next month. They're advertising 'Grand Opening' discounts of 30%. Recommend preemptive loyalty campaign."),
        ("threat", "Online Price Undercutting", "3 of your top products are listed 15-20% cheaper on Amazon. Consider adding value through bundling and in-store experience rather than price matching."),
        ("competitive_response", "Counter-Strategy for Holiday Season", "Competitor X is running a 'Buy 3 Get 1 Free' holiday promotion. Counter with a 'Holiday Gift Guide' experience package: personal shopping + gift wrapping + delivery for purchases over $100."),
        ("market_report", "Monthly Competitive Landscape", "Market position: Strong in quality/service, weaker on price. Key differentiators: in-store experience, product curation, customer relationships. Biggest risk: online alternatives."),
    ]
    emma_outputs = [
        ("winback_email", "Win-Back: Sarah Johnson", "Hi Sarah,\n\nWe noticed it's been a while since your last visit and we miss you! As a valued customer, here's an exclusive 15% off coupon just for you.\n\nUse code MISSYOU15 at checkout. Valid for 14 days.\n\nWe've got exciting new arrivals we think you'll love!"),
        ("winback_email", "Win-Back: Mike Chen", "Hey Mike,\n\nRemember how much you loved our premium collection? We just restocked with new styles and wanted you to be the first to know.\n\nHere's 15% off to welcome you back: COMEBACK15\n\nHope to see you soon!"),
        ("winback_email", "Win-Back: Lisa Park", "Dear Lisa,\n\nWe've missed seeing you at the shop! To show our appreciation for your past loyalty, enjoy 15% off your next purchase with code RETURN15.\n\nPlus, we've made some exciting changes to the store we think you'll love."),
        ("review_response", "Response to 3-Star Review", "Thank you for your feedback! We're sorry your experience didn't meet our usual standards. We'd love the chance to make it right — please reach out to us directly and we'll ensure your next visit is exceptional."),
        ("review_response", "Response to 5-Star Review", "Thank you so much for the wonderful review! We're thrilled you had such a great experience. Our team works hard to make every visit special, and reviews like yours keep us motivated!"),
        ("vip_program", "VIP Tier Proposal", "Propose a 3-tier VIP program:\n- Silver ($500+/year): 5% off + birthday reward\n- Gold ($1,000+/year): 10% off + early access + free alterations\n- Platinum ($2,500+/year): 15% off + personal shopper + exclusive events"),
        ("customer_insight", "At-Risk Customer Segment Analysis", "14 customers haven't purchased in 45+ days. Average CLV of this group: $340. Recommended action: personalized win-back campaign could recover ~$4,760 in annual revenue."),
    ]
    alex_outputs = [
        ("daily_briefing", "Tuesday Business Briefing", "Revenue is tracking 8% ahead of last month's pace. Top performer today: Premium Collection (+23% vs avg). Customer traffic up 12% week-over-week. Key risk: inventory running low on 3 bestsellers."),
        ("daily_briefing", "Monday Morning Briefing", "Weekend revenue: $3,240 (above $2,800 target). Saturday was the strongest day with 34 transactions. VIP customers drove 45% of weekend revenue. Action needed: restock top 5 products."),
        ("strategy", "Q1 Growth Strategy", "Focus on three pillars:\n1. Customer Retention: Launch VIP program (projected +15% repeat rate)\n2. Average Order Value: Introduce bundles and upsells (target AOV +$12)\n3. Traffic: Extend hours + social media push (target +20% foot traffic)"),
        ("strategy", "Competitive Positioning", "Position as the premium local alternative. Key messaging: 'Curated quality, personal service, community connection.' Avoid price wars — compete on experience and expertise."),
        ("action_plan", "This Week's Priority Actions", "1. HIGH: Restock top 3 bestsellers before weekend\n2. HIGH: Launch win-back email to 14 at-risk customers\n3. MEDIUM: Post 3x on Instagram this week\n4. MEDIUM: Review and respond to 4 pending reviews\n5. LOW: Update window display for new season"),
        ("forecast", "30-Day Revenue Forecast", "Based on current trends and seasonality:\n- Week 1: $4,200 (current trajectory)\n- Week 2: $4,500 (weekend event boost)\n- Week 3: $3,800 (mid-month typical dip)\n- Week 4: $4,800 (end-of-month push)\nProjected monthly total: $17,300 (vs $16,000 goal)"),
    ]
    max_outputs = [
        ("bundle", "Weekend Essentials Bundle", "Bundle: Any top + accessory = 20% off the accessory.\nEstimated uplift: +$8 per transaction, projected +$640/month based on current traffic."),
        ("bundle", "Gift Set Bundle", "Premium Gift Set: 3 bestselling items in gift packaging for $89 (individual value: $112).\nMargin maintained at 42%. Perfect for corporate gifts and holidays."),
        ("pricing_recommendation", "Price Adjustment: Slow Movers", "5 products haven't sold in 3 weeks. Recommend:\n- Product A: $45 → $38 (15% reduction)\n- Product B: $32 → $27 (16% reduction)\nExpected to clear $1,200 in stale inventory within 2 weeks."),
        ("pricing_recommendation", "Premium Line Price Increase", "Top 3 premium items consistently sell out. Data supports a 10% price increase:\n- Current margin: 52%\n- Projected margin after increase: 57%\n- Estimated impact: +$890/month revenue with <5% volume decrease."),
        ("upsell_strategy", "Checkout Upsell Playbook", "At checkout, suggest complementary items:\n- If buying apparel → suggest matching accessory (avg uplift: $18)\n- If buying gifts → suggest gift wrapping + card ($5 add-on, 40% attach rate)\n- Orders $40-50 → 'Add $X to get free shipping' nudge"),
        ("sales_insight", "Weekly Sales Performance", "Best day: Saturday ($1,420 revenue, 28 transactions)\nWorst day: Tuesday ($380, 8 transactions)\nAOV trending up: $52 this week vs $47 last week\nTop seller: Premium Collection A (14 units)\nRecommendation: Tuesday flash sale to boost weakest day"),
    ]

    all_outputs = [
        ("maya", maya_outputs),
        ("scout", scout_outputs),
        ("emma", emma_outputs),
        ("alex", alex_outputs),
        ("max", max_outputs),
    ]

    for atype, outputs in all_outputs:
        runs = run_map.get(atype, [])
        for i, (otype, title, content) in enumerate(outputs):
            rid = runs[i % len(runs)] if runs else None
            days_ago = random.randint(0, 29)
            rating = random.choice([None, None, 4, 5, 5, 4, 3, 5]) if random.random() > 0.4 else None
            db.add(AgentOutput(
                id=str(uuid.uuid4()),
                shop_id=shop_id,
                agent_type=atype,
                run_id=rid,
                output_type=otype,
                title=title,
                content=content,
                metadata_json={},
                rating=rating,
                created_at=now - timedelta(days=days_ago, hours=random.randint(0, 23)),
            ))

    # Seed TaskGroups with OrchestratedTasks
    commands = [
        ("Prepare a full marketing push for this weekend's sale", [
            ("maya", "Create 3 social media posts promoting a weekend sale with 20% off"),
            ("emma", "Draft win-back emails to at-risk customers with the weekend sale offer"),
            ("max", "Suggest 2 product bundles to feature in the weekend sale"),
        ]),
        ("Give me a complete business briefing with action items", [
            ("alex", "Create a comprehensive business briefing with key metrics and trends"),
            ("scout", "Provide competitive intelligence update and any new threats or opportunities"),
            ("max", "Analyze current pricing and suggest any optimizations"),
        ]),
        ("Run a customer retention campaign", [
            ("emma", "Identify at-risk customers and draft personalized win-back emails"),
            ("maya", "Create social media content focused on customer appreciation"),
            ("alex", "Analyze customer retention metrics and suggest strategic improvements"),
        ]),
        ("Analyze competitors and adjust strategy", [
            ("scout", "Comprehensive competitive analysis with opportunities and threats"),
            ("alex", "Review current strategy against competitive landscape and recommend adjustments"),
        ]),
        ("Optimize our product lineup and pricing", [
            ("max", "Review all product pricing and suggest adjustments for slow movers and top sellers"),
            ("alex", "Analyze product performance data and recommend lineup changes"),
            ("maya", "Create content highlighting our best-performing and newly priced products"),
        ]),
    ]

    for ci, (cmd, tasks) in enumerate(commands):
        gid = str(uuid.uuid4())
        days_ago = ci * 5 + random.randint(0, 3)
        g = TaskGroup(
            id=gid,
            shop_id=shop_id,
            command=cmd,
            status="completed",
            agent_count=len(tasks),
            completed_count=len(tasks),
            summary=f"Team completed {len(tasks)} tasks successfully.",
            created_at=now - timedelta(days=days_ago),
            completed_at=now - timedelta(days=days_ago) + timedelta(seconds=random.randint(10, 30)),
        )
        db.add(g)
        for atype, instructions in tasks:
            db.add(OrchestratedTask(
                id=str(uuid.uuid4()),
                group_id=gid,
                shop_id=shop_id,
                agent_type=atype,
                instructions=instructions,
                status="completed",
                result_summary="Completed successfully.",
                tokens_used=random.randint(1000, 3000),
                created_at=now - timedelta(days=days_ago),
                started_at=now - timedelta(days=days_ago) + timedelta(seconds=1),
                completed_at=now - timedelta(days=days_ago) + timedelta(seconds=random.randint(5, 20)),
            ))

    db.commit()
    log.info("Agent operations data seeded for shop %s", shop_id)
