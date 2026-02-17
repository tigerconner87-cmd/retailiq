"""Google Places API connector for review monitoring and competitor tracking.

Replace stub implementations with real Google Places API calls.
Docs: https://developers.google.com/maps/documentation/places/web-service
"""

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


@dataclass
class PlaceInfo:
    place_id: str
    name: str
    address: str
    rating: float
    review_count: int
    latitude: float
    longitude: float


@dataclass
class PlaceReview:
    author_name: str
    rating: int
    text: str
    time: datetime


MOCK_REVIEWERS = [
    "Alex M.", "Jordan T.", "Chris L.", "Sam P.", "Taylor R.",
    "Morgan K.", "Casey W.", "Riley B.", "Drew N.", "Jamie S.",
    "Pat H.", "Quinn D.", "Avery F.", "Blake G.", "Dakota J.",
]

POSITIVE_TEXTS = [
    "Great selection and friendly staff! Will definitely come back.",
    "Love this place. Always find exactly what I need.",
    "Best shop in the neighborhood. Highly recommend!",
    "Wonderful experience every time. Keep up the great work!",
    "Amazing products and fair prices. My go-to spot.",
]

NEGATIVE_TEXTS = [
    "Long wait times and unhelpful staff. Disappointing.",
    "Prices seem higher than competitors for the same products.",
    "The store was messy and disorganized. Not impressed.",
]

NEUTRAL_TEXTS = [
    "Decent shop. Nothing special but gets the job done.",
    "Average experience. Some good products, some overpriced.",
    "It's okay. Convenient location but could improve selection.",
]


class GooglePlacesConnector:
    """Google Places API connector — currently returns mock data.

    To use real Google Places API:
    1. Set GOOGLE_PLACES_API_KEY in .env
    2. Replace methods with real HTTP calls to the Places API
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        # TODO: self.base_url = "https://maps.googleapis.com/maps/api/place"

    def search_nearby(self, lat: float, lng: float, keyword: str, radius: int = 2000) -> list[PlaceInfo]:
        """Search for nearby places matching keyword. Mock: returns fake competitors."""
        # TODO: Replace with GET /nearbysearch/json
        names = [
            ("The Corner Store", "123 Main St"),
            ("City Goods", "456 Oak Ave"),
            ("Market Square", "789 Elm Blvd"),
            ("Urban Supply Co", "321 Pine St"),
            ("Neighborhood Finds", "654 Cedar Ln"),
        ]
        results = []
        for i, (name, addr) in enumerate(names):
            results.append(PlaceInfo(
                place_id=f"mock-place-{i+1:03d}",
                name=name,
                address=addr,
                rating=round(random.uniform(3.2, 4.8), 1),
                review_count=random.randint(20, 350),
                latitude=lat + random.uniform(-0.01, 0.01),
                longitude=lng + random.uniform(-0.01, 0.01),
            ))
        return results

    def get_place_details(self, place_id: str) -> PlaceInfo | None:
        """Get details for a specific place. Mock: returns generated data."""
        # TODO: Replace with GET /details/json?place_id=...
        return PlaceInfo(
            place_id=place_id,
            name=f"Shop {place_id[-3:]}",
            address="123 Mock St",
            rating=round(random.uniform(3.5, 4.7), 1),
            review_count=random.randint(30, 200),
            latitude=40.7128,
            longitude=-74.0060,
        )

    def get_reviews(self, place_id: str) -> list[PlaceReview]:
        """Fetch reviews for a place. Mock: returns generated reviews."""
        # TODO: Replace with Place Details API (reviews field)
        reviews = []
        now = datetime.now()
        for i in range(random.randint(8, 20)):
            rating = random.choices([1, 2, 3, 4, 5], weights=[5, 5, 10, 30, 50])[0]
            if rating >= 4:
                text = random.choice(POSITIVE_TEXTS)
            elif rating <= 2:
                text = random.choice(NEGATIVE_TEXTS)
            else:
                text = random.choice(NEUTRAL_TEXTS)

            reviews.append(PlaceReview(
                author_name=random.choice(MOCK_REVIEWERS),
                rating=rating,
                text=text,
                time=now - timedelta(days=random.randint(0, 180)),
            ))

        return sorted(reviews, key=lambda r: r.time, reverse=True)
