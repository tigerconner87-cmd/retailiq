from datetime import datetime, timedelta, date
from decimal import Decimal

from app.models import (
    Customer, DailySnapshot, HourlySnapshot, Product,
    Shop, Transaction, TransactionItem, User,
)
from app.services.analytics import (
    get_customer_metrics, get_peak_hours, get_product_rankings,
    get_sales_trends, get_summary,
)
from app.services.auth import hash_password


def _seed(db):
    """Create a user, shop, products, customers, transactions, and snapshots."""
    user = User(
        id="u1", email="a@b.com", hashed_password=hash_password("pw"),
        full_name="A", plan_tier="growth",
    )
    db.add(user)
    db.flush()

    shop = Shop(id="s1", user_id="u1", name="S", pos_system="square")
    db.add(shop)
    db.flush()

    prod = Product(id="p1", shop_id="s1", name="Widget", category="General", price=Decimal("25.00"), cost=Decimal("10.00"))
    db.add(prod)
    db.flush()

    cust1 = Customer(
        id="c1", shop_id="s1", first_seen=datetime.now() - timedelta(days=30),
        last_seen=datetime.now(), visit_count=5, total_spent=Decimal("200"),
    )
    cust2 = Customer(
        id="c2", shop_id="s1", first_seen=datetime.now() - timedelta(days=10),
        last_seen=datetime.now(), visit_count=1, total_spent=Decimal("30"),
    )
    db.add_all([cust1, cust2])
    db.flush()

    today = date.today()
    yesterday = today - timedelta(days=1)

    for d, rev in [(today, "500.00"), (yesterday, "400.00")]:
        for h in [10, 11, 12, 13]:
            tx = Transaction(
                id=f"tx-{d}-{h}", shop_id="s1", subtotal=Decimal(rev) / 4,
                tax=Decimal("5.00"), total=Decimal(rev) / 4 + Decimal("5.00"),
                items_count=1, timestamp=datetime.combine(d, datetime.min.time().replace(hour=h)),
                customer_id="c1",
            )
            db.add(tx)
            db.flush()

            ti = TransactionItem(
                id=f"ti-{d}-{h}", transaction_id=tx.id, product_id="p1",
                quantity=1, unit_price=Decimal("25.00"), total=Decimal("25.00"),
            )
            db.add(ti)

    # Snapshots
    for d, rev in [(today, "520.00"), (yesterday, "420.00")]:
        ds = DailySnapshot(
            id=f"ds-{d}", shop_id="s1", date=d, total_revenue=Decimal(rev),
            transaction_count=4, avg_transaction_value=Decimal(rev) / 4,
            unique_customers=2, repeat_customers=1, new_customers=1,
        )
        db.add(ds)

        for h in [10, 11, 12, 13]:
            hs = HourlySnapshot(
                id=f"hs-{d}-{h}", shop_id="s1", date=d, hour=h,
                revenue=Decimal(rev) / 4, transaction_count=1,
            )
            db.add(hs)

    db.commit()
    return shop


def test_get_summary(db):
    shop = _seed(db)
    summary = get_summary(db, shop.id)

    assert summary["transactions_today"] == 4
    assert summary["total_customers"] == 2
    assert summary["repeat_customer_rate"] == 50.0  # 1 of 2 has visit_count > 1


def test_get_sales_trends(db):
    shop = _seed(db)
    trends = get_sales_trends(db, shop.id, days=7)

    assert len(trends["daily"]) >= 1
    assert "revenue" in trends["daily"][0]
    assert len(trends["weekly_totals"]) >= 1


def test_get_peak_hours(db):
    shop = _seed(db)
    hours = get_peak_hours(db, shop.id, days=7)

    assert len(hours) > 0
    assert "hour" in hours[0]
    assert "value" in hours[0]


def test_get_product_rankings(db):
    shop = _seed(db)
    products = get_product_rankings(db, shop.id, days=7)

    assert products["total_products"] == 1
    assert products["top_products"][0]["name"] == "Widget"
    assert products["top_products"][0]["units_sold"] >= 1


def test_get_customer_metrics(db):
    shop = _seed(db)
    metrics = get_customer_metrics(db, shop.id)

    assert metrics["total_customers"] == 2
    assert metrics["repeat_customers"] == 1
    assert metrics["repeat_rate"] == 50.0
    assert metrics["avg_visits_per_customer"] == 3.0  # (5+1)/2
