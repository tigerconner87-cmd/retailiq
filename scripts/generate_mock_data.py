"""Generate 180 days of realistic mock data for Forge demo.

Targets realistic small retail boutique doing $30K-$40K/month:
- 500 customers with realistic visit/spend distributions
- 35 products ($15-$120 range, 40-60% COGS)
- Daily revenue: $800-$2,500 weekdays, $1,500-$4,000 weekends
- Monthly revenue: $25,000-$45,000
- Seasonal patterns: Nov-Dec busier, Jan-Feb slower
- Time patterns: lunch (11am-1pm) and after-work (5pm-7pm) peaks
- Weekend patterns: Saturday busiest, Sunday moderate, Tuesday slowest
- Power law product distribution (some products sell much more)
- 55 own reviews (mostly 4-5 stars), realistic competitor reviews
- 40-60 at-risk customers (30+ days inactive), 20-30 lost (60+ days)

Run:  python -m scripts.generate_mock_data
"""

import math
import random
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import (
    Agent, AgentActivity, AgentDeliverable, AgentRun, AuditLog,
    Alert, Competitor, CompetitorReview, CompetitorSnapshot, Customer,
    DailySnapshot, Expense, Goal, HourlySnapshot, MarketingCampaign,
    MarketingResponse, Product, ProductGoal, Recommendation, Review,
    RevenueGoal, SentEmail, Shop, ShopSettings, StrategyNote,
    Transaction, TransactionItem, User,
)
from app.services.auth import hash_password

random.seed(42)

# ── Configuration ─────────────────────────────────────────────────────────────

DEMO_EMAIL = "demo@forgeapp.com"
DEMO_PASSWORD = "demo1234"
DEMO_NAME = "Alex Demo"
SHOP_NAME = "Urban Threads Boutique"
DAYS = 180

# 35 products: $15-$120 range, costs = 40-60% of price
PRODUCTS = [
    # (name, category, price, cost, sku, stock)
    ("Organic Cotton T-Shirt", "Apparel", 32.00, 14.40, "APP-001", 85),
    ("Slim Fit Jeans", "Apparel", 62.00, 27.90, "APP-002", 45),
    ("Cotton Hoodie", "Apparel", 55.00, 24.75, "APP-003", 38),
    ("Linen Summer Dress", "Apparel", 68.00, 30.60, "APP-004", 30),
    ("Vintage Denim Jacket", "Apparel", 85.00, 38.25, "APP-005", 22),
    ("Beanie Hat", "Apparel", 22.00, 9.90, "APP-006", 60),
    ("Wool Blend Sweater", "Apparel", 54.00, 24.30, "APP-007", 35),
    ("Canvas Tote Bag", "Accessories", 28.00, 12.60, "ACC-001", 70),
    ("Bamboo Sunglasses", "Accessories", 36.00, 16.20, "ACC-002", 55),
    ("Linen Scarf", "Accessories", 24.00, 10.80, "ACC-003", 48),
    ("Leather Wallet", "Accessories", 48.00, 21.60, "ACC-004", 40),
    ("Enamel Pin Set", "Accessories", 15.00, 6.00, "ACC-005", 120),
    ("Silver Pendant Necklace", "Accessories", 42.00, 18.90, "ACC-006", 32),
    ("Woven Belt", "Accessories", 30.00, 13.50, "ACC-007", 42),
    ("Ceramic Travel Mug", "Home", 22.00, 9.90, "HOM-001", 65),
    ("Soy Candle Set", "Home", 30.00, 13.50, "HOM-002", 50),
    ("Reusable Water Bottle", "Home", 24.00, 10.80, "HOM-003", 55),
    ("Linen Apron", "Home", 35.00, 15.75, "HOM-004", 28),
    ("Macrame Plant Hanger", "Home", 28.00, 12.60, "HOM-005", 35),
    ("Scented Diffuser", "Home", 38.00, 17.10, "HOM-006", 30),
    ("Recycled Notebook", "Stationery", 16.00, 6.40, "STA-001", 90),
    ("Brush Pen Set", "Stationery", 18.00, 7.20, "STA-002", 75),
    ("Washi Tape Collection", "Stationery", 15.00, 6.00, "STA-003", 100),
    ("Leather Journal", "Stationery", 32.00, 14.40, "STA-004", 40),
    ("Sticker Pack", "Stationery", 12.00, 4.80, "STA-005", 150),
    ("Graphic Print Poster", "Decor", 20.00, 8.00, "DEC-001", 45),
    ("Handmade Coasters (4pk)", "Decor", 18.00, 7.20, "DEC-002", 55),
    ("Photo Frame (5x7)", "Decor", 22.00, 9.90, "DEC-003", 40),
    ("Artisan Soap Bar", "Beauty", 15.00, 6.00, "BEA-001", 80),
    ("Hand Cream Duo", "Beauty", 22.00, 9.90, "BEA-002", 60),
    ("Lip Balm Set", "Beauty", 16.00, 6.40, "BEA-003", 90),
    ("Essential Oil Blend", "Beauty", 26.00, 11.70, "BEA-004", 45),
    ("Lavender Bath Salts", "Beauty", 18.00, 7.20, "BEA-005", 50),
    ("Gift Card $25", "Gift Cards", 25.00, 0, "GFT-025", 999),
    ("Gift Card $50", "Gift Cards", 50.00, 0, "GFT-050", 999),
]

# Power-law product popularity weights (top sellers dominate)
PRODUCT_WEIGHTS = [
    18, 14, 10, 6, 5, 8, 4,      # Apparel: T-shirt & jeans dominate
    10, 5, 4, 4, 12, 3, 2,       # Accessories: tote & pins are impulse buys
    7, 6, 5, 2, 2, 3,            # Home: mugs & candles popular
    8, 4, 6, 2, 9,               # Stationery: notebooks & stickers high volume
    2, 3, 2,                     # Decor: slower
    6, 4, 5, 3, 3,               # Beauty: steady sellers
    1, 1,                        # Gift Cards: occasional
]

COMPETITORS = [
    # (name, address, category, current_rating, review_count, old_rating_offset)
    ("The Corner Store", "123 Main St", "retail", 4.2, 187, 0.1),
    ("City Goods Co", "456 Oak Ave", "retail", 3.9, 94, 0.0),
    ("Market Square Boutique", "789 Elm Blvd", "boutique", 4.5, 256, -0.1),
    ("Urban Supply Co", "321 Pine St", "retail", 4.0, 132, 0.2),
    ("Neighborhood Finds", "654 Cedar Ln", "thrift", 3.2, 68, 0.1),
    ("Style Hub", "222 Birch Rd", "boutique", 3.8, 201, 0.5),
    ("The Crafted Home", "888 Willow Way", "home goods", 4.1, 148, 0.0),
    ("Fresh Kicks", "555 Maple Dr", "sneakers", 4.1, 175, 0.4),
]

REVIEWER_NAMES = [
    "Alex M.", "Jordan T.", "Chris L.", "Sam P.", "Taylor R.",
    "Morgan K.", "Casey W.", "Riley B.", "Drew N.", "Jamie S.",
    "Pat H.", "Quinn D.", "Avery F.", "Blake G.", "Dakota J.",
    "Frankie V.", "Hayden C.", "Jules A.", "Kendall O.", "Logan E.",
    "Skyler M.", "Reese K.", "Cameron B.", "Emery T.", "Parker W.",
    "Finley R.", "Rowan S.", "Sage D.", "Charlie P.", "Ainsley H.",
]

POSITIVE_REVIEWS = [
    "Love this shop! Great selection and the staff is always helpful. Will definitely be back!",
    "My favorite local boutique. Unique finds every visit! The candles are amazing.",
    "Amazing quality products. Worth every penny. Bought gifts for the whole family.",
    "Such a cute store with great vibes. The owner is so friendly and knowledgeable.",
    "Best accessories selection in the area. Always my first stop for gifts.",
    "Friendly staff, beautiful store. Keep up the great work! Love the new collection.",
    "Discovered this gem last month. Already been back three times! Addicted to their notebooks.",
    "Perfect place for unique gifts. Everything is so well curated. Five stars!",
    "The quality is consistently excellent. Never disappointed with anything I've bought here.",
    "Beautiful store, great music, friendly people. Shopping here is an experience, not a chore.",
    "Finally a boutique that understands quality over quantity. Every item feels special.",
    "Bought the ceramic mug and leather wallet - both exceeded expectations. Highly recommend!",
]

NEUTRAL_REVIEWS = [
    "Decent shop. Some nice things but prices are a bit high for what you get.",
    "Good selection but the store could be better organized. Hard to find specific items.",
    "Nice products. Nothing super unique though. Average experience overall.",
    "Cute store but limited hours. Wish they were open later on weekdays.",
    "Some great items but the size range for clothing is limited. Hope they expand.",
    "The products are nice but I felt a bit ignored when I walked in. Okay experience.",
]

NEGATIVE_REVIEWS = [
    "Waited 10 minutes and nobody offered to help. Disappointing service.",
    "Prices don't match the quality. Found similar items cheaper elsewhere.",
    "Very limited hours. Came by twice and they were closed during posted hours.",
    "Bought a tote bag that fell apart after a week. No refund policy posted.",
    "Store was messy and disorganized. Couldn't find anything. Won't be returning.",
    "Overpriced for what it is. The candle I bought barely had any scent.",
]

COMPETITOR_POSITIVE_REVIEWS = [
    "Great store with amazing customer service! Always a pleasure shopping here.",
    "Love the selection. Prices are very reasonable for the quality you get.",
    "My go-to shop for gifts. Never fails to have something perfect.",
    "Clean, organized, and the staff always remembers my name. Five stars!",
    "Really impressed with the quality. Everything feels premium and well-curated.",
    "Best shopping experience in the area. The staff went above and beyond to help me find what I needed.",
    "Beautiful store with unique items you can't find anywhere else. Highly recommend!",
    "Friendly atmosphere and great prices. I always leave with something I love.",
    "The owner is incredibly knowledgeable and passionate. You can tell they care about their customers.",
    "Discovered this gem recently and I'm hooked. Great selection and wonderful staff.",
]

COMPETITOR_NEUTRAL_REVIEWS = [
    "It's okay. Nothing special but decent enough for the area.",
    "Average shop. Some good items, some meh. Prices are fair.",
    "Nice enough store but nothing that really stands out. Might come back.",
    "Decent selection but the layout is confusing. Hard to find what you need.",
    "Some good products but the prices are a bit high for what you get.",
    "Staff was friendly but they didn't have what I was looking for. Average experience.",
]

COMPETITOR_NEGATIVE_REVIEWS_MAP = {
    "The Corner Store": [
        "Waited forever at checkout. Only one register open on a Saturday!",
        "The store is so cluttered you can barely walk through the aisles.",
        "Staff seemed annoyed that I was asking questions. Very unwelcoming.",
        "Bought a shirt that fell apart after one wash. Poor quality for the price.",
    ],
    "City Goods Co": [
        "Very overpriced for what you get. Found the same stuff cheaper online.",
        "The store smelled musty and the lighting was terrible. Not inviting at all.",
        "Staff was on their phones the entire time. Nobody offered to help.",
        "Limited selection and high prices. Not sure how they stay in business.",
        "Returned an item and they gave me store credit only. No refund policy is ridiculous.",
    ],
    "Market Square Boutique": [
        "Beautiful store but way too expensive. $80 for a basic tote bag? Come on.",
        "Felt very judged when I walked in. The staff was snobbish.",
    ],
    "Urban Supply Co": [
        "Slow service and long lines. They need more staff during weekends.",
        "The quality has gone downhill lately. My last few purchases were disappointing.",
        "Store hours are unreliable. Showed up twice during posted hours and they were closed.",
        "Used to love this place but it's gone downhill. Dirty floors and messy displays.",
    ],
    "Neighborhood Finds": [
        "Everything is overpriced thrift store quality. Don't be fooled by the cute exterior.",
        "Found a stain on a 'new' item they were selling at full price. Sketchy.",
        "The owner was rude when I asked about a return. Never going back.",
        "Tiny store with barely any selection. Waste of a trip.",
        "Prices keep going up but quality keeps going down. Very disappointing.",
    ],
    "Style Hub": [
        "Terrible experience. Waited 15 minutes and nobody acknowledged me.",
        "The store is dirty and disorganized. Products just thrown on shelves.",
        "Rude staff. I asked for help and was told 'just look around.'",
        "Bought a bag that broke within a week. When I went back they blamed me.",
        "This place has really gone downhill. Used to be great, now it's awful.",
        "Slow checkout, rude cashier, and the item I bought was defective. 0 stars if I could.",
    ],
    "The Crafted Home": [
        "Nice products but the prices are insane. $35 for a small candle?",
        "Parking is terrible and the store is hard to find. Frustrating experience.",
        "Staff was helpful but they didn't have sizes/colors I needed. Very limited stock.",
    ],
    "Fresh Kicks": [
        "Waited 20 minutes for slow service. The staff didn't seem to care at all.",
        "Prices jumped way up recently. Same shoes cost 30% more than last year.",
        "The store is messy and disorganized. Shoes just piled on tables randomly.",
        "Bought sneakers that started falling apart in two weeks. Total waste of money.",
        "Used to be my go-to but the quality and service have tanked. Very sad.",
        "Staff was pushy and kept trying to upsell me on expensive stuff I didn't want.",
    ],
}

COMPETITOR_NEGATIVE_REVIEWS_DEFAULT = [
    "Terrible customer service. Staff was rude and unhelpful.",
    "Very overpriced. Found the same products for half the price online.",
    "Dirty store, broken shelving. They really need to clean up.",
    "Slow service and the staff seemed disinterested. Won't be coming back.",
]


def nid():
    return str(uuid.uuid4())


def classify_sentiment(text: str, rating: int) -> str:
    if rating >= 4:
        return "positive"
    elif rating <= 2:
        return "negative"
    return "neutral"


# ── Seasonal & Pattern Helpers ────────────────────────────────────────────────

def get_seasonal_factor(d: date) -> float:
    """Returns a multiplier for seasonal patterns. Nov-Dec boost, Jan-Feb dip."""
    month = d.month
    factors = {
        1: 0.78, 2: 0.82, 3: 0.90, 4: 0.95, 5: 1.0,
        6: 1.05, 7: 1.02, 8: 0.98, 9: 0.95, 10: 1.02,
        11: 1.18, 12: 1.40,
    }
    base = factors.get(month, 1.0)
    # Extra boost around Black Friday (last week of Nov)
    if month == 11 and d.day >= 23:
        base *= 1.35
    # Extra boost mid-December gift shopping
    if month == 12 and 10 <= d.day <= 23:
        base *= 1.25
    # Dip around Christmas/New Year
    if month == 12 and d.day >= 26:
        base *= 0.55
    return base


def get_dow_factor(dow: int) -> float:
    """Day-of-week multiplier. 0=Mon, 6=Sun.
    Tuesday slowest, Saturday busiest, Sunday moderate."""
    return {
        0: 0.80,  # Monday
        1: 0.70,  # Tuesday (slowest)
        2: 0.85,  # Wednesday
        3: 0.90,  # Thursday
        4: 1.10,  # Friday
        5: 1.55,  # Saturday (busiest)
        6: 1.10,  # Sunday (moderate)
    }[dow]


def get_hour_weights() -> list[float]:
    """Hourly weights for transaction distribution (9am-8pm).
    Peaks at lunch (11am-1pm) and after work (5pm-7pm)."""
    return [
        3,   # 9-10am:  just opened, light
        5,   # 10-11am: warming up
        11,  # 11-12pm: lunch crowd starts
        14,  # 12-1pm:  peak lunch
        8,   # 1-2pm:   post-lunch
        5,   # 2-3pm:   afternoon lull
        4,   # 3-4pm:   quiet
        6,   # 4-5pm:   picking up
        12,  # 5-6pm:   after-work peak
        13,  # 6-7pm:   after-work peak
        7,   # 7-8pm:   winding down
    ]


def is_anomaly_day(d: date) -> tuple[bool, float]:
    """Check if this day should be an anomaly. Returns (is_anomaly, factor)."""
    random.seed(d.toordinal())
    r = random.random()
    random.seed(42 + d.toordinal())

    if r < 0.02:  # 2% chance of very high day (event, viral post, etc.)
        return True, random.uniform(1.5, 2.0)
    elif r < 0.04:  # 2% chance of very low day (weather, road closure, etc.)
        return True, random.uniform(0.35, 0.55)
    return False, 1.0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Dropping and recreating all tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Tables ready.")

    db = SessionLocal()

    # Clean existing demo data
    existing = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if existing:
        print("Removing existing demo data...")
        shops = db.query(Shop).filter(Shop.user_id == existing.id).all()
        for shop in shops:
            db.query(Recommendation).filter(Recommendation.shop_id == shop.id).delete()
            db.query(StrategyNote).filter(StrategyNote.shop_id == shop.id).delete()
            db.query(ProductGoal).filter(ProductGoal.shop_id == shop.id).delete()
            db.query(Goal).filter(Goal.shop_id == shop.id).delete()
            db.query(MarketingResponse).filter(MarketingResponse.shop_id == shop.id).delete()
            db.query(MarketingCampaign).filter(MarketingCampaign.shop_id == shop.id).delete()
            db.query(RevenueGoal).filter(RevenueGoal.shop_id == shop.id).delete()
            db.query(Expense).filter(Expense.shop_id == shop.id).delete()
            db.query(ShopSettings).filter(ShopSettings.shop_id == shop.id).delete()
            db.query(Alert).filter(Alert.shop_id == shop.id).delete()
            db.query(Review).filter(Review.shop_id == shop.id).delete()
            comps = db.query(Competitor).filter(Competitor.shop_id == shop.id).all()
            for c in comps:
                db.query(CompetitorReview).filter(CompetitorReview.competitor_id == c.id).delete()
                db.query(CompetitorSnapshot).filter(CompetitorSnapshot.competitor_id == c.id).delete()
            db.query(Competitor).filter(Competitor.shop_id == shop.id).delete()
            db.query(HourlySnapshot).filter(HourlySnapshot.shop_id == shop.id).delete()
            db.query(DailySnapshot).filter(DailySnapshot.shop_id == shop.id).delete()
            txs = db.query(Transaction).filter(Transaction.shop_id == shop.id).all()
            for tx in txs:
                db.query(TransactionItem).filter(TransactionItem.transaction_id == tx.id).delete()
            db.query(Transaction).filter(Transaction.shop_id == shop.id).delete()
            db.query(Customer).filter(Customer.shop_id == shop.id).delete()
            db.query(Product).filter(Product.shop_id == shop.id).delete()
        db.query(Shop).filter(Shop.user_id == existing.id).delete()
        db.query(User).filter(User.id == existing.id).delete()
        db.commit()

    # Create user and shop
    print("Creating demo user and shop...")
    user = User(
        id=nid(), email=DEMO_EMAIL, hashed_password=hash_password(DEMO_PASSWORD),
        full_name=DEMO_NAME, plan_tier="growth", onboarding_completed=True, onboarding_step=4,
    )
    db.add(user)
    db.flush()

    shop = Shop(
        id=nid(), user_id=user.id, name=SHOP_NAME, pos_system="square",
        address="742 Evergreen Terrace, Portland, OR 97201",
        category="boutique", store_size_sqft=1200, staff_count=4,
        latitude=45.5152, longitude=-122.6784,
        google_place_id="mock-place-own-001",
    )
    db.add(shop)
    db.flush()

    # Shop settings
    print("Creating shop settings...")
    shop_settings = ShopSettings(
        id=nid(), shop_id=shop.id,
        monthly_rent=Decimal("3200"), avg_cogs_percentage=48.0,
        staff_hourly_rate=Decimal("17.50"), tax_rate=8.25,
        email_frequency="weekly",
    )
    db.add(shop_settings)
    db.flush()

    # Create products
    print(f"Creating {len(PRODUCTS)} products...")
    product_objs = []
    for name, category, price, cost, sku, stock in PRODUCTS:
        p = Product(
            id=nid(), shop_id=shop.id,
            external_id=f"sq-{sku.lower()}",
            name=name, category=category,
            price=Decimal(str(price)), cost=Decimal(str(cost)),
            sku=sku, stock_quantity=stock,
        )
        db.add(p)
        product_objs.append(p)
    db.flush()

    # ── Create 500 customers with planned visit budgets ──
    print("Creating 500 customers with realistic segments...")
    today = date.today()
    start_date = today - timedelta(days=DAYS)

    # Plan customer segments with visit/spend budgets
    customer_plans = []

    # 20 VIPs: 15-30 visits, $2,000-$5,000 total, joined early
    for i in range(20):
        join_day = random.randint(0, 40)  # Joined in first ~40 days
        visits = random.randint(15, 30)
        customer_plans.append({
            "segment": "vip", "visits": visits,
            "join_day": join_day, "idx": i,
        })

    # 80 regulars: 5-15 visits, $500-$2,000 total
    for i in range(80):
        join_day = random.randint(0, 100)
        visits = random.randint(5, 15)
        customer_plans.append({
            "segment": "regular", "visits": visits,
            "join_day": join_day, "idx": 20 + i,
        })

    # 200 occasional: 2-5 visits, $100-$500 total
    for i in range(200):
        join_day = random.randint(10, 160)
        visits = random.randint(2, 5)
        customer_plans.append({
            "segment": "occasional", "visits": visits,
            "join_day": join_day, "idx": 100 + i,
        })

    # 200 one-time: 1 visit, $30-$150 total
    for i in range(200):
        join_day = random.randint(5, 175)
        visits = 1
        customer_plans.append({
            "segment": "onetime", "visits": visits,
            "join_day": join_day, "idx": 300 + i,
        })

    # Create Customer objects
    customer_pool = []
    customer_tx_budget = {}  # customer_id -> remaining visits to assign

    for plan in customer_plans:
        idx = plan["idx"]
        first_day = start_date + timedelta(days=plan["join_day"])
        has_email = random.random() > 0.25  # 75% have email

        c = Customer(
            id=nid(), shop_id=shop.id, external_id=f"sq-cust-{idx+1:04d}",
            email=f"customer{idx+1}@example.com" if has_email else None,
            segment="regular",  # Will be recalculated later
            first_seen=datetime.combine(first_day, datetime.min.time()),
            last_seen=datetime.combine(first_day, datetime.min.time()),
            visit_count=0, total_spent=Decimal("0"),
        )
        db.add(c)
        customer_pool.append(c)
        customer_tx_budget[c.id] = {
            "remaining": plan["visits"],
            "segment": plan["segment"],
            "join_date": first_day,
        }
    db.flush()

    # ── Pre-schedule customer visits across the 180 days ──
    # This ensures each customer gets the right number of visits
    print("Scheduling customer visits across 180 days...")
    scheduled_visits = defaultdict(list)  # date -> list of customer objects

    for c in customer_pool:
        budget = customer_tx_budget[c.id]
        join_date = budget["join_date"]
        num_visits = budget["remaining"]
        seg = budget["segment"]

        available_days = (today - join_date).days
        if available_days < 1:
            available_days = 1

        # For at-risk/lost simulation: some customers stop visiting
        # ~50 customers should have last_seen 30-60 days ago (at_risk)
        # ~25 customers should have last_seen 60+ days ago (lost)
        cutoff_date = today  # Default: can visit up to today

        if seg == "occasional" and random.random() < 0.22:
            # ~44 of 200 occasional become at-risk (last visit 30-60 days ago)
            cutoff_date = today - timedelta(days=random.randint(31, 58))
        elif seg == "onetime" and random.random() < 0.12:
            # ~24 of 200 one-time become lost (last visit 60+ days ago)
            cutoff_date = today - timedelta(days=random.randint(61, 120))
        elif seg == "regular" and random.random() < 0.10:
            # ~8 regulars become at-risk
            cutoff_date = today - timedelta(days=random.randint(32, 50))

        max_day = min((cutoff_date - join_date).days, available_days)
        if max_day < 1:
            max_day = 1

        # Distribute visits across the available window
        visit_days = sorted(random.sample(
            range(max_day), min(num_visits, max_day)
        )) if max_day >= num_visits else list(range(max_day))

        for vd in visit_days:
            visit_date = join_date + timedelta(days=vd)
            if visit_date <= today:
                scheduled_visits[visit_date].append(c)

    # ── Generate transactions day by day ──
    print(f"Generating {DAYS} days of transactions...")
    daily_data = defaultdict(lambda: {
        "revenue": Decimal("0"), "cost": Decimal("0"), "tx_count": 0, "items_sold": 0,
        "customers": set(), "new_customers": set(),
        "hourly": defaultdict(lambda: {"rev": Decimal("0"), "count": 0}),
    })

    seen_customers = set()
    total_tx = 0
    total_revenue = Decimal("0")
    hour_weights = get_hour_weights()

    random.seed(42)

    current_date = start_date
    while current_date <= today:
        dow = current_date.weekday()
        day_offset = (current_date - start_date).days

        # Calculate multipliers
        growth_factor = 1.0 + day_offset * 0.001  # Very gradual growth (~18% over 180 days)
        seasonal = get_seasonal_factor(current_date)
        dow_factor = get_dow_factor(dow)
        is_anom, anom_factor = is_anomaly_day(current_date)

        # Base daily transactions: ~22 avg to hit ~$35K/month
        # With avg tx of ~$52 and seasonal/dow variation
        base_count = 22
        tx_count_target = int(base_count * growth_factor * seasonal * dow_factor * anom_factor)
        tx_count_target += random.randint(-2, 2)
        tx_count_target = max(6, tx_count_target)

        # Get scheduled customer visits for this day
        day_customers = list(scheduled_visits.get(current_date, []))

        # Fill remaining slots with anonymous transactions
        anon_count = max(0, tx_count_target - len(day_customers))

        # Generate customer transactions
        all_day_txs = []
        for customer in day_customers:
            all_day_txs.append(("customer", customer))
        for _ in range(anon_count):
            all_day_txs.append(("anon", None))

        random.shuffle(all_day_txs)

        for tx_type, customer in all_day_txs:
            hour = random.choices(range(9, 20), weights=hour_weights)[0]
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            ts = datetime(current_date.year, current_date.month, current_date.day, hour, minute, second)

            # Pick items: most transactions are 1-2 items for a small boutique
            num_items = random.choices([1, 2, 3, 4], weights=[45, 32, 18, 5])[0]
            chosen_products = random.choices(product_objs, weights=PRODUCT_WEIGHTS, k=num_items)

            subtotal = Decimal("0")
            total_cost = Decimal("0")
            items_data = []
            for prod in chosen_products:
                qty = random.choices([1, 2], weights=[88, 12])[0]
                line_total = prod.price * qty
                subtotal += line_total
                if prod.cost:
                    total_cost += prod.cost * qty
                items_data.append((prod, qty, line_total))

            # Occasional discounts (8% of transactions)
            discount = Decimal("0")
            if random.random() < 0.08:
                pct = Decimal(str(random.choice([0.10, 0.15, 0.20])))
                discount = (subtotal * pct).quantize(Decimal("0.01"))
                subtotal -= discount

            tax = (subtotal * Decimal("0.0825")).quantize(Decimal("0.01"))
            total = subtotal + tax

            payment = random.choices(["card", "cash", "mobile"], weights=[65, 25, 10])[0]

            tx = Transaction(
                id=nid(), shop_id=shop.id,
                external_id=f"sq-tx-{current_date.isoformat()}-{total_tx:06d}",
                customer_id=customer.id if customer else None,
                subtotal=subtotal, tax=tax, discount=discount, total=total,
                items_count=len(items_data), payment_method=payment, timestamp=ts,
            )
            db.add(tx)
            db.flush()

            for prod, qty, line_total in items_data:
                ti = TransactionItem(
                    id=nid(), transaction_id=tx.id, product_id=prod.id,
                    quantity=qty, unit_price=prod.price, total=line_total,
                )
                db.add(ti)

            # Update customer stats
            if customer:
                customer.visit_count += 1
                customer.total_spent += total
                customer.last_seen = ts
                if customer.visit_count > 0:
                    customer.avg_order_value = (customer.total_spent / customer.visit_count).quantize(Decimal("0.01"))
                daily_data[current_date]["customers"].add(customer.id)
                if customer.id not in seen_customers:
                    seen_customers.add(customer.id)
                    daily_data[current_date]["new_customers"].add(customer.id)

            # Update daily stats
            daily_data[current_date]["revenue"] += total
            daily_data[current_date]["cost"] += total_cost
            daily_data[current_date]["tx_count"] += 1
            daily_data[current_date]["items_sold"] += sum(qty for _, qty, _ in items_data)
            daily_data[current_date]["hourly"][hour]["rev"] += total
            daily_data[current_date]["hourly"][hour]["count"] += 1

            total_tx += 1
            total_revenue += total

        current_date += timedelta(days=1)

        if (current_date - start_date).days % 15 == 0:
            db.flush()

    db.flush()
    avg_daily = float(total_revenue) / DAYS
    avg_monthly = avg_daily * 30.44
    print(f"  Generated {total_tx} transactions")
    print(f"  Total revenue: ${float(total_revenue):,.0f}")
    print(f"  Avg daily: ${avg_daily:,.0f}")
    print(f"  Avg monthly: ${avg_monthly:,.0f}")

    # ── Update customer segments based on actual behavior ──
    print("Updating customer segments...")
    seg_counts = {"vip": 0, "regular": 0, "at_risk": 0, "lost": 0}
    for c in customer_pool:
        if c.visit_count == 0:
            c.segment = "lost"
            seg_counts["lost"] += 1
            continue

        days_since = 0
        if c.last_seen:
            days_since = (datetime.combine(today, datetime.min.time()) - c.last_seen).days

        spent = float(c.total_spent) if c.total_spent else 0

        # VIP: high spend + frequent visits + still active
        if spent >= 1500 and c.visit_count >= 10 and days_since <= 30:
            c.segment = "vip"
            seg_counts["vip"] += 1
        elif days_since > 60:
            c.segment = "lost"
            seg_counts["lost"] += 1
        elif days_since > 30:
            c.segment = "at_risk"
            seg_counts["at_risk"] += 1
        else:
            c.segment = "regular"
            seg_counts["regular"] += 1

        # Calculate avg days between visits
        if c.visit_count > 1 and c.first_seen and c.last_seen:
            total_days = (c.last_seen - c.first_seen).days
            c.avg_days_between_visits = round(total_days / (c.visit_count - 1), 1) if total_days > 0 else None
    db.flush()
    print(f"  Segments: VIP={seg_counts['vip']}, Regular={seg_counts['regular']}, "
          f"At-risk={seg_counts['at_risk']}, Lost={seg_counts['lost']}")

    # ── Create snapshots ──
    print("Creating daily and hourly snapshots...")
    for d, data in daily_data.items():
        unique = len(data["customers"])
        new = len(data["new_customers"])
        repeat = unique - new
        avg_tv = data["revenue"] / data["tx_count"] if data["tx_count"] > 0 else Decimal("0")

        ds = DailySnapshot(
            id=nid(), shop_id=shop.id, date=d,
            total_revenue=data["revenue"],
            total_cost=data["cost"],
            transaction_count=data["tx_count"],
            avg_transaction_value=avg_tv.quantize(Decimal("0.01")),
            items_sold=data["items_sold"],
            unique_customers=unique, repeat_customers=max(0, repeat), new_customers=new,
        )
        db.add(ds)

        for hour, hdata in data["hourly"].items():
            hs = HourlySnapshot(
                id=nid(), shop_id=shop.id, date=d, hour=hour,
                revenue=hdata["rev"], transaction_count=hdata["count"],
            )
            db.add(hs)

    # ── Create reviews for own shop ──
    print("Creating 55 reviews...")
    for i in range(55):
        days_ago = random.randint(0, 300)
        # Mostly 4-5 stars: realistic for a well-run small shop
        rating = random.choices([1, 2, 3, 4, 5], weights=[3, 4, 8, 30, 55])[0]
        if rating >= 4:
            text = random.choice(POSITIVE_REVIEWS)
        elif rating <= 2:
            text = random.choice(NEGATIVE_REVIEWS)
        else:
            text = random.choice(NEUTRAL_REVIEWS)

        r = Review(
            id=nid(), shop_id=shop.id, source="google",
            author_name=random.choice(REVIEWER_NAMES),
            rating=rating, text=text,
            review_date=datetime.now() - timedelta(days=days_ago),
            sentiment=classify_sentiment(text, rating),
            is_own_shop=True,
        )
        db.add(r)

    # ── Create competitors with reviews ──
    print(f"Creating {len(COMPETITORS)} competitors...")
    comp_objs = []
    for name, address, category, rating, review_count, old_rating_offset in COMPETITORS:
        comp = Competitor(
            id=nid(), shop_id=shop.id, name=name,
            google_place_id=f"mock-comp-{name[:4].lower()}", address=address,
            category=category,
            rating=Decimal(str(rating)), review_count=review_count,
            latitude=45.5152 + random.uniform(-0.03, 0.03),
            longitude=-122.6784 + random.uniform(-0.03, 0.03),
        )
        db.add(comp)
        db.flush()
        comp_objs.append(comp)

        # Competitor snapshots (weekly for past 6 months)
        old_rating = rating + old_rating_offset
        for w in range(26):
            snap_date = today - timedelta(weeks=w)
            progress = 1.0 - (w / 26.0)
            snap_rating = old_rating + (rating - old_rating) * progress
            snap_rating += random.uniform(-0.15, 0.15)
            snap_rating = round(max(1.0, min(5.0, snap_rating)), 1)
            snap_reviews = review_count - w * random.randint(1, 4)
            cs = CompetitorSnapshot(
                id=nid(), competitor_id=comp.id, date=snap_date,
                rating=Decimal(str(snap_rating)),
                review_count=max(10, snap_reviews),
            )
            db.add(cs)

        # Competitor reviews
        neg_templates = COMPETITOR_NEGATIVE_REVIEWS_MAP.get(name, COMPETITOR_NEGATIVE_REVIEWS_DEFAULT)

        if rating >= 4.3:
            weights = [3, 5, 10, 35, 47]
        elif rating >= 3.8:
            weights = [8, 10, 15, 35, 32]
        else:
            weights = [12, 15, 20, 30, 23]

        num_comp_reviews = random.randint(15, 30)

        recent_neg_count = 0
        if name == "Style Hub":
            recent_neg_count = 4
        elif name == "Fresh Kicks":
            recent_neg_count = 3
        elif name == "Neighborhood Finds":
            recent_neg_count = 2

        for j in range(num_comp_reviews):
            if j < recent_neg_count:
                days_ago = random.randint(0, 5)
                cr_rating = random.choice([1, 2])
                cr_text = random.choice(neg_templates)
            else:
                days_ago = random.randint(1, 180)
                cr_rating = random.choices([1, 2, 3, 4, 5], weights=weights)[0]
                if cr_rating >= 4:
                    cr_text = random.choice(COMPETITOR_POSITIVE_REVIEWS)
                elif cr_rating <= 2:
                    cr_text = random.choice(neg_templates)
                else:
                    cr_text = random.choice(COMPETITOR_NEUTRAL_REVIEWS)

            cr = CompetitorReview(
                id=nid(), competitor_id=comp.id,
                author_name=random.choice(REVIEWER_NAMES),
                rating=cr_rating, text=cr_text,
                review_date=datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 23)),
                sentiment=classify_sentiment(cr_text, cr_rating),
            )
            db.add(cr)

    # ── Create expenses ──
    print("Creating expenses...")
    expenses_data = [
        ("rent", "Store Rent", 3200),
        ("labor", "Staff Wages (4 employees)", 8400),
        ("inventory", "Inventory Purchases", 4500),
        ("marketing", "Marketing & Advertising", 600),
        ("utilities", "Utilities (Electric, Water, Internet)", 450),
        ("other", "Insurance", 280),
        ("other", "POS Software Subscription", 79),
        ("other", "Cleaning Service", 200),
    ]
    for cat, name, amount in expenses_data:
        e = Expense(
            id=nid(), shop_id=shop.id, category=cat, name=name,
            amount=Decimal(str(amount)), is_monthly=True,
        )
        db.add(e)

    # ── Create revenue goals ──
    print("Creating revenue goals...")
    for m_offset in range(6):
        goal_month = today.replace(day=1) - timedelta(days=30 * m_offset)
        goal_str = goal_month.strftime("%Y-%m")
        target = 35000 + m_offset * 500
        rg = RevenueGoal(
            id=nid(), shop_id=shop.id, month=goal_str,
            target_amount=Decimal(str(target)),
        )
        db.add(rg)

    # ── Create marketing campaigns ──
    print("Creating marketing campaigns...")
    campaigns = [
        ("Summer Sale Instagram Campaign", "social", 250, 45, 3200),
        ("Email Newsletter - Back to School", "email", 0, 30, 1800),
        ("Local Newspaper Ad", "print", 400, 14, 900),
        ("Holiday Window Display", "in-store", 150, 30, 5500),
        ("Valentine's Day Promo", "social", 180, 7, 2100),
    ]
    for name, channel, spend, duration, rev in campaigns:
        start = today - timedelta(days=random.randint(10, 150))
        mc = MarketingCampaign(
            id=nid(), shop_id=shop.id, name=name, channel=channel,
            spend=Decimal(str(spend)), start_date=start,
            end_date=start + timedelta(days=duration),
            revenue_attributed=Decimal(str(rev)),
        )
        db.add(mc)

    # ── Create alerts ──
    print("Creating alerts...")
    alerts_data = [
        ("revenue_drop", "critical", "revenue", "Revenue dropped 18% this week",
         "This week's revenue is down 18% compared to last week. Consider running a promotion to drive traffic."),
        ("negative_review", "warning", "reviews", "New 1-star Google review",
         '"Waited 10 minutes and nobody offered to help." — Alex M., 1 star. Respond promptly.'),
        ("customer_churn", "warning", "customers", "12 VIP customers at risk of churning",
         "12 customers who spent $200+ haven't visited in 25+ days. Send a win-back offer."),
        ("competitor_drop", "info", "competitors", "Style Hub dropped to 3.8 stars",
         "Your competitor Style Hub just dropped from 4.3 to 3.8 stars. This is an opportunity."),
        ("goal_progress", "info", "goals", "Monthly goal 72% complete with 8 days left",
         "You've hit $25,200 of your $35,000 goal. You need $1,225/day to hit target."),
        ("revenue_milestone", "success", "revenue", "Best Saturday ever: $3,850 in revenue!",
         "Last Saturday was your highest revenue day ever, beating the previous record by 15%."),
        ("slow_mover", "warning", "inventory", "3 products haven't sold in 14+ days",
         "Macrame Plant Hanger, Photo Frame, and Woven Belt have had zero sales in 2+ weeks."),
        ("return_rate_drop", "warning", "customers", "Customer return rate below target",
         "Only 28.3% of customers are returning. Industry average is 30-40%. Consider a loyalty program."),
    ]
    for i, (atype, severity, category, title, message) in enumerate(alerts_data):
        a = Alert(
            id=nid(), shop_id=shop.id, alert_type=atype, severity=severity,
            category=category, title=title, message=message,
            is_read=(i > 3),
            created_at=datetime.now() - timedelta(days=i, hours=random.randint(0, 12)),
        )
        db.add(a)

    # ── Create marketing responses ──
    print("Creating marketing responses...")
    marketing_resp_data = [
        {
            "comp_name": "Style Hub",
            "weakness": "Multiple customers reporting rude staff and long wait times",
            "opp_type": "negative_reviews",
            "priority": "hot",
            "instagram": (
                "At Urban Threads Boutique, great service is our promise. Every customer matters, "
                "every visit counts. That's why our community keeps coming back! "
                "Come experience the difference. #CustomerFirst #QualityService #ShopLocal"
            ),
            "email": (
                "Hi!\n\nWe believe shopping should be a joy, not a chore. At Urban Threads Boutique, "
                "our team is dedicated to making every visit special — from personalized "
                "recommendations to a warm welcome at the door.\n\n"
                "Don't take our word for it — come see for yourself! "
                "This week, enjoy a free gift with any purchase over $30.\n\nWarm regards,\nThe Urban Threads Team"
            ),
            "promo": (
                "\"Service Guarantee\" Campaign: Promote your customer service commitment. "
                "Offer a free gift with purchase this week to drive foot traffic from "
                "Style Hub's dissatisfied customers."
            ),
        },
        {
            "comp_name": "Fresh Kicks",
            "weakness": "Rating dropped from 4.5 to 4.1 stars — quality and service complaints",
            "opp_type": "rating_drop",
            "priority": "hot",
            "instagram": (
                "Looking for a new favorite local shop? We've been rated 4.3+ stars by our "
                "amazing community! Stop by Urban Threads this weekend and see why customers keep coming "
                "back. First-time visitors get 10% off! #ShopLocal #NewFavorite"
            ),
            "email": (
                "Hey there!\n\nLooking for a new go-to spot for unique finds? Urban Threads Boutique has "
                "been earning rave reviews from the community. From curated accessories to handpicked "
                "home goods, we pride ourselves on quality and service.\n\n"
                "Come visit us this week and enjoy 15% off your first purchase!\n\nSee you soon!"
            ),
            "promo": (
                "\"New Neighbor\" Welcome Offer: 15% off for first-time visitors. Run targeted local "
                "ads this week while Fresh Kicks' rating is declining."
            ),
        },
        {
            "comp_name": "Neighborhood Finds",
            "weakness": "Consistent complaints about overpriced items and quality issues",
            "opp_type": "service_gap",
            "priority": "good",
            "instagram": (
                "Quality doesn't have to break the bank! At Urban Threads Boutique, "
                "we offer curated finds at prices you'll love. Every item handpicked for quality. "
                "#ValueForMoney #ShopLocal #QualityMatters"
            ),
            "email": (
                "Hi there!\n\nWe know what matters to you: quality products at fair prices. "
                "That's why at Urban Threads, every item is handpicked and quality-checked.\n\n"
                "Visit us this week for something special — and see the difference quality makes!\n\n"
                "Best,\nThe Urban Threads Team"
            ),
            "promo": (
                "\"Quality Promise\" Campaign: Highlight your quality commitment and fair pricing. "
                "Create a comparison post showing the value you offer."
            ),
        },
        {
            "comp_name": "City Goods Co",
            "weakness": "Low engagement — barely any new reviews in weeks",
            "opp_type": "low_engagement",
            "priority": "good",
            "instagram": (
                "New arrivals just dropped at Urban Threads! Fresh finds every week — "
                "from handcrafted jewelry to one-of-a-kind home decor. Follow us for daily "
                "updates and never miss a drop! #NewArrivals #AlwaysFresh #ShopLocal"
            ),
            "email": (
                "Hey!\n\nWhile some shops go quiet, we keep things exciting! "
                "This week at Urban Threads, we've got fresh arrivals, exclusive finds, "
                "and a special surprise for our loyal customers.\n\n"
                "Stop by or follow us on Instagram for daily updates!\n\nCheers,\nThe Urban Threads Team"
            ),
            "promo": (
                "\"Always Something New\" social media blitz: Post daily for the next 2 weeks "
                "showcasing new arrivals. Fill the engagement gap competitors are leaving."
            ),
        },
        {
            "comp_name": "Urban Supply Co",
            "weakness": "Store hours unreliable and quality declining",
            "opp_type": "service_gap",
            "priority": "fyi",
            "instagram": (
                "Open when you need us, with the quality you deserve. Urban Threads Boutique — "
                "reliable hours, consistent quality, always here for you. #ShopLocal #Reliable"
            ),
            "email": (
                "Hi!\n\nYou can count on us. Urban Threads is open every day with consistent hours "
                "and a team that's always ready to help.\n\nStop by anytime — we'll be here!\n\n"
                "Best,\nThe Urban Threads Team"
            ),
            "promo": (
                "Promote your reliable hours and consistent quality. Post your schedule "
                "prominently on social media and highlight your consistency."
            ),
        },
    ]

    for mrd in marketing_resp_data:
        comp_obj = next((c for c in comp_objs if c.name == mrd["comp_name"]), None)
        mr = MarketingResponse(
            id=nid(), shop_id=shop.id,
            competitor_id=comp_obj.id if comp_obj else None,
            competitor_name=mrd["comp_name"],
            weakness=mrd["weakness"],
            opportunity_type=mrd["opp_type"],
            instagram_post=mrd["instagram"],
            email_content=mrd["email"],
            promotion_idea=mrd["promo"],
            priority=mrd["priority"],
            status="new",
        )
        db.add(mr)

    # ── Create goals ──
    print("Creating goals & strategy data...")
    current_month = today.strftime("%Y-%m")
    current_q_num = (today.month - 1) // 3 + 1
    current_quarter = f"{today.year}-Q{current_q_num}"

    goals_data = [
        ("revenue", "Monthly Revenue Target", 35000, "$", "monthly", current_month),
        ("transactions", "Monthly Transactions", 680, "#", "monthly", current_month),
        ("customers", "New Customer Acquisition", 30, "#", "monthly", current_month),
        ("aov", "Average Order Value", 52, "$", "monthly", current_month),
    ]
    for gtype, title, target, unit, period, pkey in goals_data:
        g = Goal(
            id=nid(), shop_id=shop.id,
            goal_type=gtype, title=title,
            target_value=Decimal(str(target)), unit=unit,
            period=period, period_key=pkey,
            status="active",
        )
        db.add(g)

    # Past goals — compute status from actual snapshot data
    db.flush()
    from calendar import monthrange as _mr
    rev_targets = [33000, 36000, 34000]
    tx_targets = [650, 700, 660]
    for m in range(1, 4):
        past_start = today.replace(day=1) - timedelta(days=30 * m)
        past_month = past_start.strftime("%Y-%m")
        yr, mo = int(past_month[:4]), int(past_month[5:7])
        _, last_day = _mr(yr, mo)
        month_start = date(yr, mo, 1)
        month_end = date(yr, mo, last_day)

        rev_target = rev_targets[m - 1]
        actual_rev = sum(
            float(d["revenue"]) for dt, d in daily_data.items()
            if month_start <= dt <= month_end
        )
        g = Goal(
            id=nid(), shop_id=shop.id,
            goal_type="revenue", title="Monthly Revenue Target",
            target_value=Decimal(str(rev_target)), unit="$",
            period="monthly", period_key=past_month,
            status="met" if actual_rev >= rev_target else "missed",
        )
        db.add(g)

        tx_target = tx_targets[m - 1]
        actual_tx = sum(
            d["tx_count"] for dt, d in daily_data.items()
            if month_start <= dt <= month_end
        )
        g2 = Goal(
            id=nid(), shop_id=shop.id,
            goal_type="transactions", title="Monthly Transactions",
            target_value=Decimal(str(tx_target)), unit="#",
            period="monthly", period_key=past_month,
            status="met" if actual_tx >= tx_target else "missed",
        )
        db.add(g2)

    # Product goals for top products
    product_targets = [60, 45, 35, 50, 40, 55, 30, 25]
    for i, p in enumerate(product_objs[:8]):
        pg = ProductGoal(
            id=nid(), shop_id=shop.id,
            product_id=p.id,
            target_units=product_targets[i],
            period=current_month,
        )
        db.add(pg)

    # Strategy notes
    sn = StrategyNote(
        id=nid(), shop_id=shop.id,
        quarter=current_quarter,
        title="Growth & Community Building",
        objectives=[
            "Increase monthly revenue to $38K by end of quarter",
            "Grow repeat customer base by 15%",
            "Launch Instagram presence with 500+ followers",
            "Expand product line with 8 new curated items",
        ],
        key_results=[
            "Revenue: $35K -> $38K monthly",
            "Repeat rate: 28% -> 33%",
            "Instagram followers: 0 -> 500",
            "New products: launch 8 items with 50%+ margin",
        ],
        notes="Focus on building local community engagement through events and social media. Partner with 2-3 local artisans for exclusive collections.",
        status="active",
    )
    db.add(sn)

    if current_q_num > 1:
        prev_quarter = f"{today.year}-Q{current_q_num - 1}"
    else:
        prev_quarter = f"{today.year - 1}-Q4"
    sn2 = StrategyNote(
        id=nid(), shop_id=shop.id,
        quarter=prev_quarter,
        title="Foundation & Operations",
        objectives=[
            "Stabilize monthly revenue at $30K+",
            "Implement inventory management system",
            "Hire and train 2 part-time staff",
            "Set up loyalty program",
        ],
        key_results=[
            "Revenue consistently above $30K/mo",
            "Inventory accuracy at 95%+",
            "Staff trained with 4.5+ customer satisfaction",
            "Loyalty program: 80+ members",
        ],
        notes="Successfully established operational foundation. Inventory system in place, staff performing well. Loyalty program soft-launched with 72 members.",
        status="completed",
    )
    db.add(sn2)

    # ── Agent Fleet & Deliverables ──────────────────────────────────────────
    today_dt = datetime.now()

    # Create agent records
    agent_types = ["maya", "scout", "emma", "alex", "max"]
    agent_objs = {}
    for at in agent_types:
        a = Agent(id=nid(), shop_id=shop.id, agent_type=at, is_active=True)
        db.add(a)
        agent_objs[at] = a

    # Create agent runs (last 24h)
    for at in agent_types:
        hours_ago = random.randint(1, 18)
        run = AgentRun(
            id=nid(), shop_id=shop.id, agent_type=at, trigger="scheduled",
            instructions=f"Daily {at} run", status="completed",
            output_count=random.randint(1, 3), tokens_used=random.randint(500, 3000),
            duration_ms=random.randint(2000, 12000),
            created_at=today_dt - timedelta(hours=hours_ago),
            completed_at=today_dt - timedelta(hours=hours_ago, minutes=-2),
        )
        db.add(run)

    # Create agent activities
    activity_data = [
        ("maya", "content_generated", "Created Instagram post: Weekend Vibes at Urban Threads", -2.5),
        ("maya", "content_generated", "Drafted email campaign: Spring Collection Launch", -5.1),
        ("maya", "content_generated", "Generated social calendar for the week", -8.0),
        ("scout", "analysis_complete", "Competitor opportunity: Style Hub rating dropped to 3.6", -3.2),
        ("scout", "analysis_complete", "Weekly competitor digest generated", -12.0),
        ("emma", "content_generated", "Win-back emails drafted for 8 at-risk customers", -4.0),
        ("emma", "content_generated", "Customer retention report generated", -7.5),
        ("alex", "analysis_complete", "Daily briefing generated: revenue up 12%", -1.5),
        ("alex", "analysis_complete", "Weekly strategy memo prepared", -24.0),
        ("max", "analysis_complete", "Bundle opportunity: Hoodie + Beanie combo identified", -6.0),
        ("max", "analysis_complete", "Price optimization report for 5 products", -10.0),
    ]
    for at, action, desc, hours_offset in activity_data:
        act = AgentActivity(
            id=nid(), agent_id=agent_objs[at].id, shop_id=shop.id,
            action_type=action, description=desc,
            created_at=today_dt + timedelta(hours=hours_offset),
        )
        db.add(act)

    # ── Approved Deliverables (appear on dashboard pages) ──
    approved_deliverables = [
        # 3 Maya approved posts (Marketing page)
        {
            "agent_type": "maya", "deliverable_type": "social_post",
            "title": "Weekend Vibes at Urban Threads",
            "content": "Step into the weekend in style! Our Oversized Hoodie ($55) is flying off the shelves this week — grab yours before they're gone! Pair it with our Canvas Tote for the ultimate casual look.\n\n#UrbanThreads #PortlandFashion #WeekendVibes #ShopLocal #OOTD",
            "overall_quality": 88, "confidence": 0.88, "status": "approved", "hours_ago": 6,
        },
        {
            "agent_type": "maya", "deliverable_type": "social_post",
            "title": "New Arrivals Alert",
            "content": "Fresh drop alert! Our Linen Button-Up ($48) is perfect for those transitional spring days. Light, breathable, and effortlessly stylish. Available in store and ready for you.\n\n#NewArrivals #SpringStyle #LinenLove #UrbanThreads #PortlandBoutique",
            "overall_quality": 85, "confidence": 0.85, "status": "approved", "hours_ago": 18,
        },
        {
            "agent_type": "maya", "deliverable_type": "email_campaign",
            "title": "Spring Collection Preview — Exclusive First Look",
            "content": "Subject: You're Invited: Spring Collection Preview\n\nHi [Name],\n\nSpring is around the corner and we've been busy curating our new collection just for you.\n\nHighlights:\n- Linen Button-Up ($48) — perfect for layering\n- Floral Sundress ($72) — brunch-ready\n- Canvas Tote ($42) — the everyday essential\n\nAs a valued customer, you get first access before we share with the public.\n\nCome visit us this weekend!\n\nWarmly,\nUrban Threads Team",
            "overall_quality": 92, "confidence": 0.92, "status": "approved", "hours_ago": 24,
        },
        # 2 Scout approved insights (Competitors page)
        {
            "agent_type": "scout", "deliverable_type": "competitor_report",
            "title": "Opportunity Alert: Style Hub Rating Drops to 3.6",
            "content": "Style Hub's Google rating dropped from 4.1 to 3.6 in the last 2 weeks. Recent negative reviews mention 'rude staff' and 'limited selection.'\n\nRecommended actions:\n1. Run a targeted Instagram campaign highlighting your friendly team and wide selection\n2. Consider a 'Welcome Style Hub customers' 10% off promotion\n3. Monitor their response — they may run a counter-promotion\n\nEstimated opportunity: Capture 15-20 of their dissatisfied customers ($800-$1,200 monthly revenue).",
            "overall_quality": 90, "confidence": 0.87, "status": "approved", "hours_ago": 12,
        },
        {
            "agent_type": "scout", "deliverable_type": "competitor_report",
            "title": "Weekly Competitive Landscape Summary",
            "content": "This week's competitive landscape:\n\n1. Style Hub (3.6★) — Rating still declining. 3 new negative reviews.\n2. Fresh Kicks (4.2★) — Stable. Launched new sneaker line.\n3. Neighborhood Finds (4.4★) — Strong week. 5 new positive reviews.\n4. City Goods Co (3.9★) — Neutral. No significant changes.\n\nYour position: Strong. Your 4.7★ rating is the highest in the area. Capitalize on competitor weakness by increasing social media presence.",
            "overall_quality": 85, "confidence": 0.83, "status": "approved", "hours_ago": 36,
        },
        # 2 Emma approved emails (Win-back page)
        {
            "agent_type": "emma", "deliverable_type": "winback_email",
            "title": "Win-Back: Sarah Johnson — 45 days inactive",
            "content": "Subject: We miss you at Urban Threads!\n\nHi Sarah,\n\nIt's been a while since your last visit and we've been thinking of you! We know you love our Classic Cotton T-Shirts — and guess what? We just got a fresh batch in 3 new colors.\n\nAs a thank you for being a valued customer, here's 15% off your next visit:\n\nCode: WELCOME15\nValid for 7 days\n\nCome say hi!\n\nWarmly,\nThe Urban Threads Team",
            "overall_quality": 91, "confidence": 0.90, "status": "approved", "hours_ago": 8,
        },
        {
            "agent_type": "emma", "deliverable_type": "winback_email",
            "title": "Win-Back: Mike Chen — 62 days inactive",
            "content": "Subject: Something special waiting for you, Mike\n\nHi Mike,\n\nWe noticed it's been a while and wanted to reach out. Your favorite Slim Fit Jeans are back in stock, plus we've added some great new accessories.\n\nHere's an exclusive 20% off your next purchase:\n\nCode: COMEBACK20\nValid for 5 days\n\nWe'd love to see you back!\n\nBest,\nUrban Threads",
            "overall_quality": 88, "confidence": 0.86, "status": "approved", "hours_ago": 10,
        },
        # 1 Alex approved briefing
        {
            "agent_type": "alex", "deliverable_type": "daily_briefing",
            "title": "Daily Briefing — Revenue Up 12.5%, Action Items Inside",
            "content": "Good morning! Here's your daily briefing:\n\nRevenue Summary:\n- Yesterday: $2,847 (+12.5% vs. last week)\n- Monthly pace: $34,200 / $35,000 target (97.7%)\n- Top seller: Oversized Hoodie (8 units, $440)\n\nKey Actions:\n1. Restock Oversized Hoodies — only 12 left at current sell rate\n2. 3 at-risk customers haven't visited in 35+ days — win-back emails ready\n3. Style Hub continues to decline — perfect time for a competitive push\n\nForecast: On track to hit monthly goal by the 27th at current pace.",
            "overall_quality": 94, "confidence": 0.93, "status": "approved", "hours_ago": 2,
        },
        # 2 Max approved suggestions (Products page)
        {
            "agent_type": "max", "deliverable_type": "bundle_suggestion",
            "title": "Bundle Opportunity: Hoodie + Beanie Winter Combo",
            "content": "Bundle: Oversized Hoodie ($55) + Wool Beanie ($22)\n\nCurrent price if bought separately: $77\nSuggested bundle price: $68 (12% discount)\nEstimated margin: 52% (still healthy)\n\nWhy this works:\n- 34% of hoodie buyers also browse beanies\n- Cross-sell rate could increase from 8% to 25%\n- Estimated additional monthly revenue: $340-$510\n\nRecommendation: Display these together near checkout with a 'Better Together' sign.",
            "overall_quality": 87, "confidence": 0.85, "status": "approved", "hours_ago": 14,
        },
        {
            "agent_type": "max", "deliverable_type": "price_recommendation",
            "title": "Price Optimization: Silk Scarf Underpriced by $7",
            "content": "Product: Silk Scarf\nCurrent price: $38\nSuggested price: $45\n\nAnalysis:\n- Your Silk Scarf is priced 16% below comparable items at nearby boutiques\n- Demand elasticity analysis shows this product can sustain a price increase\n- At $45, estimated monthly revenue increases by $63 with minimal volume impact\n- Competitors price similar scarves at $42-$55\n\nAction: Increase price to $45 on the next restock cycle.",
            "overall_quality": 83, "confidence": 0.81, "status": "approved", "hours_ago": 20,
        },
    ]

    for d in approved_deliverables:
        deliv = AgentDeliverable(
            id=nid(), shop_id=shop.id,
            agent_type=d["agent_type"], deliverable_type=d["deliverable_type"],
            title=d["title"], content=d["content"],
            overall_quality=d["overall_quality"], confidence=d.get("confidence", 0.8),
            status=d["status"], source="internal",
            approved_at=today_dt - timedelta(hours=d["hours_ago"]) if d["status"] == "approved" else None,
            created_at=today_dt - timedelta(hours=d["hours_ago"]),
        )
        db.add(deliv)

    # ── Pending Approval Items (5 items in the queue) ──
    pending_deliverables = [
        {
            "agent_type": "maya", "deliverable_type": "social_post",
            "title": "Monday Motivation: Start Your Week in Style",
            "content": "Start your week right! Our Denim Jacket ($89) pairs perfectly with literally everything. Layer it over a tee, dress it up with a scarf — it's the one piece you need this season.\n\n#MondayMotivation #DenimJacket #UrbanThreads #PortlandStyle",
            "overall_quality": 86, "confidence": 0.86, "hours_ago": 1,
        },
        {
            "agent_type": "emma", "deliverable_type": "winback_email",
            "title": "Win-Back: Lisa Park — 78 days inactive",
            "content": "Subject: Lisa, we have something special for you\n\nHi Lisa,\n\nWe've missed seeing you at Urban Threads! Your favorite Yoga Leggings have been restocked, plus we've added some amazing new activewear.\n\nHere's 25% off your next visit — our way of saying we'd love to see you back:\n\nCode: MISSYOU25\nValid for 5 days\n\nHope to see you soon!\nUrban Threads Team",
            "overall_quality": 89, "confidence": 0.87, "hours_ago": 2,
        },
        {
            "agent_type": "scout", "deliverable_type": "competitor_report",
            "title": "Fresh Kicks Launching New Product Line",
            "content": "Fresh Kicks announced a new 'Urban Athletics' line on their Instagram. This is their first expansion into casual streetwear, directly competing with your hoodie and t-shirt categories.\n\nRecommended response:\n1. Differentiate on quality and local brand story\n2. Consider a 'Local > Chain' social media campaign\n3. Bundle your best-selling streetwear items at a slight discount\n\nUrgency: Medium — their launch is in 2 weeks.",
            "overall_quality": 84, "confidence": 0.82, "hours_ago": 3,
        },
        {
            "agent_type": "max", "deliverable_type": "bundle_suggestion",
            "title": "Cross-Sell: Sundress + Crossbody Purse Summer Set",
            "content": "Bundle: Floral Sundress ($72) + Crossbody Purse ($58)\n\nSuggested bundle price: $115 (11% discount)\nEstimated margin: 48%\n\n28% of sundress buyers browse accessories. This bundle could drive an additional $280/month in revenue.",
            "overall_quality": 81, "confidence": 0.79, "hours_ago": 4,
        },
        {
            "agent_type": "alex", "deliverable_type": "strategy_memo",
            "title": "Q1 Mid-Quarter Review: On Track but Watch Cash Flow",
            "content": "Mid-quarter strategy assessment:\n\nPositive:\n- Revenue tracking at 103% of target\n- Customer acquisition up 8% MoM\n- Social engagement growing steadily\n\nConcerns:\n- Inventory costs up 12% — review vendor pricing\n- Cash flow tight in weeks 3-4 of each month\n- Two product categories underperforming (stationery, decor)\n\nRecommendation: Negotiate better terms with top 3 vendors. Consider clearance sale on underperforming categories.",
            "overall_quality": 91, "confidence": 0.89, "hours_ago": 5,
        },
    ]

    for d in pending_deliverables:
        deliv = AgentDeliverable(
            id=nid(), shop_id=shop.id,
            agent_type=d["agent_type"], deliverable_type=d["deliverable_type"],
            title=d["title"], content=d["content"],
            overall_quality=d["overall_quality"], confidence=d.get("confidence", 0.8),
            status="pending_approval", source="internal",
            created_at=today_dt - timedelta(hours=d["hours_ago"]),
        )
        db.add(deliv)

    # ── Audit Log entries ──
    audit_entries = [
        ("claw_bot", "goal_started", "goal", None, {"title": "Monthly Revenue Target"}, -24),
        ("maya", "deliverable_created", "deliverable", None, {"title": "Weekend Vibes at Urban Threads", "quality_score": 88}, -6),
        ("maya", "deliverable_created", "deliverable", None, {"title": "New Arrivals Alert", "quality_score": 85}, -18),
        ("scout", "deliverable_created", "deliverable", None, {"title": "Style Hub Rating Drops", "quality_score": 90}, -12),
        ("emma", "deliverable_created", "deliverable", None, {"title": "Win-Back: Sarah Johnson", "quality_score": 91}, -8),
        ("alex", "deliverable_created", "deliverable", None, {"title": "Daily Briefing", "quality_score": 94}, -2),
        ("max", "deliverable_created", "deliverable", None, {"title": "Hoodie + Beanie Bundle", "quality_score": 87}, -14),
        ("user", "deliverable_approved", "deliverable", None, {"title": "Weekend Vibes at Urban Threads"}, -5),
        ("user", "deliverable_approved", "deliverable", None, {"title": "Style Hub Rating Drops"}, -11),
        ("system", "agent_executed", "agent", None, {"agent": "maya", "trigger": "scheduled"}, -6),
        ("system", "agent_executed", "agent", None, {"agent": "alex", "trigger": "scheduled"}, -2),
    ]
    for actor, action, rtype, rid, details, hours_offset in audit_entries:
        db.add(AuditLog(
            id=nid(), shop_id=shop.id,
            actor=actor, action=action, resource_type=rtype, resource_id=rid,
            details=details, created_at=today_dt + timedelta(hours=hours_offset),
        ))

    # ── Sent Email log ──
    db.add(SentEmail(
        id=nid(), shop_id=shop.id, to_email="sarah@example.com",
        subject="We miss you at Urban Threads!", body_preview="Hi Sarah, it's been a while...",
        template="marketing", status="sent", sent_by="emma",
        created_at=today_dt - timedelta(days=3),
    ))

    db.commit()
    db.close()

    print()
    print("=" * 60)
    print("  Mock data generated successfully!")
    print("=" * 60)
    print(f"  Email:        {DEMO_EMAIL}")
    print(f"  Password:     {DEMO_PASSWORD}")
    print(f"  Shop:         {SHOP_NAME}")
    print(f"  Days:         {DAYS}")
    print(f"  Transactions: {total_tx}")
    print(f"  Avg daily:    ${avg_daily:,.0f}")
    print(f"  Avg monthly:  ${avg_monthly:,.0f}")
    print(f"  Products:     {len(PRODUCTS)}")
    print(f"  Customers:    500 (VIP={seg_counts['vip']}, Regular={seg_counts['regular']}, "
          f"At-risk={seg_counts['at_risk']}, Lost={seg_counts['lost']})")
    print(f"  Reviews:      55 (own) + ~180 (competitors)")
    print(f"  Competitors:  {len(COMPETITORS)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
