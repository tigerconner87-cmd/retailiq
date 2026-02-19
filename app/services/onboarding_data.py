"""Set up new user accounts after onboarding — competitors, goals, settings, alerts."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    new_id, Shop, ShopSettings, Competitor,
    Alert, Goal, RevenueGoal, StrategyNote,
)

# Revenue ranges for setting goal defaults
REVENUE_RANGES = {
    "under_10k": (5000, 10000),
    "10k_25k": (10000, 25000),
    "25k_50k": (25000, 50000),
    "50k_100k": (50000, 100000),
    "100k_plus": (100000, 150000),
}


def generate_onboarding_setup(
    db: Session,
    shop: Shop,
    monthly_revenue: str = "10k_25k",
    revenue_target: float = 25000,
    competitor_names: list[str] = None,
    biggest_challenges: list[str] = None,
):
    """Create essential account setup for a new shop (no mock data).

    Creates: shop settings, competitors (placeholder), goals, strategy note,
    and welcome alerts. Does NOT create products, customers, transactions,
    snapshots, or reviews — those come from the user's POS integration.
    """
    nid = lambda: str(__import__("uuid").uuid4())
    today = datetime.utcnow().date()

    rev_low, rev_high = REVENUE_RANGES.get(monthly_revenue, (10000, 25000))
    target_monthly_revenue = (rev_low + rev_high) / 2

    # --- Shop Settings ---
    settings = ShopSettings(
        id=nid(), shop_id=shop.id,
        monthly_rent=Decimal("2500"),
        avg_cogs_percentage=40.0,
        staff_hourly_rate=Decimal("16.50"),
        tax_rate=8.25,
    )
    db.add(settings)

    # --- Competitors (placeholder — no reviews yet) ---
    comp_names = [n.strip() for n in (competitor_names or []) if n.strip()]
    for comp_name in comp_names[:5]:
        comp = Competitor(
            id=nid(), shop_id=shop.id, name=comp_name,
            rating=None, review_count=0,
            category=shop.category,
        )
        db.add(comp)

    # --- Goals ---
    current_month = today.strftime("%Y-%m")
    now_q = f"{today.year}-Q{(today.month - 1) // 3 + 1}"

    # Revenue goal
    g = Goal(
        id=nid(), shop_id=shop.id, goal_type="revenue",
        title="Monthly Revenue Target", target_value=Decimal(str(revenue_target)),
        unit="$", period="monthly", period_key=current_month, status="active",
    )
    db.add(g)

    # Transaction goal
    avg_txn_estimate = target_monthly_revenue / 200  # rough estimate
    txn_target = max(50, int(revenue_target / max(1, avg_txn_estimate)))
    g2 = Goal(
        id=nid(), shop_id=shop.id, goal_type="transactions",
        title="Monthly Transactions", target_value=Decimal(str(txn_target)),
        unit="#", period="monthly", period_key=current_month, status="active",
    )
    db.add(g2)

    # Revenue goal entry
    rg = RevenueGoal(
        id=nid(), shop_id=shop.id, month=current_month,
        target_amount=Decimal(str(revenue_target)),
    )
    db.add(rg)

    # Strategy note
    challenges_text = ", ".join(biggest_challenges) if biggest_challenges else "growth"
    sn = StrategyNote(
        id=nid(), shop_id=shop.id, quarter=now_q,
        title=f"Q{(today.month - 1) // 3 + 1} {today.year} Growth Strategy",
        objectives=["Increase monthly revenue", "Improve customer retention", "Expand marketing reach"],
        key_results=["Hit revenue target", "Boost repeat rate to 35%", "Post 3x per week on social"],
        notes=f"Key challenges: {challenges_text}. Focus on data-driven decisions using Forge insights.",
        status="active",
    )
    db.add(sn)

    # --- Alerts (welcome) ---
    alerts_data = [
        ("welcome", "success", "general", "Welcome to Forge!",
         f"Your dashboard is ready for {shop.name}. Connect your POS system to start seeing real data!"),
        ("tip", "info", "revenue",
         "Connect your POS to import sales data",
         "Go to Settings to connect Shopify, Square, or Clover. Your dashboard will populate automatically."),
        ("tip", "info", "customers",
         "Your competitors are being monitored",
         f"We're gathering data on {len(comp_names)} competitor(s). Check the Competitors tab in 24 hours for insights."
         if comp_names else
         "Add competitors in the Competitors section to start monitoring their reviews and activity."),
    ]
    for atype, sev, cat, title, msg in alerts_data:
        a = Alert(
            id=nid(), shop_id=shop.id, alert_type=atype, severity=sev,
            category=cat, title=title, message=msg,
        )
        db.add(a)

    db.commit()
