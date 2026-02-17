"""Shopify POS connector.

Replace the mock implementations with real Shopify Admin API calls.
Docs: https://shopify.dev/docs/api/admin-rest
"""

import random
from datetime import date, datetime, timedelta

from app.connectors.base import (
    BasePOSConnector, POSTransaction, POSProduct, POSCustomer, HourlyBreakdown,
)

MOCK_PRODUCTS = [
    POSProduct("sh-001", "Hand-Poured Soy Candle", "Home", 24.00, 7.50),
    POSProduct("sh-002", "Artisan Soap Bar", "Beauty", 8.99, 2.50),
    POSProduct("sh-003", "Essential Oil Diffuser", "Home", 39.99, 14.00),
    POSProduct("sh-004", "Organic Face Cream", "Beauty", 32.00, 10.00),
    POSProduct("sh-005", "Beeswax Lip Balm 3-Pack", "Beauty", 12.99, 3.80),
    POSProduct("sh-006", "Dried Flower Bouquet", "Decor", 28.00, 9.00),
    POSProduct("sh-007", "Ceramic Planter", "Decor", 22.99, 7.00),
    POSProduct("sh-008", "Linen Tea Towel Set", "Home", 19.99, 6.00),
]


class ShopifyConnector(BasePOSConnector):
    """Shopify POS connector — currently returns mock data.

    To use real Shopify API:
    1. pip install shopifyapi
    2. Set SHOPIFY_ACCESS_TOKEN and SHOPIFY_SHOP_DOMAIN in .env
    3. Replace each method body with Shopify API calls
    """

    # TODO: Real implementation
    # import shopify
    # shopify.Session.setup(api_key=..., secret=...)

    def fetch_transactions(self, start_date: date, end_date: date) -> list[POSTransaction]:
        # TODO: Replace with shopify.Order.find(...)
        transactions = []
        current = start_date
        while current <= end_date:
            day_of_week = current.weekday()
            base_count = {0: 25, 1: 30, 2: 35, 3: 38, 4: 50, 5: 70, 6: 45}[day_of_week]
            count = base_count + random.randint(-8, 8)

            for i in range(count):
                hour = random.choices(range(10, 20), weights=[4, 7, 9, 8, 5, 4, 5, 8, 7, 3])[0]
                ts = datetime(current.year, current.month, current.day, hour, random.randint(0, 59))

                num_items = random.choices([1, 2, 3], weights=[50, 35, 15])[0]
                items = []
                subtotal = 0.0
                for _ in range(num_items):
                    product = random.choice(MOCK_PRODUCTS)
                    qty = random.choices([1, 2], weights=[80, 20])[0]
                    line_total = product.price * qty
                    subtotal += line_total
                    items.append({
                        "product_id": product.external_id,
                        "name": product.name,
                        "quantity": qty,
                        "unit_price": product.price,
                        "total": round(line_total, 2),
                    })

                tax = round(subtotal * 0.07, 2)
                transactions.append(POSTransaction(
                    external_id=f"sh-tx-{current.isoformat()}-{i:04d}",
                    timestamp=ts,
                    subtotal=round(subtotal, 2),
                    tax=tax,
                    total=round(subtotal + tax, 2),
                    items=items,
                    customer_id=f"sh-cust-{random.randint(1, 150):04d}" if random.random() > 0.35 else None,
                ))
            current += timedelta(days=1)
        return transactions

    def fetch_products(self) -> list[POSProduct]:
        # TODO: Replace with shopify.Product.find()
        return list(MOCK_PRODUCTS)

    def fetch_customers(self) -> list[POSCustomer]:
        # TODO: Replace with shopify.Customer.find()
        customers = []
        base_date = datetime.now() - timedelta(days=90)
        for i in range(1, 151):
            first = base_date + timedelta(days=random.randint(0, 80))
            visits = random.choices([1, 2, 3, 5, 8, 15], weights=[45, 22, 15, 10, 6, 2])[0]
            last = first + timedelta(days=random.randint(0, max(1, 90 - (first - base_date).days)))
            customers.append(POSCustomer(
                external_id=f"sh-cust-{i:04d}",
                first_seen=first,
                last_seen=last,
                visit_count=visits,
                total_spent=round(visits * random.uniform(12, 55), 2),
            ))
        return customers

    def fetch_hourly_breakdown(self, target_date: date) -> list[HourlyBreakdown]:
        # TODO: Replace with aggregated Shopify order data
        hourly_weights = {
            10: 0.06, 11: 0.10, 12: 0.14, 13: 0.12, 14: 0.08,
            15: 0.06, 16: 0.07, 17: 0.12, 18: 0.12, 19: 0.08, 20: 0.05,
        }
        day_revenue = random.uniform(1200, 2800)
        results = []
        for hour, weight in hourly_weights.items():
            rev = round(day_revenue * weight * random.uniform(0.8, 1.2), 2)
            tx = max(1, int(rev / random.uniform(15, 30)))
            results.append(HourlyBreakdown(hour=hour, revenue=rev, transaction_count=tx))
        return results
