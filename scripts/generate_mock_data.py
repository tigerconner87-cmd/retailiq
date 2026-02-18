"""Generate 180 days of realistic mock data for RetailIQ demo.

Features:
- 180 days of transaction history with seasonal patterns
- 35 products across categories with realistic pricing
- 500+ unique customers with segment distributions
- 55 Google reviews with realistic text and sentiment
- 8 competitors with varying ratings and review histories
- Day-of-week patterns (weekends busier)
- Time-of-day patterns (lunch and after-work peaks)
- Seasonal patterns (Nov-Dec holiday boost)
- Anomaly days (unusually high or low sales)
- Progressive growth trend
- Expenses, goals, marketing campaigns

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
    Alert, Competitor, CompetitorReview, CompetitorSnapshot, Customer,
    DailySnapshot, Expense, HourlySnapshot, MarketingCampaign, Product,
    Recommendation, Review, RevenueGoal, Shop, ShopSettings,
    Transaction, TransactionItem, User,
)
from app.services.auth import hash_password

random.seed(42)

# ── Configuration ─────────────────────────────────────────────────────────────

DEMO_EMAIL = "demo@retailiq.com"
DEMO_PASSWORD = "demo1234"
DEMO_NAME = "Alex Demo"
SHOP_NAME = "Urban Threads Boutique"
DAYS = 180

PRODUCTS = [
    # (name, category, price, cost, sku, stock)
    ("Organic Cotton T-Shirt", "Apparel", 29.99, 12.00, "APP-001", 85),
    ("Slim Fit Jeans", "Apparel", 59.99, 22.00, "APP-002", 45),
    ("Cotton Hoodie", "Apparel", 54.99, 20.00, "APP-003", 38),
    ("Linen Summer Dress", "Apparel", 64.99, 24.00, "APP-004", 30),
    ("Vintage Denim Jacket", "Apparel", 79.99, 28.00, "APP-005", 22),
    ("Beanie Hat", "Apparel", 19.99, 6.00, "APP-006", 60),
    ("Wool Blend Sweater", "Apparel", 49.99, 18.00, "APP-007", 35),
    ("Canvas Tote Bag", "Accessories", 24.99, 8.00, "ACC-001", 70),
    ("Bamboo Sunglasses", "Accessories", 34.99, 11.00, "ACC-002", 55),
    ("Linen Scarf", "Accessories", 22.99, 7.00, "ACC-003", 48),
    ("Leather Wallet", "Accessories", 44.99, 15.00, "ACC-004", 40),
    ("Enamel Pin Set", "Accessories", 9.99, 2.50, "ACC-005", 120),
    ("Silver Pendant Necklace", "Accessories", 38.99, 12.00, "ACC-006", 32),
    ("Woven Belt", "Accessories", 27.99, 9.00, "ACC-007", 42),
    ("Ceramic Travel Mug", "Home", 18.99, 6.50, "HOM-001", 65),
    ("Soy Candle Set", "Home", 27.99, 9.00, "HOM-002", 50),
    ("Reusable Water Bottle", "Home", 21.99, 7.00, "HOM-003", 55),
    ("Linen Apron", "Home", 32.99, 11.00, "HOM-004", 28),
    ("Macrame Plant Hanger", "Home", 26.99, 8.50, "HOM-005", 35),
    ("Scented Diffuser", "Home", 34.99, 11.00, "HOM-006", 30),
    ("Recycled Notebook", "Stationery", 12.99, 3.50, "STA-001", 90),
    ("Brush Pen Set", "Stationery", 16.99, 5.00, "STA-002", 75),
    ("Washi Tape Collection", "Stationery", 8.99, 2.80, "STA-003", 100),
    ("Leather Journal", "Stationery", 28.99, 9.50, "STA-004", 40),
    ("Sticker Pack", "Stationery", 6.99, 1.50, "STA-005", 150),
    ("Graphic Print Poster", "Decor", 16.99, 4.00, "DEC-001", 45),
    ("Handmade Coasters (4pk)", "Decor", 14.99, 4.50, "DEC-002", 55),
    ("Photo Frame (5x7)", "Decor", 19.99, 6.00, "DEC-003", 40),
    ("Artisan Soap Bar", "Beauty", 8.99, 2.50, "BEA-001", 80),
    ("Hand Cream Duo", "Beauty", 18.99, 5.50, "BEA-002", 60),
    ("Lip Balm Set", "Beauty", 11.99, 3.00, "BEA-003", 90),
    ("Essential Oil Blend", "Beauty", 22.99, 7.00, "BEA-004", 45),
    ("Lavender Bath Salts", "Beauty", 15.99, 4.50, "BEA-005", 50),
    ("Gift Card $25", "Gift Cards", 25.00, 0, "GFT-025", 999),
    ("Gift Card $50", "Gift Cards", 50.00, 0, "GFT-050", 999),
]

# Product popularity weights (higher = more likely to sell)
PRODUCT_WEIGHTS = [
    14, 11, 9, 7, 8, 6, 5,  # Apparel
    8, 6, 5, 5, 7, 4, 3,    # Accessories
    7, 5, 6, 3, 3, 3,       # Home
    6, 4, 5, 3, 4,          # Stationery
    3, 3, 2,                 # Decor
    5, 4, 4, 3, 3,          # Beauty
    2, 1,                    # Gift Cards
]

COMPETITORS = [
    ("The Corner Store", "123 Main St", "retail", 4.2, 187),
    ("City Goods Co", "456 Oak Ave", "retail", 3.9, 94),
    ("Market Square Boutique", "789 Elm Blvd", "boutique", 4.5, 256),
    ("Urban Supply Co", "321 Pine St", "retail", 4.0, 132),
    ("Neighborhood Finds", "654 Cedar Ln", "thrift", 3.7, 68),
    ("Style Hub", "222 Birch Rd", "boutique", 4.3, 201),
    ("The Crafted Home", "888 Willow Way", "home goods", 4.1, 148),
    ("Vintage Collective", "555 Maple Dr", "vintage", 4.4, 175),
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
]

COMPETITOR_NEUTRAL_REVIEWS = [
    "It's okay. Nothing special but decent enough for the area.",
    "Average shop. Some good items, some meh. Prices are fair.",
]

COMPETITOR_NEGATIVE_REVIEWS = [
    "Terrible customer service. Staff was rude and unhelpful.",
    "Very overpriced. Found the same products for half the price online.",
    "Dirty store, broken shelving. They really need to clean up.",
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
    """Returns a multiplier for seasonal patterns. Nov-Dec gets holiday boost."""
    month = d.month
    factors = {
        1: 0.85, 2: 0.88, 3: 0.92, 4: 0.95, 5: 1.0,
        6: 1.05, 7: 1.02, 8: 0.98, 9: 0.95, 10: 1.0,
        11: 1.15, 12: 1.35,
    }
    base = factors.get(month, 1.0)
    # Extra boost around Black Friday (last week of Nov)
    if month == 11 and d.day >= 23:
        base *= 1.3
    # Extra boost mid-December
    if month == 12 and 10 <= d.day <= 23:
        base *= 1.2
    # Dip around Christmas/New Year
    if month == 12 and d.day >= 26:
        base *= 0.6
    return base


def get_dow_factor(dow: int) -> float:
    """Day-of-week multiplier. 0=Mon, 6=Sun."""
    return {0: 0.75, 1: 0.82, 2: 0.90, 3: 0.95, 4: 1.15, 5: 1.35, 6: 1.05}[dow]


def get_hour_weights() -> list[float]:
    """Hourly weights for transaction distribution (9am-9pm)."""
    return [
        3, 5, 8, 12, 10, 7,   # 9-10, 10-11, 11-12, 12-1, 1-2, 2-3
        5, 6, 9, 11, 8, 4,    # 3-4, 4-5, 5-6, 6-7, 7-8, 8-9
    ]


def is_anomaly_day(d: date) -> tuple[bool, float]:
    """Check if this day should be an anomaly. Returns (is_anomaly, factor)."""
    random.seed(d.toordinal())
    r = random.random()
    random.seed(42 + d.toordinal())

    if r < 0.02:  # 2% chance of very high day
        return True, random.uniform(1.6, 2.0)
    elif r < 0.04:  # 2% chance of very low day
        return True, random.uniform(0.3, 0.5)
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
        monthly_rent=Decimal("3200"), avg_cogs_percentage=38.0,
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

    # Create customers with segment distribution
    print("Creating 500 customers...")
    today = date.today()
    start_date = today - timedelta(days=DAYS)
    customer_pool = []

    for i in range(500):
        first_day = start_date + timedelta(days=random.randint(0, DAYS - 10))
        # Assign segments: 10% VIP, 50% regular, 25% at-risk, 15% lost
        r = random.random()
        if r < 0.10:
            segment = "vip"
        elif r < 0.60:
            segment = "regular"
        elif r < 0.85:
            segment = "at_risk"
        else:
            segment = "lost"

        c = Customer(
            id=nid(), shop_id=shop.id, external_id=f"sq-cust-{i+1:04d}",
            email=f"customer{i+1}@example.com" if random.random() > 0.3 else None,
            segment=segment,
            first_seen=datetime.combine(first_day, datetime.min.time()),
            last_seen=datetime.combine(first_day, datetime.min.time()),
            visit_count=0, total_spent=Decimal("0"),
        )
        db.add(c)
        customer_pool.append(c)
    db.flush()

    # Generate transactions
    print(f"Generating {DAYS} days of transactions...")
    daily_data = defaultdict(lambda: {
        "revenue": Decimal("0"), "cost": Decimal("0"), "tx_count": 0, "items_sold": 0,
        "customers": set(), "new_customers": set(),
        "hourly": defaultdict(lambda: {"rev": Decimal("0"), "count": 0}),
    })

    seen_customers = set()
    total_tx = 0
    hour_weights = get_hour_weights()

    # Seed for reproducibility of anomalies
    random.seed(42)

    current_date = start_date
    while current_date <= today:
        dow = current_date.weekday()
        day_offset = (current_date - start_date).days

        # Calculate multipliers
        growth_factor = 1.0 + day_offset * 0.0015  # Gradual growth
        seasonal = get_seasonal_factor(current_date)
        dow_factor = get_dow_factor(dow)
        is_anom, anom_factor = is_anomaly_day(current_date)

        # Base transactions per day
        base_count = 52
        tx_count = int(base_count * growth_factor * seasonal * dow_factor * anom_factor)
        tx_count += random.randint(-5, 5)
        tx_count = max(8, tx_count)

        for _ in range(tx_count):
            hour = random.choices(range(9, 21), weights=hour_weights)[0]
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            ts = datetime(current_date.year, current_date.month, current_date.day, hour, minute, second)

            # Pick customer: 25% anonymous, 75% tracked
            customer = None
            if random.random() > 0.25:
                # VIP customers shop more frequently
                if random.random() < 0.3:
                    vips = [c for c in customer_pool if c.segment == "vip" and c.first_seen and ts >= c.first_seen]
                    if vips:
                        customer = random.choice(vips)
                if not customer:
                    eligible = [c for c in customer_pool if c.first_seen and ts >= c.first_seen]
                    if eligible:
                        customer = random.choice(eligible)

            # Pick items
            num_items = random.choices([1, 2, 3, 4, 5], weights=[38, 30, 20, 9, 3])[0]
            chosen_products = random.choices(product_objs, weights=PRODUCT_WEIGHTS, k=num_items)

            subtotal = Decimal("0")
            total_cost = Decimal("0")
            items_data = []
            for prod in chosen_products:
                qty = random.choices([1, 2, 3], weights=[72, 22, 6])[0]
                line_total = prod.price * qty
                subtotal += line_total
                if prod.cost:
                    total_cost += prod.cost * qty
                items_data.append((prod, qty, line_total))

            # Occasional discounts (10% of transactions)
            discount = Decimal("0")
            if random.random() < 0.10:
                discount = (subtotal * Decimal(str(random.choice([0.10, 0.15, 0.20])))).quantize(Decimal("0.01"))
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

        current_date += timedelta(days=1)

        if (current_date - start_date).days % 15 == 0:
            db.flush()

    db.flush()
    print(f"  Generated {total_tx} transactions")

    # Update customer segments based on actual behavior
    print("Updating customer segments...")
    for c in customer_pool:
        if c.visit_count == 0:
            c.segment = "lost"
            continue
        if c.last_seen:
            days_since = (datetime.combine(today, datetime.min.time()) - c.last_seen).days
            if c.total_spent and float(c.total_spent) > 500 and c.visit_count >= 5:
                c.segment = "vip"
            elif days_since > 60:
                c.segment = "lost"
            elif days_since > 30:
                c.segment = "at_risk"
            else:
                c.segment = "regular"
            # Calculate avg days between visits
            if c.visit_count > 1 and c.first_seen and c.last_seen:
                total_days = (c.last_seen - c.first_seen).days
                c.avg_days_between_visits = round(total_days / (c.visit_count - 1), 1) if c.visit_count > 1 else None
    db.flush()

    # Create snapshots
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

    # Create reviews for own shop
    print("Creating 55 reviews...")
    for i in range(55):
        days_ago = random.randint(0, 300)
        rating = random.choices([1, 2, 3, 4, 5], weights=[4, 5, 10, 28, 53])[0]
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

    # Create competitors with reviews
    print(f"Creating {len(COMPETITORS)} competitors...")
    for name, address, category, rating, review_count in COMPETITORS:
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

        # Competitor snapshots (weekly for past 6 months)
        for w in range(26):
            snap_date = today - timedelta(weeks=w)
            drift = random.uniform(-0.3, 0.3)
            snap_reviews = review_count - w * random.randint(1, 4)
            cs = CompetitorSnapshot(
                id=nid(), competitor_id=comp.id, date=snap_date,
                rating=Decimal(str(round(max(1.0, min(5.0, rating + drift)), 1))),
                review_count=max(10, snap_reviews),
            )
            db.add(cs)

        # Competitor reviews (8-15 per competitor)
        num_comp_reviews = random.randint(8, 15)
        for j in range(num_comp_reviews):
            days_ago = random.randint(0, 180)
            cr_rating = random.choices([1, 2, 3, 4, 5], weights=[5, 8, 15, 35, 37])[0]
            if cr_rating >= 4:
                cr_text = random.choice(COMPETITOR_POSITIVE_REVIEWS)
            elif cr_rating <= 2:
                cr_text = random.choice(COMPETITOR_NEGATIVE_REVIEWS)
            else:
                cr_text = random.choice(COMPETITOR_NEUTRAL_REVIEWS)

            cr = CompetitorReview(
                id=nid(), competitor_id=comp.id,
                author_name=random.choice(REVIEWER_NAMES),
                rating=cr_rating, text=cr_text,
                review_date=datetime.now() - timedelta(days=days_ago),
                sentiment=classify_sentiment(cr_text, cr_rating),
            )
            db.add(cr)

    # Create expenses
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

    # Create revenue goals for recent months
    print("Creating revenue goals...")
    for m_offset in range(6):
        goal_month = today.replace(day=1) - timedelta(days=30 * m_offset)
        goal_str = goal_month.strftime("%Y-%m")
        target = 38000 + m_offset * 500  # Increasing goals
        rg = RevenueGoal(
            id=nid(), shop_id=shop.id, month=goal_str,
            target_amount=Decimal(str(target)),
        )
        db.add(rg)

    # Create marketing campaigns
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

    # Create alerts
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
         "You've hit $27,360 of your $38,000 goal. You need $1,330/day to hit target."),
        ("revenue_milestone", "success", "revenue", "Best Saturday ever: $4,230 in revenue!",
         "Last Saturday was your highest revenue day ever, beating the previous record by 12%."),
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

    db.commit()
    db.close()

    print()
    print("=" * 60)
    print("  Mock data generated successfully!")
    print("=" * 60)
    print(f"  Email:       {DEMO_EMAIL}")
    print(f"  Password:    {DEMO_PASSWORD}")
    print(f"  Shop:        {SHOP_NAME}")
    print(f"  Days:        {DAYS}")
    print(f"  Transactions: {total_tx}")
    print(f"  Products:    {len(PRODUCTS)}")
    print(f"  Customers:   500")
    print(f"  Reviews:     55 (own) + ~80 (competitors)")
    print(f"  Competitors: {len(COMPETITORS)}")
    print(f"  Expenses:    {len(expenses_data)}")
    print(f"  Campaigns:   {len(campaigns)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
