from abc import ABC, abstractmethod
from datetime import date, datetime
from dataclasses import dataclass, field


@dataclass
class POSTransaction:
    external_id: str
    timestamp: datetime
    subtotal: float
    tax: float
    total: float
    items: list[dict] = field(default_factory=list)
    customer_id: str | None = None


@dataclass
class POSProduct:
    external_id: str
    name: str
    category: str | None = None
    price: float = 0.0
    cost: float | None = None


@dataclass
class POSCustomer:
    external_id: str
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    visit_count: int = 1
    total_spent: float = 0.0


@dataclass
class HourlyBreakdown:
    hour: int
    revenue: float
    transaction_count: int


class BasePOSConnector(ABC):
    """Abstract connector for POS system integrations.

    Subclass this and implement each method with real API calls.
    Default implementations return mock data for development.
    """

    def __init__(self, credentials: dict | None = None):
        self.credentials = credentials or {}

    @abstractmethod
    def fetch_transactions(self, start_date: date, end_date: date) -> list[POSTransaction]:
        """Fetch transactions in a date range."""

    @abstractmethod
    def fetch_products(self) -> list[POSProduct]:
        """Fetch the product catalog."""

    @abstractmethod
    def fetch_customers(self) -> list[POSCustomer]:
        """Fetch customer visit data."""

    @abstractmethod
    def fetch_hourly_breakdown(self, target_date: date) -> list[HourlyBreakdown]:
        """Fetch revenue broken down by hour for a single day."""

    def test_connection(self) -> bool:
        """Verify the connection credentials work."""
        try:
            self.fetch_products()
            return True
        except Exception:
            return False
