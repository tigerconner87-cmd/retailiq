"""Google Business Profile integration — Places search, reviews sync, sentiment."""

import logging
from datetime import datetime, date, timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Shop, Competitor, CompetitorReview, CompetitorSnapshot, Review, new_id
from app.services.cache import cache_get, cache_set

log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

PLACES_BASE = "https://maps.googleapis.com/maps/api/place"

POSITIVE_WORDS = {
    "great", "excellent", "amazing", "wonderful", "fantastic", "love", "best",
    "perfect", "friendly", "delicious", "recommend", "awesome", "outstanding",
    "clean", "helpful",
}

NEGATIVE_WORDS = {
    "terrible", "awful", "worst", "rude", "dirty", "slow", "cold", "bad",
    "horrible", "disappointed", "never", "disgusting", "overpriced", "unfriendly",
}

# ── Mock data (used when GOOGLE_PLACES_API_KEY is not configured) ────────────

MOCK_SEARCH_RESULTS = [
    {"place_id": "mock_1", "name": "Downtown Coffee House", "address": "123 Main St", "rating": 4.3, "review_count": 187, "lat": 40.7128, "lng": -74.0060},
    {"place_id": "mock_2", "name": "The Corner Store", "address": "456 Oak Ave", "rating": 4.1, "review_count": 93, "lat": 40.7138, "lng": -74.0050},
    {"place_id": "mock_3", "name": "Sunrise Boutique", "address": "789 Elm St", "rating": 4.6, "review_count": 245, "lat": 40.7148, "lng": -74.0040},
    {"place_id": "mock_4", "name": "Metro Retail Co", "address": "321 Pine Rd", "rating": 3.8, "review_count": 62, "lat": 40.7118, "lng": -74.0070},
]

MOCK_REVIEWS = [
    {"author": "Sarah M.", "rating": 5, "text": "Absolutely love this place! The staff is incredibly friendly and the selection is amazing. Will definitely be coming back.", "time": 1706745600, "relative_time": "2 weeks ago"},
    {"author": "James K.", "rating": 4, "text": "Good quality products at reasonable prices. The store was clean and well-organized.", "time": 1706140800, "relative_time": "3 weeks ago"},
    {"author": "Lisa P.", "rating": 2, "text": "Waited 15 minutes and nobody helped me. The prices seem overpriced for what you get. Disappointed.", "time": 1705536000, "relative_time": "1 month ago"},
    {"author": "Mike R.", "rating": 5, "text": "Best shop in the area! Great customer service and unique products you can't find anywhere else.", "time": 1704931200, "relative_time": "1 month ago"},
    {"author": "Emma W.", "rating": 3, "text": "It's okay. Nothing special but not bad either. Average prices and selection.", "time": 1704326400, "relative_time": "2 months ago"},
]


# ── 1. Sentiment analysis ────────────────────────────────────────────────────

def analyze_sentiment(text: str) -> str:
    """Keyword-based sentiment analysis.

    Returns "positive", "negative", or "neutral".
    """
    if not text:
        return "neutral"

    words = set(text.lower().split())

    pos_count = sum(1 for w in words if w.strip(".,!?;:'\"()") in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w.strip(".,!?;:'\"()") in NEGATIVE_WORDS)

    if pos_count > neg_count:
        return "positive"
    if neg_count > pos_count:
        return "negative"
    return "neutral"


# ── 2. Search places ─────────────────────────────────────────────────────────

def search_places(query: str) -> list[dict]:
    """Search Google Places by text query.

    Returns a list of place dicts with place_id, name, address, rating,
    review_count, lat, lng.  Falls back to mock data when no API key is set.
    """
    cache_key = f"riq:places:search:{hash(query)}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    if not settings.GOOGLE_PLACES_API_KEY:
        log.info("No GOOGLE_PLACES_API_KEY configured — returning mock search results")
        cache_set(cache_key, MOCK_SEARCH_RESULTS, ttl=3600)
        return MOCK_SEARCH_RESULTS

    try:
        resp = httpx.get(
            f"{PLACES_BASE}/textsearch/json",
            params={"query": query, "key": settings.GOOGLE_PLACES_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for place in data.get("results", []):
            results.append({
                "place_id": place.get("place_id"),
                "name": place.get("name"),
                "address": place.get("formatted_address", ""),
                "rating": place.get("rating"),
                "review_count": place.get("user_ratings_total", 0),
                "lat": place.get("geometry", {}).get("location", {}).get("lat"),
                "lng": place.get("geometry", {}).get("location", {}).get("lng"),
            })

        cache_set(cache_key, results, ttl=3600)
        return results

    except Exception:
        log.exception("Google Places text search failed for query=%s", query)
        return []


# ── 3. Find nearby ───────────────────────────────────────────────────────────

def find_nearby(
    lat: float,
    lng: float,
    business_type: str = "store",
    radius: int = 5000,
) -> list[dict]:
    """Search for nearby businesses via Google Places Nearby Search.

    Returns the same shape as search_places.  Falls back to mock data when no
    API key is set.
    """
    cache_key = f"riq:places:nearby:{lat:.4f},{lng:.4f}:{business_type}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    if not settings.GOOGLE_PLACES_API_KEY:
        log.info("No GOOGLE_PLACES_API_KEY configured — returning mock nearby results")
        cache_set(cache_key, MOCK_SEARCH_RESULTS, ttl=3600)
        return MOCK_SEARCH_RESULTS

    try:
        resp = httpx.get(
            f"{PLACES_BASE}/nearbysearch/json",
            params={
                "location": f"{lat},{lng}",
                "radius": radius,
                "type": business_type,
                "key": settings.GOOGLE_PLACES_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for place in data.get("results", []):
            results.append({
                "place_id": place.get("place_id"),
                "name": place.get("name"),
                "address": place.get("formatted_address", place.get("vicinity", "")),
                "rating": place.get("rating"),
                "review_count": place.get("user_ratings_total", 0),
                "lat": place.get("geometry", {}).get("location", {}).get("lat"),
                "lng": place.get("geometry", {}).get("location", {}).get("lng"),
            })

        cache_set(cache_key, results, ttl=3600)
        return results

    except Exception:
        log.exception("Google Places nearby search failed (lat=%s, lng=%s)", lat, lng)
        return []


# ── 4. Get place reviews ─────────────────────────────────────────────────────

def get_place_reviews(place_id: str) -> dict:
    """Fetch reviews for a single place via Google Places Details API.

    Returns {name, rating, review_count, reviews: [{author, rating, text, time,
    relative_time}]}.  Falls back to mock reviews when no API key is set.
    """
    cache_key = f"riq:places:reviews:{place_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    if not settings.GOOGLE_PLACES_API_KEY:
        log.info("No GOOGLE_PLACES_API_KEY configured — returning mock reviews")
        mock_result = {
            "name": "Mock Business",
            "rating": 4.2,
            "review_count": len(MOCK_REVIEWS),
            "reviews": MOCK_REVIEWS,
        }
        cache_set(cache_key, mock_result, ttl=86400)
        return mock_result

    try:
        resp = httpx.get(
            f"{PLACES_BASE}/details/json",
            params={
                "place_id": place_id,
                "fields": "reviews,rating,user_ratings_total,name",
                "key": settings.GOOGLE_PLACES_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("result", {})

        reviews = []
        for r in data.get("reviews", []):
            reviews.append({
                "author": r.get("author_name", "Anonymous"),
                "rating": r.get("rating"),
                "text": r.get("text", ""),
                "time": r.get("time"),
                "relative_time": r.get("relative_time_description", ""),
            })

        result = {
            "name": data.get("name", ""),
            "rating": data.get("rating"),
            "review_count": data.get("user_ratings_total", 0),
            "reviews": reviews,
        }
        cache_set(cache_key, result, ttl=86400)
        return result

    except Exception:
        log.exception("Google Places details failed for place_id=%s", place_id)
        return {"name": "", "rating": None, "review_count": 0, "reviews": []}


# ── 5. Sync reviews for own shop ─────────────────────────────────────────────

def sync_reviews_for_shop(db: Session, shop: Shop) -> int:
    """Pull Google reviews for the shop's own listing and persist new ones.

    Returns the count of newly created Review records.
    """
    if not shop.google_place_id:
        log.debug("Shop %s has no google_place_id — skipping review sync", shop.id)
        return 0

    place_data = get_place_reviews(shop.google_place_id)
    new_count = 0

    for rev in place_data.get("reviews", []):
        # Derive a review date from the epoch timestamp
        review_dt = (
            datetime.utcfromtimestamp(rev["time"])
            if rev.get("time")
            else datetime.utcnow()
        )

        # De-duplicate: same author + rating within a 7-day window
        existing = (
            db.query(Review)
            .filter(
                Review.shop_id == shop.id,
                Review.author_name == rev.get("author", "Anonymous"),
                Review.rating == rev.get("rating"),
                Review.review_date >= review_dt - timedelta(days=7),
                Review.review_date <= review_dt + timedelta(days=7),
            )
            .first()
        )
        if existing:
            continue

        sentiment = analyze_sentiment(rev.get("text", ""))

        review = Review(
            id=new_id(),
            shop_id=shop.id,
            source="google",
            author_name=rev.get("author", "Anonymous"),
            rating=rev.get("rating"),
            text=rev.get("text", ""),
            review_date=review_dt,
            sentiment=sentiment,
            is_own_shop=True,
        )
        db.add(review)
        new_count += 1

    if new_count:
        db.commit()
        log.info("Synced %d new Google reviews for shop %s", new_count, shop.id)

    return new_count


# ── 6. Sync reviews for competitor ───────────────────────────────────────────

def sync_reviews_for_competitor(db: Session, competitor: Competitor) -> int:
    """Pull Google reviews for a competitor and persist new ones.

    Also creates a CompetitorSnapshot and updates the competitor's aggregate
    rating / review_count.  Returns the count of newly created reviews.
    """
    if not competitor.google_place_id:
        log.debug("Competitor %s has no google_place_id — skipping", competitor.id)
        return 0

    place_data = get_place_reviews(competitor.google_place_id)
    new_count = 0

    for rev in place_data.get("reviews", []):
        review_dt = (
            datetime.utcfromtimestamp(rev["time"])
            if rev.get("time")
            else datetime.utcnow()
        )

        # De-duplicate: same author + rating within a 7-day window
        existing = (
            db.query(CompetitorReview)
            .filter(
                CompetitorReview.competitor_id == competitor.id,
                CompetitorReview.author_name == rev.get("author", "Anonymous"),
                CompetitorReview.rating == rev.get("rating"),
                CompetitorReview.review_date >= review_dt - timedelta(days=7),
                CompetitorReview.review_date <= review_dt + timedelta(days=7),
            )
            .first()
        )
        if existing:
            continue

        sentiment = analyze_sentiment(rev.get("text", ""))

        comp_review = CompetitorReview(
            id=new_id(),
            competitor_id=competitor.id,
            author_name=rev.get("author", "Anonymous"),
            rating=rev.get("rating"),
            text=rev.get("text", ""),
            review_date=review_dt,
            sentiment=sentiment,
        )
        db.add(comp_review)
        new_count += 1

    # Create a daily snapshot with latest aggregate data
    snapshot = CompetitorSnapshot(
        id=new_id(),
        competitor_id=competitor.id,
        date=date.today(),
        rating=place_data.get("rating"),
        review_count=place_data.get("review_count", 0),
    )
    db.add(snapshot)

    # Update competitor aggregate fields
    if place_data.get("rating") is not None:
        competitor.rating = place_data["rating"]
    if place_data.get("review_count") is not None:
        competitor.review_count = place_data["review_count"]

    db.commit()
    log.info(
        "Synced %d new reviews for competitor %s (%s)",
        new_count,
        competitor.id,
        competitor.name,
    )

    return new_count


# ── 7. Sync all competitors for a shop ───────────────────────────────────────

def sync_all_competitors(db: Session, shop_id: str) -> dict:
    """Sync Google reviews for every competitor belonging to a shop.

    Returns a summary dict:
        {synced: int, total_new_reviews: int,
         competitors: [{name: str, new_reviews: int}]}
    """
    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .all()
    )

    total_new = 0
    comp_results = []

    for comp in competitors:
        try:
            n = sync_reviews_for_competitor(db, comp)
        except Exception:
            log.exception("Failed to sync reviews for competitor %s", comp.id)
            n = 0

        total_new += n
        comp_results.append({"name": comp.name, "new_reviews": n})

    log.info(
        "Competitor sync complete for shop %s: %d competitors, %d new reviews",
        shop_id,
        len(competitors),
        total_new,
    )

    return {
        "synced": len(competitors),
        "total_new_reviews": total_new,
        "competitors": comp_results,
    }
