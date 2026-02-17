"""Square POS connector.

Replace the mock implementations with real Square API calls using
the Square SDK (squareup). Docs: https://developer.squareup.com/
"""

import random
from datetime import date, datetime, timedelta

from app.connectors.base import (
    BasePOSConnector, POSTransaction, POSProduct, POSCustomer, HourlyBreakdown,
)

MOCK_PRODUCTS = [
    POSProduct("sq-001", "Organic Cotton T-Shirt", "Apparel", 29.99, 12.00),
    POSProduct("sq-002", "Slim Fit Jeans", "Apparel", 59.99, 22.00),
    POSProduct("sq-003", "Canvas Tote Bag", "Accessories", 24.99, 8.00),
    POSProduct("sq-004", "Ceramic Travel Mug", "Home", 18.99, 6.50),
    POSProduct("sq-005", "Bamboo Sunglasses", "Accessories", 34.99, 11.00),
    POSProduct("sq-006", "Linen Scarf", "Accessories", 22.99, 7.00),
    POSProduct("sq-007", "Recycled Notebook", "Stationery", 12.99, 3.50),
    POSProduct("sq-008", "Soy Candle Set", "Home", 27.99, 9.00),
    POSProduct("sq-009", "Leather Wallet", "Accessories", 44.99, 15.00),
    POSProduct("sq-010", "Cotton Hoodie", "Apparel", 54.99, 20.00),
]


class SquareConnector(BasePOSConnector):
    """Square POS connector — currently returns mock data.

    To use real Square API:
    1. pip install squareup
    2. Set SQUARE_ACCESS_TOKEN in .env
    3. Replace each method body with Square SDK calls
    """

    # TODO: Replace with real API call
    # from square.client import Client
    # self.client = Client(access_token=credentials.get("access_token"), environment="production")

    def fetch_transactions(self, start_date: date, end_date: date) -> list[POSTransaction]:
        """Mock: generate random transactions for the date range."""
        # TODO: Replace with self.client.orders.search_orders(...)
        transactions = []
        current = start_date
        while current <= end_date:
            day_of_week = current.weekday()
            base_count = {0: 35, 1: 40, 2: 45, 3: 48, 4: 60, 5: 80, 6: 55}[day_of_week]
            count = base_count + random.randint(-10, 10)

            for i in range(count):
                hour = random.choices(
                    range(9, 21),
                    weights=[3, 5, 8, 10, 9, 6, 4, 5, 7, 8, 6, 3],
                )[0]
                minute = random.randint(0, 59)
                ts = datetime(current.year, current.month, current.day, hour, minute)

                num_items = random.choices([1, 2, 3, 4], weights=[45, 30, 18, 7])[0]
                items = []
                subtotal = 0.0
                for _ in range(num_items):
                    product = random.choice(MOCK_PRODUCTS)
                    qty = random.choices([1, 2, 3], weights=[75, 20, 5])[0]
                    line_total = product.price * qty
                    subtotal += line_total
                    items.append({
                        "product_id": product.external_id,
                        "name": product.name,
                        "quantity": qty,
                        "unit_price": product.price,
                        "total": round(line_total, 2),
                    })

                tax = round(subtotal * 0.0825, 2)
                transactions.append(POSTransaction(
                    external_id=f"sq-tx-{current.isoformat()}-{i:04d}",
                    timestamp=ts,
                    subtotal=round(subtotal, 2),
                    tax=tax,
                    total=round(subtotal + tax, 2),
                    items=items,
                    customer_id=f"sq-cust-{random.randint(1, 200):04d}" if random.random() > 0.3 else None,
                ))
            current += timedelta(days=1)
        return transactions

    def fetch_products(self) -> list[POSProduct]:
        """Mock: return static product catalog."""
        # TODO: Replace with self.client.catalog.list_catalog(types=["ITEM"])
        return list(MOCK_PRODUCTS)

    def fetch_customers(self) -> list[POSCustomer]:
        """Mock: return synthetic customer data."""
        # TODO: Replace with self.client.customers.list_customers()
        customers = []
        base_date = datetime.now() - timedelta(days=90)
        for i in range(1, 201):
            first = base_date + timedelta(days=random.randint(0, 80))
            visits = random.choices(
                [1, 2, 3, 5, 8, 12, 20],
                weights=[40, 20, 15, 10, 8, 5, 2],
            )[0]
            last = first + timedelta(days=random.randint(0, 90 - (first - base_date).days))
            customers.append(POSCustomer(
                external_id=f"sq-cust-{i:04d}",
                first_seen=first,
                last_seen=last,
                visit_count=visits,
                total_spent=round(visits * random.uniform(15, 65), 2),
            ))
        return customers

    def fetch_hourly_breakdown(self, target_date: date) -> list[HourlyBreakdown]:
        """Mock: return hourly revenue distribution."""
        # TODO: Replace with aggregated order data from Square
        hourly_weights = {
            9: 0.04, 10: 0.06, 11: 0.10, 12: 0.13, 13: 0.11,
            14: 0.07, 15: 0.05, 16: 0.06, 17: 0.09, 18: 0.11,
            19: 0.10, 20: 0.08,
        }
        day_revenue = random.uniform(1800, 3500)
        results = []
        for hour, weight in hourly_weights.items():
            rev = round(day_revenue * weight * random.uniform(0.8, 1.2), 2)
            tx = max(1, int(rev / random.uniform(18, 35)))
            results.append(HourlyBreakdown(hour=hour, revenue=rev, transaction_count=tx))
        return results
