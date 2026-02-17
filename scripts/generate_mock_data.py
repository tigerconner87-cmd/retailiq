"""Generate 90 days of realistic mock data for RetailIQ demo.

Run:  python -m scripts.generate_mock_data
"""

import random
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import (
    Alert, Competitor, CompetitorSnapshot, Customer, DailySnapshot,
    HourlySnapshot, Product, Review, Shop, Transaction, TransactionItem, User,
)
from app.services.auth import hash_password
from app.services.reviews import classify_sentiment

random.seed(42)

# ── Configuration ─────────────────────────────────────────────────────────────

DEMO_EMAIL = "demo@retailiq.com"
DEMO_PASSWORD = "demo1234"
DEMO_NAME = "Alex Demo"
SHOP_NAME = "Urban Threads Boutique"
DAYS = 90

PRODUCTS = [
    ("Organic Cotton T-Shirt", "Apparel", 29.99, 12.00),
    ("Slim Fit Jeans", "Apparel", 59.99, 22.00),
    ("Canvas Tote Bag", "Accessories", 24.99, 8.00),
    ("Ceramic Travel Mug", "Home", 18.99, 6.50),
    ("Bamboo Sunglasses", "Accessories", 34.99, 11.00),
    ("Linen Scarf", "Accessories", 22.99, 7.00),
    ("Recycled Notebook", "Stationery", 12.99, 3.50),
    ("Soy Candle Set", "Home", 27.99, 9.00),
    ("Leather Wallet", "Accessories", 44.99, 15.00),
    ("Cotton Hoodie", "Apparel", 54.99, 20.00),
    ("Enamel Pin Set", "Accessories", 9.99, 2.50),
    ("Reusable Water Bottle", "Home", 21.99, 7.00),
    ("Graphic Print Poster", "Decor", 16.99, 4.00),
    ("Linen Apron", "Home", 32.99, 11.00),
    ("Beanie Hat", "Apparel", 19.99, 6.00),
]

PRODUCT_WEIGHTS = [12, 10, 8, 7, 6, 5, 5, 5, 4, 4, 3, 3, 3, 2, 2]

COMPETITORS = [
    ("The Corner Store", "123 Main St", 4.2, 187),
    ("City Goods", "456 Oak Ave", 3.9, 94),
    ("Market Square", "789 Elm Blvd", 4.5, 256),
    ("Urban Supply Co", "321 Pine St", 4.0, 132),
    ("Neighborhood Finds", "654 Cedar Ln", 3.7, 68),
]

REVIEWER_NAMES = [
    "Alex M.", "Jordan T.", "Chris L.", "Sam P.", "Taylor R.",
    "Morgan K.", "Casey W.", "Riley B.", "Drew N.", "Jamie S.",
    "Pat H.", "Quinn D.", "Avery F.", "Blake G.", "Dakota J.",
    "Frankie V.", "Hayden C.", "Jules A.", "Kendall O.", "Logan E.",
]

POSITIVE_REVIEWS = [
    "Love this shop! Great selection and the staff is always helpful.",
    "My favorite local boutique. Unique finds every visit!",
    "Amazing quality products. Worth every penny.",
    "Such a cute store with great vibes. Bought gifts for everyone!",
    "Best accessories selection in the area. Always my first stop.",
    "Friendly staff, beautiful store. Keep up the great work!",
    "Discovered this gem last month. Already been back three times!",
]

NEUTRAL_REVIEWS = [
    "Decent shop. Some nice things but prices are a bit high.",
    "Good selection but the store could be better organized.",
    "Nice products. Nothing super unique though.",
]

NEGATIVE_REVIEWS = [
    "Waited 10 minutes and nobody offered to help. Disappointing.",
    "Prices don't match the quality. Found similar items cheaper elsewhere.",
    "Very limited hours. Came by twice and they were closed.",
]


def nid():
    return str(uuid.uuid4())


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # Clean existing demo data
    existing = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if existing:
        print("Removing existing demo data...")
        shops = db.query(Shop).filter(Shop.user_id == existing.id).all()
        for shop in shops:
            db.query(Alert).filter(Alert.shop_id == shop.id).delete()
            db.query(Review).filter(Review.shop_id == shop.id).delete()
            comps = db.query(Competitor).filter(Competitor.shop_id == shop.id).all()
            for c in comps:
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
        full_name=DEMO_NAME, plan_tier="growth",
    )
    db.add(user)
    db.flush()

    shop = Shop(
        id=nid(), user_id=user.id, name=SHOP_NAME, pos_system="square",
        address="742 Evergreen Terrace, Portland, OR 97201",
        latitude=45.5152, longitude=-122.6784,
        google_place_id="mock-place-own-001",
    )
    db.add(shop)
    db.flush()

    # Create products
    print("Creating products...")
    product_objs = []
    for name, category, price, cost in PRODUCTS:
        p = Product(
            id=nid(), shop_id=shop.id, external_id=f"sq-{name[:3].lower()}-{random.randint(100,999)}",
            name=name, category=category, price=Decimal(str(price)), cost=Decimal(str(cost)),
        )
        db.add(p)
        product_objs.append(p)
    db.flush()

    # Create customers
    print("Creating customers...")
    today = date.today()
    start_date = today - timedelta(days=DAYS)
    customer_pool = []
    for i in range(200):
        first_day = start_date + timedelta(days=random.randint(0, DAYS - 10))
        c = Customer(
            id=nid(), shop_id=shop.id, external_id=f"sq-cust-{i+1:04d}",
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
        "revenue": Decimal("0"), "tx_count": 0,
        "customers": set(), "new_customers": set(), "hourly": defaultdict(lambda: {"rev": Decimal("0"), "count": 0}),
    })

    # Track which customers have been seen
    seen_customers = set()
    total_tx = 0

    current_date = start_date
    while current_date <= today:
        dow = current_date.weekday()
        # Progressive growth: slight upward trend over 90 days
        day_offset = (current_date - start_date).days
        growth_factor = 1.0 + day_offset * 0.002

        base_count = {0: 38, 1: 42, 2: 48, 3: 50, 4: 65, 5: 85, 6: 58}[dow]
        tx_count = int(base_count * growth_factor) + random.randint(-8, 8)

        for _ in range(tx_count):
            # Pick hour weighted toward lunch and evening
            hour = random.choices(
                range(9, 21),
                weights=[3, 5, 8, 10, 9, 6, 4, 5, 7, 8, 6, 3],
            )[0]
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            ts = datetime(current_date.year, current_date.month, current_date.day, hour, minute, second)

            # Pick customer (30% anonymous, 70% tracked)
            customer = None
            if random.random() > 0.30:
                customer = random.choice(customer_pool)
                if customer.first_seen and datetime.combine(current_date, datetime.min.time()) < customer.first_seen:
                    customer = None

            # Pick items
            num_items = random.choices([1, 2, 3, 4], weights=[42, 32, 19, 7])[0]
            chosen_products = random.choices(product_objs, weights=PRODUCT_WEIGHTS, k=num_items)

            subtotal = Decimal("0")
            items_data = []
            for prod in chosen_products:
                qty = random.choices([1, 2, 3], weights=[75, 20, 5])[0]
                line_total = prod.price * qty
                subtotal += line_total
                items_data.append((prod, qty, line_total))

            tax = (subtotal * Decimal("0.0825")).quantize(Decimal("0.01"))
            total = subtotal + tax

            tx = Transaction(
                id=nid(), shop_id=shop.id,
                external_id=f"sq-tx-{current_date.isoformat()}-{total_tx:06d}",
                customer_id=customer.id if customer else None,
                subtotal=subtotal, tax=tax, total=total,
                items_count=len(items_data), timestamp=ts,
            )
            db.add(tx)
            db.flush()

            for prod, qty, line_total in items_data:
                ti = TransactionItem(
                    id=nid(), transaction_id=tx.id, product_id=prod.id,
                    quantity=qty, unit_price=prod.price, total=line_total,
                )
                db.add(ti)

            # Update customer
            if customer:
                customer.visit_count += 1
                customer.total_spent += total
                customer.last_seen = ts
                daily_data[current_date]["customers"].add(customer.id)
                if customer.id not in seen_customers:
                    seen_customers.add(customer.id)
                    daily_data[current_date]["new_customers"].add(customer.id)

            # Update daily stats
            daily_data[current_date]["revenue"] += total
            daily_data[current_date]["tx_count"] += 1
            daily_data[current_date]["hourly"][hour]["rev"] += total
            daily_data[current_date]["hourly"][hour]["count"] += 1

            total_tx += 1

        current_date += timedelta(days=1)

        # Commit every 10 days to avoid OOM
        if (current_date - start_date).days % 10 == 0:
            db.flush()

    db.flush()
    print(f"  Generated {total_tx} transactions")

    # Create snapshots
    print("Creating daily and hourly snapshots...")
    for d, data in daily_data.items():
        unique = len(data["customers"])
        new = len(data["new_customers"])
        repeat = unique - new
        avg_tv = data["revenue"] / data["tx_count"] if data["tx_count"] > 0 else Decimal("0")

        ds = DailySnapshot(
            id=nid(), shop_id=shop.id, date=d,
            total_revenue=data["revenue"], transaction_count=data["tx_count"],
            avg_transaction_value=avg_tv.quantize(Decimal("0.01")),
            unique_customers=unique, repeat_customers=max(0, repeat), new_customers=new,
        )
        db.add(ds)

        for hour, hdata in data["hourly"].items():
            hs = HourlySnapshot(
                id=nid(), shop_id=shop.id, date=d, hour=hour,
                revenue=hdata["rev"], transaction_count=hdata["count"],
            )
            db.add(hs)

    # Create reviews
    print("Creating reviews...")
    for i in range(25):
        days_ago = random.randint(0, 180)
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

    # Create competitors
    print("Creating competitors...")
    for name, address, rating, review_count in COMPETITORS:
        comp = Competitor(
            id=nid(), shop_id=shop.id, name=name,
            google_place_id=f"mock-comp-{name[:4].lower()}", address=address,
            rating=Decimal(str(rating)), review_count=review_count,
            latitude=45.5152 + random.uniform(-0.02, 0.02),
            longitude=-122.6784 + random.uniform(-0.02, 0.02),
        )
        db.add(comp)
        db.flush()

        # Competitor snapshots (weekly for past 90 days)
        for w in range(13):
            snap_date = today - timedelta(weeks=w)
            drift = random.uniform(-0.2, 0.2)
            snap_reviews = review_count - w * random.randint(1, 5)
            cs = CompetitorSnapshot(
                id=nid(), competitor_id=comp.id, date=snap_date,
                rating=Decimal(str(round(rating + drift, 1))),
                review_count=max(10, snap_reviews),
            )
            db.add(cs)

    # Create alerts
    print("Creating alerts...")
    alerts_data = [
        ("revenue_drop", "critical", "Revenue dropped 23% this week",
         "This week's revenue is down 23% compared to last week ($6,420 vs $8,340). Consider running a promotion."),
        ("negative_review", "warning", "New 1-star Google review",
         '"Waited 10 minutes and nobody offered to help." — Alex M., 1 star'),
        ("return_rate_drop", "warning", "Customer return rate below target",
         "Only 28.3% of customers are returning. Industry average is 30-40%. Consider a loyalty program."),
        ("revenue_drop", "info", "Monday revenue was lower than average",
         "Monday generated $1,847 which is 12% below your Monday average of $2,099."),
    ]
    for i, (atype, severity, title, message) in enumerate(alerts_data):
        a = Alert(
            id=nid(), shop_id=shop.id, alert_type=atype, severity=severity,
            title=title, message=message, is_read=(i > 1),
            created_at=datetime.now() - timedelta(days=i, hours=random.randint(0, 12)),
        )
        db.add(a)

    db.commit()
    db.close()

    print()
    print("=" * 50)
    print("  Mock data generated successfully!")
    print("=" * 50)
    print(f"  Email:    {DEMO_EMAIL}")
    print(f"  Password: {DEMO_PASSWORD}")
    print(f"  Shop:     {SHOP_NAME}")
    print(f"  Days:     {DAYS}")
    print(f"  Transactions: {total_tx}")
    print(f"  Products: {len(PRODUCTS)}")
    print(f"  Customers: 200")
    print(f"  Reviews:  25")
    print(f"  Competitors: {len(COMPETITORS)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
