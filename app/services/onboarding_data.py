"""Generate starter mock data for newly registered users based on their onboarding info."""

import random
from datetime import datetime, timedelta, date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    new_id, Shop, ShopSettings, Product, Customer, Transaction, TransactionItem,
    DailySnapshot, HourlySnapshot, Review, Competitor, CompetitorReview,
    Alert, Goal, ProductGoal, RevenueGoal, StrategyNote,
)

# Product catalogs by shop type
PRODUCT_CATALOGS = {
    "boutique": [
        ("Vintage Denim Jacket", "Apparel", 89.99, 38),
        ("Linen Wrap Dress", "Apparel", 68.00, 32),
        ("Silk Scarf", "Accessories", 34.99, 25),
        ("Leather Tote Bag", "Accessories", 120.00, 45),
        ("Statement Earrings", "Jewelry", 28.00, 15),
        ("Cotton Blouse", "Apparel", 45.00, 22),
        ("Wide-Brim Hat", "Accessories", 42.00, 18),
        ("Knit Cardigan", "Apparel", 58.00, 28),
        ("Beaded Necklace", "Jewelry", 36.00, 12),
        ("Canvas Sneakers", "Footwear", 55.00, 24),
        ("Printed T-Shirt", "Apparel", 25.00, 10),
        ("Enamel Pin Set", "Accessories", 12.00, 4),
        ("Soy Candle", "Home", 18.00, 6),
        ("Reusable Tote", "Accessories", 15.00, 5),
        ("Gift Card $25", "Gift Cards", 25.00, 0),
    ],
    "clothing": [
        ("Classic Fit Jeans", "Denim", 69.99, 30),
        ("Graphic Hoodie", "Tops", 54.00, 24),
        ("Oxford Button-Down", "Tops", 48.00, 20),
        ("Chino Pants", "Bottoms", 55.00, 25),
        ("Crew Neck Tee", "Tops", 22.00, 8),
        ("Bomber Jacket", "Outerwear", 95.00, 42),
        ("Wool Beanie", "Accessories", 18.00, 6),
        ("Polo Shirt", "Tops", 38.00, 16),
        ("Cargo Shorts", "Bottoms", 42.00, 18),
        ("Denim Jacket", "Outerwear", 78.00, 35),
        ("V-Neck Sweater", "Tops", 52.00, 24),
        ("Slim Fit Blazer", "Formal", 125.00, 55),
        ("Leather Belt", "Accessories", 32.00, 12),
        ("Ankle Socks 3-Pack", "Basics", 14.00, 4),
        ("Gift Card $50", "Gift Cards", 50.00, 0),
    ],
    "gift_shop": [
        ("Scented Candle", "Candles", 22.00, 8),
        ("Greeting Card Set", "Stationery", 12.00, 3),
        ("Ceramic Mug", "Drinkware", 16.00, 6),
        ("Picture Frame", "Decor", 24.00, 10),
        ("Essential Oil Diffuser", "Wellness", 38.00, 15),
        ("Plush Throw Blanket", "Home", 45.00, 20),
        ("Journal Notebook", "Stationery", 15.00, 5),
        ("Bath Bomb Set", "Wellness", 18.00, 6),
        ("Succulent Planter", "Decor", 28.00, 10),
        ("Artisan Soap", "Wellness", 9.00, 3),
        ("Wine Glasses Set", "Drinkware", 32.00, 12),
        ("Puzzle 500pc", "Games", 20.00, 8),
        ("Coaster Set", "Home", 14.00, 5),
        ("Tote Bag", "Bags", 18.00, 6),
        ("Gift Card $25", "Gift Cards", 25.00, 0),
    ],
    "home_goods": [
        ("Throw Pillow", "Textiles", 35.00, 14),
        ("Ceramic Vase", "Decor", 42.00, 18),
        ("Woven Basket", "Storage", 28.00, 10),
        ("Table Lamp", "Lighting", 65.00, 28),
        ("Cotton Towel Set", "Bath", 24.00, 8),
        ("Scented Candle Lg", "Candles", 32.00, 10),
        ("Wall Art Print", "Decor", 48.00, 15),
        ("Serving Board", "Kitchen", 38.00, 16),
        ("Linen Napkins 4pk", "Kitchen", 22.00, 7),
        ("Plant Pot", "Decor", 18.00, 6),
        ("Throw Blanket", "Textiles", 55.00, 22),
        ("Candle Holder", "Decor", 26.00, 10),
        ("Door Mat", "Home", 30.00, 12),
        ("Storage Bin", "Storage", 20.00, 8),
        ("Gift Card $50", "Gift Cards", 50.00, 0),
    ],
}

# Revenue ranges for scaling
REVENUE_RANGES = {
    "under_10k": (5000, 10000),
    "10k_25k": (10000, 25000),
    "25k_50k": (25000, 50000),
    "50k_100k": (50000, 100000),
    "100k_plus": (100000, 150000),
}

# Day-of-week traffic multipliers
DOW_FACTORS = {0: 0.75, 1: 0.82, 2: 0.90, 3: 0.95, 4: 1.15, 5: 1.35, 6: 1.05}

# Hour distribution (9am-8pm)
HOUR_WEIGHTS = {
    9: 3, 10: 5, 11: 7, 12: 10, 13: 8, 14: 6,
    15: 5, 16: 7, 17: 9, 18: 7, 19: 4, 20: 2,
}

FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn", "Avery",
    "Harper", "Peyton", "Blake", "Cameron", "Reese", "Dakota", "Emerson", "Finley",
    "Sage", "Rowan", "Charlie", "Parker", "Drew", "Jamie", "Skyler", "Hayden",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Lee", "Kim", "Patel", "Chen", "Nguyen", "Lopez",
]


def generate_starter_data(
    db: Session,
    shop: Shop,
    monthly_revenue: str = "10k_25k",
    revenue_target: float = 25000,
    competitor_names: list[str] = None,
    biggest_challenge: str = "all",
):
    """Generate 30 days of realistic starter data for a new shop."""
    rng = random.Random(hash(shop.id) % (2**31))
    nid = lambda: str(__import__("uuid").uuid4())

    rev_low, rev_high = REVENUE_RANGES.get(monthly_revenue, (10000, 25000))
    target_monthly_revenue = (rev_low + rev_high) / 2

    # --- Products ---
    catalog_key = shop.category if shop.category in PRODUCT_CATALOGS else "boutique"
    catalog = PRODUCT_CATALOGS.get(catalog_key, PRODUCT_CATALOGS["boutique"])

    products = []
    for name, cat, price, cost in catalog:
        p = Product(
            id=nid(), shop_id=shop.id, name=name, category=cat,
            price=Decimal(str(price)), cost=Decimal(str(cost)) if cost else None,
            sku=f"SKU-{rng.randint(1000,9999)}", stock_quantity=rng.randint(20, 200),
        )
        db.add(p)
        products.append(p)
    db.flush()

    # --- Shop Settings ---
    settings = ShopSettings(
        id=nid(), shop_id=shop.id,
        monthly_rent=Decimal(str(rng.randint(1500, 4000))),
        avg_cogs_percentage=38.0,
        staff_hourly_rate=Decimal("16.50"),
        tax_rate=8.25,
    )
    db.add(settings)

    # --- Customers ---
    num_customers = max(30, int(target_monthly_revenue / 250))
    customers = []
    today = datetime.utcnow().date()
    for i in range(num_customers):
        segment = rng.choices(["vip", "regular", "at_risk", "lost"], [8, 55, 25, 12])[0]
        first_seen = today - timedelta(days=rng.randint(1, 90))
        c = Customer(
            id=nid(), shop_id=shop.id,
            email=f"customer{i+1}@example.com" if rng.random() < 0.6 else None,
            segment=segment,
            first_seen=datetime.combine(first_seen, datetime.min.time()),
            last_seen=datetime.combine(today - timedelta(days=rng.randint(0, 20)), datetime.min.time()),
            visit_count=rng.randint(1, 12),
            total_spent=Decimal("0"), avg_order_value=Decimal("0"),
        )
        db.add(c)
        customers.append(c)
    db.flush()

    # --- Transactions (30 days) ---
    # Calculate daily targets
    daily_target_rev = target_monthly_revenue / 30
    product_weights = [float(p.price) for p in products]
    total_weight = sum(product_weights)
    product_probs = [w / total_weight for w in product_weights]

    hour_list = list(HOUR_WEIGHTS.keys())
    hour_probs_raw = [HOUR_WEIGHTS[h] for h in hour_list]
    hour_total = sum(hour_probs_raw)
    hour_probs = [w / hour_total for w in hour_probs_raw]

    all_transactions = []
    daily_data = {}  # date -> {rev, count, items, customers_set, hourly}

    for day_offset in range(30, 0, -1):
        d = today - timedelta(days=day_offset)
        dow = d.weekday()
        dow_mult = DOW_FACTORS.get(dow, 1.0)
        day_noise = rng.uniform(0.8, 1.2)
        day_rev_target = daily_target_rev * dow_mult * day_noise

        daily_data[d] = {"rev": Decimal("0"), "count": 0, "items": 0,
                         "customers": set(), "hourly": {}}

        accumulated_rev = 0
        avg_price = sum(float(p.price) for p in products) / len(products)
        approx_txns = max(5, int(day_rev_target / avg_price * 0.7))

        for _ in range(approx_txns):
            if accumulated_rev >= day_rev_target * 1.1:
                break

            hour = rng.choices(hour_list, hour_probs)[0]
            minute = rng.randint(0, 59)
            ts = datetime.combine(d, datetime.min.time()).replace(hour=hour, minute=minute)

            # Pick 1-3 items
            num_items = rng.choices([1, 2, 3], [60, 30, 10])[0]
            chosen = rng.choices(products, product_probs, k=num_items)

            items_list = []
            subtotal = Decimal("0")
            for prod in chosen:
                qty = 1
                item_total = prod.price * qty
                subtotal += item_total
                items_list.append((prod, qty, item_total))

            tax = (subtotal * Decimal("0.0825")).quantize(Decimal("0.01"))
            discount = Decimal("0")
            if rng.random() < 0.08:
                discount = (subtotal * Decimal(str(rng.randint(10, 20) / 100))).quantize(Decimal("0.01"))
            total = subtotal - discount + tax

            # Assign customer
            cust = rng.choice(customers) if rng.random() < 0.75 else None

            txn = Transaction(
                id=nid(), shop_id=shop.id,
                customer_id=cust.id if cust else None,
                subtotal=subtotal, tax=tax, discount=discount, total=total,
                items_count=num_items,
                payment_method=rng.choices(["card", "cash", "mobile"], [65, 25, 10])[0],
                timestamp=ts,
            )
            db.add(txn)

            for prod, qty, item_total in items_list:
                ti = TransactionItem(
                    id=nid(), transaction_id=txn.id, product_id=prod.id,
                    quantity=qty, unit_price=prod.price, total=item_total,
                )
                db.add(ti)

            accumulated_rev += float(total)
            daily_data[d]["rev"] += total
            daily_data[d]["count"] += 1
            daily_data[d]["items"] += num_items
            if cust:
                daily_data[d]["customers"].add(cust.id)
            daily_data[d]["hourly"].setdefault(hour, {"rev": Decimal("0"), "count": 0})
            daily_data[d]["hourly"][hour]["rev"] += total
            daily_data[d]["hourly"][hour]["count"] += 1

            all_transactions.append(txn)

    # --- Daily & Hourly Snapshots ---
    for d, dd in daily_data.items():
        atv = (dd["rev"] / dd["count"]).quantize(Decimal("0.01")) if dd["count"] > 0 else Decimal("0")
        ds = DailySnapshot(
            id=nid(), shop_id=shop.id, date=d,
            total_revenue=dd["rev"], transaction_count=dd["count"],
            avg_transaction_value=atv, items_sold=dd["items"],
            unique_customers=len(dd["customers"]),
            new_customers=max(0, len(dd["customers"]) - rng.randint(0, 3)),
            repeat_customers=rng.randint(0, max(1, len(dd["customers"]) // 3)),
        )
        db.add(ds)

        for hour, hd in dd["hourly"].items():
            hs = HourlySnapshot(
                id=nid(), shop_id=shop.id, date=d, hour=hour,
                revenue=hd["rev"], transaction_count=hd["count"],
            )
            db.add(hs)

    # --- Update customer totals ---
    for cust in customers:
        cust_txns = [t for t in all_transactions if t.customer_id == cust.id]
        if cust_txns:
            cust.total_spent = sum(t.total for t in cust_txns)
            cust.visit_count = len(cust_txns)
            cust.avg_order_value = (cust.total_spent / len(cust_txns)).quantize(Decimal("0.01"))
            cust.last_seen = max(t.timestamp for t in cust_txns)
            cust.first_seen = min(t.timestamp for t in cust_txns)

    # --- Reviews (own shop) ---
    review_texts_pos = [
        "Great selection and friendly staff! Will definitely be back.",
        "Love this shop! Found exactly what I was looking for.",
        "Best local shop in town. Quality products every time.",
        "Amazing customer service. They went above and beyond.",
        "Beautiful store with unique items you won't find anywhere else.",
    ]
    review_texts_neg = [
        "Limited hours made it hard to visit. Wish they were open later.",
        "Prices are a bit high for what you get.",
    ]

    for i in range(8):
        rating = rng.choices([5, 4, 3], [50, 35, 15])[0]
        r = Review(
            id=nid(), shop_id=shop.id, source="google",
            author_name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            rating=rating,
            text=rng.choice(review_texts_pos) if rating >= 4 else rng.choice(review_texts_neg),
            review_date=datetime.combine(today - timedelta(days=rng.randint(1, 60)), datetime.min.time()),
            sentiment="positive" if rating >= 4 else ("neutral" if rating == 3 else "negative"),
            is_own_shop=True,
        )
        db.add(r)

    # --- Competitors ---
    comp_names = [n.strip() for n in (competitor_names or []) if n.strip()]
    for comp_name in comp_names[:5]:
        comp_rating = Decimal(str(round(rng.uniform(3.2, 4.6), 1)))
        comp = Competitor(
            id=nid(), shop_id=shop.id, name=comp_name,
            rating=comp_rating, review_count=rng.randint(20, 150),
            category=shop.category,
        )
        db.add(comp)
        db.flush()

        # Add a few competitor reviews
        for j in range(rng.randint(5, 12)):
            cr_rating = rng.choices([5, 4, 3, 2, 1], [30, 30, 20, 12, 8])[0]
            cr = CompetitorReview(
                id=nid(), competitor_id=comp.id,
                author_name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                rating=cr_rating,
                text=rng.choice(review_texts_pos) if cr_rating >= 4 else "Could be better. Service was slow.",
                review_date=datetime.combine(today - timedelta(days=rng.randint(1, 90)), datetime.min.time()),
                sentiment="positive" if cr_rating >= 4 else ("neutral" if cr_rating == 3 else "negative"),
            )
            db.add(cr)

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
    avg_txn_value = target_monthly_revenue / max(1, len(all_transactions) / 30 * 30)
    txn_target = int(revenue_target / max(1, avg_txn_value))
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

    # Product goals for top 5 products
    for prod in products[:5]:
        pg = ProductGoal(
            id=nid(), shop_id=shop.id, product_id=prod.id,
            target_units=rng.randint(30, 120), period=current_month,
        )
        db.add(pg)

    # Strategy note
    sn = StrategyNote(
        id=nid(), shop_id=shop.id, quarter=now_q,
        title=f"Q{(today.month - 1) // 3 + 1} {today.year} Growth Strategy",
        objectives=["Increase monthly revenue", "Improve customer retention", "Expand marketing reach"],
        key_results=["Hit revenue target", "Boost repeat rate to 35%", "Post 3x per week on social"],
        notes="Focus on data-driven decisions using RetailIQ insights.",
        status="active",
    )
    db.add(sn)

    # --- Alerts (welcome) ---
    alerts = [
        ("welcome", "success", "general", "Welcome to RetailIQ!",
         f"Your dashboard is ready with 30 days of data for {shop.name}. Explore your insights!"),
        ("insight", "info", "revenue",
         f"Your estimated daily revenue is ${int(daily_target_rev):,}",
         "Based on your revenue range, we've set up realistic benchmarks. Adjust your goals anytime."),
        ("tip", "info", "customers",
         "Start tracking customer return rates",
         "Connect your POS to get real customer data. For now, we've generated sample data to show you the ropes."),
    ]
    for atype, sev, cat, title, msg in alerts:
        a = Alert(
            id=nid(), shop_id=shop.id, alert_type=atype, severity=sev,
            category=cat, title=title, message=msg,
        )
        db.add(a)

    db.commit()
