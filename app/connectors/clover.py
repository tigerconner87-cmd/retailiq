"""Clover POS connector.

Replace the mock implementations with real Clover REST API calls.
Docs: https://docs.clover.com/reference
"""

import random
from datetime import date, datetime, timedelta

from app.connectors.base import (
    BasePOSConnector, POSTransaction, POSProduct, POSCustomer, HourlyBreakdown,
)

MOCK_PRODUCTS = [
    POSProduct("cl-001", "House Blend Coffee 12oz", "Beverages", 14.99, 5.00),
    POSProduct("cl-002", "Cold Brew Concentrate", "Beverages", 18.99, 6.00),
    POSProduct("cl-003", "Blueberry Muffin", "Bakery", 4.50, 1.20),
    POSProduct("cl-004", "Avocado Toast", "Food", 11.99, 3.80),
    POSProduct("cl-005", "Breakfast Burrito", "Food", 9.99, 3.00),
    POSProduct("cl-006", "Matcha Latte", "Beverages", 5.99, 1.80),
    POSProduct("cl-007", "Croissant", "Bakery", 3.99, 1.00),
    POSProduct("cl-008", "Acai Bowl", "Food", 13.99, 4.50),
    POSProduct("cl-009", "Chai Tea Latte", "Beverages", 5.49, 1.50),
    POSProduct("cl-010", "Banana Bread Slice", "Bakery", 4.99, 1.30),
]


class CloverConnector(BasePOSConnector):
    """Clover POS connector — currently returns mock data.

    To use real Clover API:
    1. pip install requests
    2. Set CLOVER_ACCESS_TOKEN and CLOVER_MERCHANT_ID in .env
    3. Replace each method body with Clover REST API calls
    """

    # TODO: Real implementation
    # self.base_url = f"https://api.clover.com/v3/merchants/{merchant_id}"
    # self.headers = {"Authorization": f"Bearer {access_token}"}

    def fetch_transactions(self, start_date: date, end_date: date) -> list[POSTransaction]:
        # TODO: Replace with GET /v3/merchants/{mId}/orders
        transactions = []
        current = start_date
        while current <= end_date:
            day_of_week = current.weekday()
            base_count = {0: 50, 1: 55, 2: 60, 3: 65, 4: 80, 5: 95, 6: 70}[day_of_week]
            count = base_count + random.randint(-12, 12)

            for i in range(count):
                hour = random.choices(
                    range(7, 19),
                    weights=[6, 10, 12, 9, 8, 10, 7, 5, 6, 8, 7, 4],
                )[0]
                ts = datetime(current.year, current.month, current.day, hour, random.randint(0, 59))

                num_items = random.choices([1, 2, 3, 4], weights=[40, 35, 18, 7])[0]
                items = []
                subtotal = 0.0
                for _ in range(num_items):
                    product = random.choice(MOCK_PRODUCTS)
                    qty = random.choices([1, 2, 3], weights=[70, 25, 5])[0]
                    line_total = product.price * qty
                    subtotal += line_total
                    items.append({
                        "product_id": product.external_id,
                        "name": product.name,
                        "quantity": qty,
                        "unit_price": product.price,
                        "total": round(line_total, 2),
                    })

                tax = round(subtotal * 0.0875, 2)
                transactions.append(POSTransaction(
                    external_id=f"cl-tx-{current.isoformat()}-{i:04d}",
                    timestamp=ts,
                    subtotal=round(subtotal, 2),
                    tax=tax,
                    total=round(subtotal + tax, 2),
                    items=items,
                    customer_id=f"cl-cust-{random.randint(1, 250):04d}" if random.random() > 0.4 else None,
                ))
            current += timedelta(days=1)
        return transactions

    def fetch_products(self) -> list[POSProduct]:
        # TODO: Replace with GET /v3/merchants/{mId}/items
        return list(MOCK_PRODUCTS)

    def fetch_customers(self) -> list[POSCustomer]:
        # TODO: Replace with GET /v3/merchants/{mId}/customers
        customers = []
        base_date = datetime.now() - timedelta(days=90)
        for i in range(1, 251):
            first = base_date + timedelta(days=random.randint(0, 80))
            visits = random.choices([1, 2, 3, 4, 6, 10, 18], weights=[35, 20, 15, 12, 10, 6, 2])[0]
            last = first + timedelta(days=random.randint(0, max(1, 90 - (first - base_date).days)))
            customers.append(POSCustomer(
                external_id=f"cl-cust-{i:04d}",
                first_seen=first,
                last_seen=last,
                visit_count=visits,
                total_spent=round(visits * random.uniform(8, 35), 2),
            ))
        return customers

    def fetch_hourly_breakdown(self, target_date: date) -> list[HourlyBreakdown]:
        # TODO: Replace with aggregated Clover order data
        hourly_weights = {
            7: 0.06, 8: 0.10, 9: 0.12, 10: 0.09, 11: 0.08, 12: 0.10,
            13: 0.07, 14: 0.05, 15: 0.06, 16: 0.08, 17: 0.10, 18: 0.06, 19: 0.03,
        }
        day_revenue = random.uniform(2000, 4000)
        results = []
        for hour, weight in hourly_weights.items():
            rev = round(day_revenue * weight * random.uniform(0.8, 1.2), 2)
            tx = max(1, int(rev / random.uniform(8, 20)))
            results.append(HourlyBreakdown(hour=hour, revenue=rev, transaction_count=tx))
        return results
