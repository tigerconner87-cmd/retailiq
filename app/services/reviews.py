import logging
import re
from collections import Counter
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Review, Competitor, CompetitorSnapshot, CompetitorReview, Shop

log = logging.getLogger(__name__)


def get_reviews_summary(db: Session, shop_id: str) -> dict:
    reviews = (
        db.query(Review)
        .filter(Review.shop_id == shop_id, Review.is_own_shop.is_(True))
        .order_by(Review.review_date.desc())
        .limit(100)
        .all()
    )

    avg_rating = db.query(func.avg(Review.rating)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar()

    total = db.query(func.count(Review.id)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar() or 0

    # Sentiment breakdown
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}
    for r in reviews:
        if r.sentiment in sentiments:
            sentiments[r.sentiment] += 1

    # Rating distribution
    rating_dist = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    for r in reviews:
        if r.rating:
            rating_dist[str(r.rating)] = rating_dist.get(str(r.rating), 0) + 1

    # Review velocity (reviews per week, last 12 weeks)
    today = date.today()
    velocity = []
    for w in range(12):
        week_end = today - timedelta(weeks=w)
        week_start = week_end - timedelta(days=6)
        count = sum(
            1 for r in reviews
            if r.review_date and week_start <= r.review_date.date() <= week_end
        )
        velocity.append({"week_start": week_start.isoformat(), "count": count})
    velocity.reverse()

    # NPS estimate (9-10 promoters, 7-8 passive, 1-6 detractors mapped from 1-5 scale)
    promoters = sum(1 for r in reviews if r.rating and r.rating >= 5)
    detractors = sum(1 for r in reviews if r.rating and r.rating <= 2)
    total_with_rating = sum(1 for r in reviews if r.rating)
    nps = round((promoters - detractors) / total_with_rating * 100, 1) if total_with_rating > 0 else 0

    # Response rate
    responded = sum(1 for r in reviews if r.response_text)
    response_rate = round(responded / len(reviews) * 100, 1) if reviews else 0

    # Common terms from review text
    common_terms = _extract_common_terms([r.text for r in reviews if r.text])

    # Generate suggested responses for negative reviews without responses
    review_list = []
    for r in reviews:
        suggested = None
        if r.rating and r.rating <= 3 and not r.response_text:
            suggested = _generate_response_suggestion(r.text, r.rating)

        review_list.append({
            "id": r.id,
            "author_name": r.author_name,
            "rating": r.rating,
            "text": r.text,
            "review_date": r.review_date,
            "sentiment": r.sentiment,
            "is_own_shop": r.is_own_shop,
            "response_text": r.response_text,
            "suggested_response": suggested,
        })

    return {
        "reviews": review_list,
        "avg_rating": round(float(avg_rating), 1) if avg_rating else None,
        "total_reviews": total,
        "sentiment_breakdown": sentiments,
        "rating_distribution": rating_dist,
        "review_velocity": velocity,
        "nps_estimate": nps,
        "response_rate": response_rate,
        "common_terms": common_terms,
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

        # Trend based on rating change
        trend = "stable"
        if rating_change and rating_change > 0.2:
            trend = "improving"
        elif rating_change and rating_change < -0.2:
            trend = "declining"

        # Sentiment from competitor reviews
        comp_reviews = (
            db.query(CompetitorReview)
            .filter(CompetitorReview.competitor_id == c.id)
            .all()
        )
        sentiment_breakdown = {"positive": 0, "neutral": 0, "negative": 0}
        for cr in comp_reviews:
            if cr.sentiment in sentiment_breakdown:
                sentiment_breakdown[cr.sentiment] += 1

        comp_list.append({
            "id": c.id,
            "name": c.name,
            "address": c.address,
            "category": c.category,
            "rating": float(c.rating) if c.rating else None,
            "review_count": c.review_count,
            "rating_change": rating_change,
            "trend": trend,
            "sentiment_breakdown": sentiment_breakdown,
        })

    # Own shop rating
    own_avg = db.query(func.avg(Review.rating)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar()
    own_count = db.query(func.count(Review.id)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar() or 0

    # Market position
    all_ratings = [float(c.rating) for c in competitors if c.rating]
    own_rating_val = round(float(own_avg), 1) if own_avg else None
    if own_rating_val and all_ratings:
        above_count = sum(1 for r in all_ratings if own_rating_val > r)
        rank = len(all_ratings) + 1 - above_count
        market_position = {
            "rank": rank,
            "total": len(all_ratings) + 1,
            "percentile": round(above_count / (len(all_ratings) + 1) * 100),
        }
    else:
        market_position = {"rank": 0, "total": len(all_ratings) + 1, "percentile": 0}

    return {
        "competitors": comp_list,
        "own_rating": own_rating_val,
        "own_review_count": own_count,
        "market_position": market_position,
    }


def classify_sentiment(text: str | None, rating: int) -> str:
    """Simple rule-based sentiment. Replace with NLP model later."""
    if rating >= 4:
        return "positive"
    if rating <= 2:
        return "negative"
    return "neutral"


def _extract_common_terms(texts: list[str]) -> list[dict]:
    """Extract most common meaningful terms from review texts."""
    stop_words = {
        "the", "a", "an", "is", "was", "are", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "up", "about", "into", "through",
        "during", "before", "after", "above", "below", "between", "this",
        "that", "these", "those", "i", "me", "my", "we", "our", "you", "your",
        "he", "she", "it", "they", "them", "his", "her", "its", "their",
        "what", "which", "who", "when", "where", "how", "all", "each",
        "every", "both", "few", "more", "most", "other", "some", "such",
        "no", "nor", "not", "only", "own", "same", "so", "than", "too",
        "very", "just", "but", "and", "or", "if", "then", "else", "here",
        "there", "also", "as", "well", "really", "get", "got", "one",
        "much", "even", "still", "back", "way", "like", "go", "going",
        "went", "come", "came", "make", "made", "take", "took", "think",
    }

    all_words = []
    for text in texts:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        all_words.extend(w for w in words if w not in stop_words)

    counter = Counter(all_words)
    top = counter.most_common(15)
    return [{"term": term, "count": count} for term, count in top]


def _generate_response_suggestion(text: str | None, rating: int) -> str:
    """Generate a suggested response for negative reviews."""
    if rating == 1:
        opener = "We sincerely apologize for your experience."
    elif rating == 2:
        opener = "We're sorry to hear about your experience."
    else:
        opener = "Thank you for your feedback."

    if text:
        text_lower = text.lower()
        if any(w in text_lower for w in ["wait", "slow", "long"]):
            detail = " We're working on improving our service speed."
        elif any(w in text_lower for w in ["rude", "staff", "employee"]):
            detail = " We take staff conduct seriously and will address this."
        elif any(w in text_lower for w in ["price", "expensive", "cost"]):
            detail = " We strive to offer fair value and will review our pricing."
        elif any(w in text_lower for w in ["quality", "broken", "defect"]):
            detail = " Product quality is our priority and we'd like to make this right."
        else:
            detail = " We take all feedback seriously."
    else:
        detail = " We'd love to learn more about how we can improve."

    return f"{opener}{detail} Please reach out to us directly so we can make it right."
