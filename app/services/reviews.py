import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Review, Competitor, CompetitorSnapshot, Shop

log = logging.getLogger(__name__)


def get_reviews_summary(db: Session, shop_id: str) -> dict:
    reviews = (
        db.query(Review)
        .filter(Review.shop_id == shop_id, Review.is_own_shop.is_(True))
        .order_by(Review.review_date.desc())
        .limit(50)
        .all()
    )

    avg_rating = db.query(func.avg(Review.rating)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar()

    total = db.query(func.count(Review.id)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar() or 0

    sentiments = {"positive": 0, "neutral": 0, "negative": 0}
    for r in reviews:
        if r.sentiment in sentiments:
            sentiments[r.sentiment] += 1

    review_list = [
        {
            "id": r.id,
            "author_name": r.author_name,
            "rating": r.rating,
            "text": r.text,
            "review_date": r.review_date.isoformat() if r.review_date else None,
            "sentiment": r.sentiment,
            "is_own_shop": r.is_own_shop,
        }
        for r in reviews
    ]

    return {
        "reviews": review_list,
        "avg_rating": round(float(avg_rating), 1) if avg_rating else None,
        "total_reviews": total,
        "sentiment_breakdown": sentiments,
    }


def get_competitors_summary(db: Session, shop_id: str) -> dict:
    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .order_by(Competitor.rating.desc())
        .all()
    )

    comp_list = []
    for c in competitors:
        # Get rating change from 30 days ago
        thirty_ago = date.today() - timedelta(days=30)
        old_snap = (
            db.query(CompetitorSnapshot)
            .filter(CompetitorSnapshot.competitor_id == c.id, CompetitorSnapshot.date <= thirty_ago)
            .order_by(CompetitorSnapshot.date.desc())
            .first()
        )
        rating_change = None
        if old_snap and old_snap.rating and c.rating:
            rating_change = round(float(c.rating) - float(old_snap.rating), 1)

        comp_list.append({
            "id": c.id,
            "name": c.name,
            "address": c.address,
            "rating": float(c.rating) if c.rating else None,
            "review_count": c.review_count,
            "rating_change": rating_change,
        })

    # Own shop rating
    own_avg = db.query(func.avg(Review.rating)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar()
    own_count = db.query(func.count(Review.id)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar() or 0

    return {
        "competitors": comp_list,
        "own_rating": round(float(own_avg), 1) if own_avg else None,
        "own_review_count": own_count,
    }


def classify_sentiment(text: str | None, rating: int) -> str:
    """Simple rule-based sentiment. Replace with NLP model later."""
    if rating >= 4:
        return "positive"
    if rating <= 2:
        return "negative"
    return "neutral"
