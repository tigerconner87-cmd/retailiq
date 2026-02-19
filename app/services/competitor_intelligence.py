"""Competitor Intelligence Engine for Forge.

Analyzes competitor data to detect opportunities, generate marketing responses,
build weekly reports, and provide actionable competitive intelligence.
"""

import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Competitor, CompetitorReview, CompetitorSnapshot,
    MarketingResponse, Review, Shop,
)

log = logging.getLogger(__name__)

SHOP_NAME_PLACEHOLDER = "your shop"

# ── Threat Level Assessment ─────────────────────────────────────────────────


def _threat_level(own_rating: float | None, comp_rating: float | None) -> str:
    if own_rating is None or comp_rating is None:
        return "Low"
    diff = comp_rating - own_rating
    if diff >= 0.3:
        return "High"
    if diff >= -0.1:
        return "Medium"
    return "Low"


def _sentiment_score(reviews: list) -> float:
    if not reviews:
        return 0.0
    pos = sum(1 for r in reviews if r.sentiment == "positive")
    return round(pos / len(reviews) * 100, 1)


def _response_rate(reviews: list) -> float:
    """Estimate response rate for competitor (simulated)."""
    if not reviews:
        return 0.0
    # Since we don't track competitor responses, estimate from rating consistency
    high_rated = sum(1 for r in reviews if r.rating and r.rating >= 4)
    return round(high_rated / len(reviews) * 100, 1) if reviews else 0.0


def _estimated_traffic(review_count: int, rating: float | None) -> int:
    """Estimate monthly traffic from review count and rating."""
    if not rating:
        return review_count * 10
    return int(review_count * (rating / 4.0) * 15)


# ── Competitor Overview ─────────────────────────────────────────────────────


def get_competitor_overview(db: Session, shop_id: str) -> dict:
    """Full competitor overview with cards, threat levels, and trends."""
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    shop_name = shop.name if shop else SHOP_NAME_PLACEHOLDER

    own_avg = db.query(func.avg(Review.rating)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar()
    own_count = db.query(func.count(Review.id)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar() or 0
    own_reviews = (
        db.query(Review)
        .filter(Review.shop_id == shop_id, Review.is_own_shop.is_(True))
        .all()
    )
    own_rating = round(float(own_avg), 1) if own_avg else None
    own_sentiment = _sentiment_score([type("R", (), {"sentiment": r.sentiment})() for r in own_reviews])
    own_responded = sum(1 for r in own_reviews if r.response_text)
    own_response_rate = round(own_responded / len(own_reviews) * 100, 1) if own_reviews else 0.0

    # Own shop card
    own_card = {
        "id": "own",
        "name": shop_name,
        "is_own": True,
        "rating": own_rating,
        "review_count": own_count,
        "rating_trend": "stable",
        "sentiment_score": own_sentiment,
        "response_rate": own_response_rate,
        "threat_level": None,
        "estimated_traffic": _estimated_traffic(own_count, own_rating),
    }

    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .order_by(Competitor.rating.desc())
        .all()
    )

    cards = [own_card]
    for c in competitors:
        comp_reviews = db.query(CompetitorReview).filter(
            CompetitorReview.competitor_id == c.id
        ).all()

        # Get rating trend
        thirty_ago = date.today() - timedelta(days=30)
        old_snap = (
            db.query(CompetitorSnapshot)
            .filter(CompetitorSnapshot.competitor_id == c.id, CompetitorSnapshot.date <= thirty_ago)
            .order_by(CompetitorSnapshot.date.desc())
            .first()
        )
        rating_change = None
        trend = "stable"
        if old_snap and old_snap.rating and c.rating:
            rating_change = round(float(c.rating) - float(old_snap.rating), 1)
            if rating_change > 0.2:
                trend = "improving"
            elif rating_change < -0.2:
                trend = "declining"

        cards.append({
            "id": c.id,
            "name": c.name,
            "is_own": False,
            "rating": float(c.rating) if c.rating else None,
            "review_count": c.review_count,
            "rating_trend": trend,
            "rating_change": rating_change,
            "sentiment_score": _sentiment_score(comp_reviews),
            "response_rate": _response_rate(comp_reviews),
            "threat_level": _threat_level(own_rating, float(c.rating) if c.rating else None),
            "estimated_traffic": _estimated_traffic(c.review_count, float(c.rating) if c.rating else None),
            "address": c.address,
            "category": c.category,
        })

    return {"cards": cards, "own_rating": own_rating, "own_review_count": own_count}


# ── Comparison Table ────────────────────────────────────────────────────────


def _extract_strengths_weaknesses(reviews: list) -> tuple[list[str], list[str]]:
    """Extract strengths and weaknesses from review text."""
    strengths = []
    weaknesses = []

    positive_keywords = {
        "friendly": "Friendly staff", "helpful": "Helpful service",
        "clean": "Clean store", "organized": "Well organized",
        "quality": "Quality products", "selection": "Great selection",
        "price": "Good prices", "unique": "Unique finds",
        "atmosphere": "Great atmosphere", "knowledgeable": "Knowledgeable staff",
        "curated": "Well curated", "experience": "Great experience",
        "gift": "Good for gifts", "convenient": "Convenient location",
    }

    negative_keywords = {
        "wait": "Slow service", "slow": "Slow service",
        "rude": "Rude staff", "expensive": "Overpriced",
        "overpriced": "Overpriced", "dirty": "Dirty store",
        "disorganized": "Disorganized", "messy": "Messy store",
        "limited": "Limited selection", "broken": "Quality issues",
        "ignored": "Poor attention", "closed": "Unreliable hours",
        "refund": "Bad return policy", "scent": "Product quality issues",
    }

    pos_counts = Counter()
    neg_counts = Counter()

    for r in reviews:
        if not r.text:
            continue
        text_lower = r.text.lower()
        if r.sentiment == "positive" or (r.rating and r.rating >= 4):
            for kw, label in positive_keywords.items():
                if kw in text_lower:
                    pos_counts[label] += 1
        if r.sentiment == "negative" or (r.rating and r.rating <= 2):
            for kw, label in negative_keywords.items():
                if kw in text_lower:
                    neg_counts[label] += 1

    strengths = [label for label, _ in pos_counts.most_common(3)]
    weaknesses = [label for label, _ in neg_counts.most_common(3)]

    if not strengths:
        strengths = ["No clear strengths identified"]
    if not weaknesses:
        weaknesses = ["No significant weaknesses"]

    return strengths, weaknesses


def get_competitor_comparison(db: Session, shop_id: str) -> dict:
    """Side-by-side comparison table."""
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    shop_name = shop.name if shop else SHOP_NAME_PLACEHOLDER

    own_avg = db.query(func.avg(Review.rating)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar()
    own_count = db.query(func.count(Review.id)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar() or 0
    own_reviews = (
        db.query(Review)
        .filter(Review.shop_id == shop_id, Review.is_own_shop.is_(True))
        .all()
    )
    own_rating = round(float(own_avg), 1) if own_avg else 0
    own_sentiment = _sentiment_score([type("R", (), {"sentiment": r.sentiment})() for r in own_reviews])
    own_responded = sum(1 for r in own_reviews if r.response_text)
    own_response_rate = round(own_responded / len(own_reviews) * 100, 1) if own_reviews else 0.0
    own_strengths, own_weaknesses = _extract_strengths_weaknesses(own_reviews)

    own_row = {
        "name": shop_name,
        "is_own": True,
        "rating": own_rating,
        "review_count": own_count,
        "response_rate": own_response_rate,
        "sentiment_score": own_sentiment,
        "estimated_traffic": _estimated_traffic(own_count, own_rating),
        "strengths": own_strengths,
        "weaknesses": own_weaknesses,
    }

    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .order_by(Competitor.rating.desc())
        .all()
    )

    rows = [own_row]
    for c in competitors:
        comp_reviews = db.query(CompetitorReview).filter(
            CompetitorReview.competitor_id == c.id
        ).all()
        c_strengths, c_weaknesses = _extract_strengths_weaknesses(comp_reviews)

        rows.append({
            "name": c.name,
            "is_own": False,
            "rating": float(c.rating) if c.rating else 0,
            "review_count": c.review_count,
            "response_rate": _response_rate(comp_reviews),
            "sentiment_score": _sentiment_score(comp_reviews),
            "estimated_traffic": _estimated_traffic(c.review_count, float(c.rating) if c.rating else None),
            "strengths": c_strengths,
            "weaknesses": c_weaknesses,
        })

    return {"rows": rows, "own_rating": own_rating}


# ── Opportunity Detection ───────────────────────────────────────────────────


def get_opportunities(db: Session, shop_id: str) -> dict:
    """Detect competitive opportunities from competitor data."""
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    shop_name = shop.name if shop else SHOP_NAME_PLACEHOLDER

    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .all()
    )

    opportunities = []
    today = date.today()
    ninety_ago = today - timedelta(days=90)
    thirty_ago = today - timedelta(days=30)
    seven_ago = today - timedelta(days=7)

    # Get own shop rating for comparison
    own_avg = db.query(func.avg(Review.rating)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar()
    own_rating = round(float(own_avg), 1) if own_avg else None

    for c in competitors:
        comp_reviews = (
            db.query(CompetitorReview)
            .filter(CompetitorReview.competitor_id == c.id)
            .order_by(CompetitorReview.review_date.desc())
            .all()
        )

        # 1. Rating drop detection — compare against 90 days ago for reliable detection
        old_snap = (
            db.query(CompetitorSnapshot)
            .filter(CompetitorSnapshot.competitor_id == c.id, CompetitorSnapshot.date <= ninety_ago)
            .order_by(CompetitorSnapshot.date.desc())
            .first()
        )
        if old_snap and old_snap.rating and c.rating:
            drop = float(old_snap.rating) - float(c.rating)
            if drop >= 0.15:
                opportunities.append({
                    "id": f"drop-{c.id}",
                    "competitor": c.name,
                    "type": "rating_drop",
                    "priority": "hot" if drop >= 0.3 else "good",
                    "title": f"{c.name} dropped from {float(old_snap.rating):.1f} to {float(c.rating)} stars",
                    "description": f"Their rating has been declining and customers are looking for alternatives. This is your chance to attract them with targeted marketing.",
                    "why_it_matters": f"A {drop:.1f}-star decline means growing dissatisfaction — their customers are actively seeking new options in your area.",
                    "action": _generate_opportunity_action(c.name, "rating_drop", shop_name, drop),
                })

        # 2. Negative review spikes (2+ negative in last 7 days)
        recent_negative = [
            r for r in comp_reviews
            if r.review_date and r.review_date.date() >= seven_ago
            and r.sentiment == "negative"
        ]
        if len(recent_negative) >= 2:
            topics = _extract_negative_topics([r.text for r in recent_negative if r.text])
            topic_str = topics[0] if topics else "poor experience"
            opportunities.append({
                "id": f"neg-{c.id}",
                "competitor": c.name,
                "type": "negative_reviews",
                "priority": "hot" if len(recent_negative) >= 3 else "good",
                "title": f"{c.name} just got {len(recent_negative)} negative reviews about {topic_str}",
                "description": f"TARGET their unhappy customers with messaging that highlights your strengths in this area.",
                "why_it_matters": f"Multiple negative reviews in a short period signal a real problem — their customers are actively frustrated.",
                "action": _generate_opportunity_action(c.name, "negative_reviews", shop_name, topic_str),
            })

        # 3. Low response rate / engagement gap
        recent_reviews = [r for r in comp_reviews if r.review_date and r.review_date.date() >= thirty_ago]
        if len(comp_reviews) > 5 and len(recent_reviews) < 2:
            opportunities.append({
                "id": f"engage-{c.id}",
                "competitor": c.name,
                "type": "low_engagement",
                "priority": "good",
                "title": f"{c.name} hasn't gotten new reviews in weeks — they're losing engagement",
                "description": f"Time to increase your posting and visibility. Their audience is up for grabs.",
                "why_it_matters": "Low engagement means their marketing is stale. Customers are looking for something fresh.",
                "action": _generate_opportunity_action(c.name, "low_engagement", shop_name, None),
            })

        # 4. Service gap detection (from review analysis)
        neg_reviews = [r for r in comp_reviews if r.sentiment == "negative"]
        if len(neg_reviews) >= 3:
            gap_topics = _extract_negative_topics([r.text for r in neg_reviews if r.text])
            for topic in gap_topics[:1]:
                opportunities.append({
                    "id": f"gap-{c.id}-{topic[:4]}",
                    "competitor": c.name,
                    "type": "service_gap",
                    "priority": "fyi",
                    "title": f"{c.name} customers consistently complain about {topic}",
                    "description": f"If you excel in this area, promote it. Make it clear you're the better alternative.",
                    "why_it_matters": f"This is a recurring issue — not a one-time complaint. These customers want what you offer.",
                    "action": _generate_opportunity_action(c.name, "service_gap", shop_name, topic),
                })

        # 5. Rating advantage — your shop is notably better rated
        if own_rating and c.rating and own_rating > float(c.rating) + 0.2:
            advantage = round(own_rating - float(c.rating), 1)
            if len(neg_reviews) >= 2:
                opportunities.append({
                    "id": f"adv-{c.id}",
                    "competitor": c.name,
                    "type": "rating_advantage",
                    "priority": "good" if advantage >= 0.5 else "fyi",
                    "title": f"You're rated {advantage} stars higher than {c.name} — promote it",
                    "description": f"Your {own_rating}-star rating vs their {float(c.rating)}-star rating is a clear competitive advantage. Use it in your marketing.",
                    "why_it_matters": f"Customers compare ratings before visiting. Your {advantage}-star advantage is a powerful selling point.",
                    "action": _generate_opportunity_action(c.name, "service_gap", shop_name, "higher quality and better service"),
                })

    # Sort: hot first, then good, then fyi
    priority_order = {"hot": 0, "good": 1, "fyi": 2}
    opportunities.sort(key=lambda x: priority_order.get(x["priority"], 3))

    return {"opportunities": opportunities, "total": len(opportunities)}


def _extract_negative_topics(texts: list[str]) -> list[str]:
    """Extract topic keywords from negative review texts."""
    topic_map = {
        "slow service": ["wait", "slow", "long", "forever", "took"],
        "rude staff": ["rude", "unfriendly", "attitude", "ignored", "dismissive"],
        "high prices": ["expensive", "overpriced", "price", "cost", "pricey"],
        "poor quality": ["broken", "fell apart", "defect", "quality", "cheap"],
        "dirty store": ["dirty", "messy", "disorganized", "cluttered", "unclean"],
        "limited selection": ["limited", "small", "nothing", "empty", "bare"],
        "bad return policy": ["refund", "return", "exchange", "policy"],
        "unreliable hours": ["closed", "hours", "open", "schedule"],
    }

    found = Counter()
    for text in texts:
        lower = text.lower()
        for topic, keywords in topic_map.items():
            if any(kw in lower for kw in keywords):
                found[topic] += 1

    return [topic for topic, _ in found.most_common(3)]


def _generate_opportunity_action(comp_name: str, opp_type: str, shop_name: str, detail) -> dict:
    """Generate ready-to-use marketing actions for an opportunity."""
    if opp_type == "rating_drop":
        return {
            "instagram_post": (
                f"Looking for a new favorite local shop? Our community loves us — and we think you will too! "
                f"Stop by {shop_name} this weekend and see why customers keep coming "
                f"back. First-time visitors get 10% off! #ShopLocal #NewFavorite"
            ),
            "email_subject": f"Discover Why Locals Are Choosing {shop_name}",
            "email_body": (
                f"Hey there!\n\nLooking for a new go-to spot for unique finds? {shop_name} has "
                f"been earning rave reviews from the community. From curated accessories to handpicked "
                f"home goods, we pride ourselves on quality and service.\n\n"
                f"Come visit us this week and enjoy 15% off your first purchase! "
                f"We think you'll love what you find.\n\nSee you soon!"
            ),
            "promotion_idea": (
                f"\"New Neighbor\" Welcome Offer: 15% off for first-time visitors. Position this "
                f"as welcoming new customers from the area. Run targeted local ads this week while "
                f"{comp_name}'s rating is down."
            ),
        }
    elif opp_type == "negative_reviews":
        return {
            "instagram_post": (
                f"At {shop_name}, great service is our promise. Every customer matters, "
                f"every visit counts. That's why our community keeps coming back! "
                f"Come experience the difference. #CustomerFirst #QualityService #ShopLocal"
            ),
            "email_subject": f"This Is What Great Service Looks Like at {shop_name}",
            "email_body": (
                f"Hi!\n\nWe believe shopping should be a joy, not a chore. At {shop_name}, "
                f"our team is dedicated to making every visit special — from personalized "
                f"recommendations to a warm welcome at the door.\n\n"
                f"Don't take our word for it — come see for yourself! "
                f"This week, enjoy a free gift with any purchase over $30.\n\nWarm regards,\nThe {shop_name} Team"
            ),
            "promotion_idea": (
                f"\"Service Guarantee\" Campaign: Promote your customer service commitment. "
                f"Offer a free gift with purchase this week to drive foot traffic from "
                f"{comp_name}'s dissatisfied customers. Highlight {detail} as your differentiator."
            ),
        }
    elif opp_type == "low_engagement":
        return {
            "instagram_post": (
                f"New arrivals just dropped at {shop_name}! Fresh finds every week — "
                f"from handcrafted jewelry to one-of-a-kind home decor. Follow us for daily "
                f"updates and never miss a drop! #NewArrivals #AlwaysFresh #ShopLocal"
            ),
            "email_subject": f"Something New Every Week at {shop_name}",
            "email_body": (
                f"Hey!\n\nWhile some shops go quiet, we keep things exciting! "
                f"This week at {shop_name}, we've got fresh arrivals, exclusive finds, "
                f"and a special surprise for our loyal customers.\n\n"
                f"Stop by or shop online — and don't forget to follow us on Instagram "
                f"for daily updates!\n\nCheers,\nThe {shop_name} Team"
            ),
            "promotion_idea": (
                "\"Always Something New\" social media blitz: Post daily for the next 2 weeks "
                "showcasing new arrivals and behind-the-scenes content. Run a small Instagram "
                "ad targeting local shoppers. Fill the engagement gap your competitors are leaving."
            ),
        }
    else:  # service_gap
        return {
            "instagram_post": (
                f"Great {detail or 'service'} isn't a luxury — it's our standard. "
                f"At {shop_name}, we put our customers first, always. "
                f"Come experience the difference! #ShopLocal #QualityMatters"
            ),
            "email_subject": f"Why Customers Choose {shop_name} for {detail or 'Quality'}",
            "email_body": (
                f"Hi there!\n\nWe know what matters to you: {detail or 'a great experience'}. "
                f"That's why at {shop_name}, we go above and beyond to deliver exactly that.\n\n"
                f"From our carefully curated selection to our attentive team, every detail "
                f"is designed with you in mind.\n\nVisit us this week for something special!\n\n"
                f"Best,\nThe {shop_name} Team"
            ),
            "promotion_idea": (
                f"Highlight your strength in {detail or 'customer service'} across all channels. "
                f"Create a short video or photo series showing this in action. "
                f"Consider a targeted promotion that addresses exactly what competitors lack."
            ),
        }


# ── Competitor Review Feed ──────────────────────────────────────────────────


def get_competitor_review_feed(
    db: Session, shop_id: str,
    competitor_id: str | None = None,
    rating_filter: int | None = None,
    sentiment_filter: str | None = None,
) -> dict:
    """Live feed of all competitor reviews with filters."""
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    shop_name = shop.name if shop else SHOP_NAME_PLACEHOLDER

    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .all()
    )
    comp_map = {c.id: c.name for c in competitors}

    query = db.query(CompetitorReview)
    if competitor_id:
        query = query.filter(CompetitorReview.competitor_id == competitor_id)
    else:
        comp_ids = [c.id for c in competitors]
        query = query.filter(CompetitorReview.competitor_id.in_(comp_ids))

    if rating_filter:
        query = query.filter(CompetitorReview.rating == rating_filter)
    if sentiment_filter:
        query = query.filter(CompetitorReview.sentiment == sentiment_filter)

    reviews = query.order_by(CompetitorReview.review_date.desc()).limit(100).all()

    feed = []
    for r in reviews:
        capitalize_msg = None
        if r.rating and r.rating <= 2:
            capitalize_msg = _generate_capitalize_message(r.text, comp_map.get(r.competitor_id, "Competitor"), shop_name)

        feed.append({
            "id": r.id,
            "competitor_id": r.competitor_id,
            "competitor_name": comp_map.get(r.competitor_id, "Unknown"),
            "author_name": r.author_name,
            "rating": r.rating,
            "text": r.text,
            "review_date": r.review_date.isoformat() if r.review_date else None,
            "sentiment": r.sentiment,
            "capitalize_message": capitalize_msg,
        })

    # Filter options for the UI
    filter_options = {
        "competitors": [{"id": c.id, "name": c.name} for c in competitors],
        "ratings": [1, 2, 3, 4, 5],
        "sentiments": ["positive", "neutral", "negative"],
    }

    return {"reviews": feed, "total": len(feed), "filter_options": filter_options}


def _generate_capitalize_message(text: str | None, comp_name: str, shop_name: str) -> str:
    """Generate a marketing message to capitalize on a competitor's negative review."""
    if not text:
        return (
            f"Post on social media: 'At {shop_name}, every customer is our priority. "
            f"Come experience the difference! #ShopLocal'"
        )

    text_lower = text.lower()
    if any(w in text_lower for w in ["wait", "slow", "long"]):
        return (
            f"Post: 'Fast, friendly service every time at {shop_name}. "
            f"No waiting, no hassle — just a great experience. Come see us today! "
            f"#FastService #ShopLocal'"
        )
    elif any(w in text_lower for w in ["rude", "staff", "unfriendly", "ignored"]):
        return (
            f"Post: 'Our team at {shop_name} is here for YOU. Personalized service, "
            f"warm smiles, and expert advice — that's our promise. #CustomerFirst #ShopLocal'"
        )
    elif any(w in text_lower for w in ["expensive", "overpriced", "price"]):
        return (
            f"Post: 'Quality doesn't have to break the bank! At {shop_name}, "
            f"we offer curated finds at prices you'll love. #ValueForMoney #ShopLocal'"
        )
    elif any(w in text_lower for w in ["dirty", "messy", "disorganized"]):
        return (
            f"Post: 'A clean, organized, beautiful shopping experience — that's {shop_name}. "
            f"Come browse our carefully curated collection! #ShopLocal'"
        )
    else:
        return (
            f"Post: 'Looking for a better shopping experience? {shop_name} delivers "
            f"quality, service, and unique finds every single day. #ShopLocal #BetterChoice'"
        )


# ── Competitor Sentiment Analysis ───────────────────────────────────────────


def get_competitor_sentiment(db: Session, shop_id: str) -> dict:
    """Sentiment analysis for each competitor."""
    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .order_by(Competitor.rating.desc())
        .all()
    )

    results = []
    for c in competitors:
        reviews = (
            db.query(CompetitorReview)
            .filter(CompetitorReview.competitor_id == c.id)
            .all()
        )

        sentiment_breakdown = {"positive": 0, "neutral": 0, "negative": 0}
        for r in reviews:
            if r.sentiment in sentiment_breakdown:
                sentiment_breakdown[r.sentiment] += 1

        # Extract what customers love and hate
        positive_terms = _extract_terms_by_sentiment(reviews, "positive")
        negative_terms = _extract_terms_by_sentiment(reviews, "negative")

        # Trend: sentiment over time (last 6 months, monthly)
        trend = []
        today = date.today()
        for m in range(6):
            month_end = today.replace(day=1) - timedelta(days=30 * m)
            month_start = month_end - timedelta(days=30)
            month_reviews = [
                r for r in reviews
                if r.review_date and month_start <= r.review_date.date() <= month_end
            ]
            if month_reviews:
                pos = sum(1 for r in month_reviews if r.sentiment == "positive")
                trend.append({
                    "month": month_start.strftime("%b %Y"),
                    "positive_pct": round(pos / len(month_reviews) * 100, 1),
                    "total": len(month_reviews),
                })
            else:
                trend.append({
                    "month": month_start.strftime("%b %Y"),
                    "positive_pct": 0,
                    "total": 0,
                })
        trend.reverse()

        results.append({
            "id": c.id,
            "name": c.name,
            "rating": float(c.rating) if c.rating else None,
            "sentiment_breakdown": sentiment_breakdown,
            "positive_terms": positive_terms,
            "negative_terms": negative_terms,
            "sentiment_trend": trend,
            "overall_sentiment_score": _sentiment_score(reviews),
        })

    return {"competitors": results}


def _extract_terms_by_sentiment(reviews: list, sentiment: str) -> list[dict]:
    """Extract common terms from reviews of a specific sentiment."""
    stop_words = {
        "the", "a", "an", "is", "was", "are", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "up", "about", "into", "through",
        "this", "that", "these", "those", "i", "me", "my", "we", "our",
        "you", "your", "he", "she", "it", "they", "them", "his", "her",
        "its", "their", "what", "which", "who", "when", "where", "how",
        "all", "each", "every", "both", "few", "more", "most", "other",
        "some", "such", "no", "nor", "not", "only", "own", "same", "so",
        "than", "too", "very", "just", "but", "and", "or", "if", "here",
        "there", "also", "as", "well", "really", "get", "got", "one",
        "much", "even", "still", "back", "way", "like", "go", "going",
        "went", "come", "came", "make", "made", "take", "took", "think",
        "okay", "average", "nothing", "decent", "though", "overall",
    }

    texts = [r.text for r in reviews if r.text and r.sentiment == sentiment]
    all_words = []
    for text in texts:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        all_words.extend(w for w in words if w not in stop_words)

    counter = Counter(all_words)
    return [{"term": term, "count": count} for term, count in counter.most_common(10)]


# ── Market Position Map ─────────────────────────────────────────────────────


def get_market_position(db: Session, shop_id: str) -> dict:
    """Market position map data (x=review volume, y=rating)."""
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    shop_name = shop.name if shop else SHOP_NAME_PLACEHOLDER

    own_avg = db.query(func.avg(Review.rating)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar()
    own_count = db.query(func.count(Review.id)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar() or 0
    own_rating = round(float(own_avg), 1) if own_avg else 0

    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .all()
    )

    points = [{
        "name": shop_name,
        "is_own": True,
        "x": own_count,
        "y": own_rating,
        "review_count": own_count,
        "rating": own_rating,
    }]

    for c in competitors:
        points.append({
            "name": c.name,
            "is_own": False,
            "x": c.review_count,
            "y": float(c.rating) if c.rating else 0,
            "review_count": c.review_count,
            "rating": float(c.rating) if c.rating else 0,
        })

    # Calculate quadrant boundaries (median split)
    all_x = [p["x"] for p in points]
    all_y = [p["y"] for p in points]
    mid_x = sorted(all_x)[len(all_x) // 2] if all_x else 100
    mid_y = sorted(all_y)[len(all_y) // 2] if all_y else 4.0

    # Assign quadrants
    for p in points:
        if p["x"] >= mid_x and p["y"] >= mid_y:
            p["quadrant"] = "Market Leaders"
        elif p["x"] < mid_x and p["y"] >= mid_y:
            p["quadrant"] = "Hidden Gems"
        elif p["x"] >= mid_x and p["y"] < mid_y:
            p["quadrant"] = "Well-Known but Declining"
        else:
            p["quadrant"] = "Struggling"

    return {
        "points": points,
        "mid_x": mid_x,
        "mid_y": mid_y,
        "quadrants": {
            "top_right": "Market Leaders",
            "top_left": "Hidden Gems",
            "bottom_right": "Well-Known but Declining",
            "bottom_left": "Struggling",
        },
    }


# ── Weekly Report ───────────────────────────────────────────────────────────


def get_weekly_report(db: Session, shop_id: str) -> dict:
    """Auto-generated weekly competitor report."""
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    shop_name = shop.name if shop else SHOP_NAME_PLACEHOLDER
    today = date.today()
    week_ago = today - timedelta(days=7)

    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .all()
    )

    # Own shop stats this week
    own_new_reviews = (
        db.query(func.count(Review.id))
        .filter(
            Review.shop_id == shop_id,
            Review.is_own_shop.is_(True),
            Review.review_date >= datetime.combine(week_ago, datetime.min.time()),
        )
        .scalar() or 0
    )

    competitor_summaries = []
    opportunities_found = []

    for c in competitors:
        # New reviews this week
        new_reviews = (
            db.query(CompetitorReview)
            .filter(
                CompetitorReview.competitor_id == c.id,
                CompetitorReview.review_date >= datetime.combine(week_ago, datetime.min.time()),
            )
            .all()
        )

        new_negative = sum(1 for r in new_reviews if r.sentiment == "negative")
        new_positive = sum(1 for r in new_reviews if r.sentiment == "positive")

        # Rating change this week
        old_snap = (
            db.query(CompetitorSnapshot)
            .filter(CompetitorSnapshot.competitor_id == c.id, CompetitorSnapshot.date <= week_ago)
            .order_by(CompetitorSnapshot.date.desc())
            .first()
        )
        rating_change = None
        if old_snap and old_snap.rating and c.rating:
            rating_change = round(float(c.rating) - float(old_snap.rating), 1)

        comp_summary = {
            "name": c.name,
            "current_rating": float(c.rating) if c.rating else None,
            "rating_change": rating_change,
            "new_reviews": len(new_reviews),
            "new_positive": new_positive,
            "new_negative": new_negative,
        }
        competitor_summaries.append(comp_summary)

        # Check for opportunities
        if new_negative >= 2:
            opportunities_found.append(
                f"{c.name} got {new_negative} negative reviews this week — their customers may be looking for alternatives."
            )
        if rating_change and rating_change < -0.2:
            opportunities_found.append(
                f"{c.name}'s rating dropped by {abs(rating_change)} stars — time to increase your visibility."
            )

    # Recommended actions
    actions = []
    if opportunities_found:
        actions.append("Run a targeted social media campaign highlighting your strengths.")
        actions.append("Consider a limited-time promotion to attract new customers from competitors.")
    actions.append("Respond to all your new reviews promptly to maintain your response rate.")
    actions.append("Post at least 3 times on social media this week to stay visible.")

    # Summary text
    total_comp_reviews = sum(cs["new_reviews"] for cs in competitor_summaries)
    declining_comps = [cs["name"] for cs in competitor_summaries if cs["rating_change"] and cs["rating_change"] < -0.1]

    summary = f"This week in your market: Your competitors received {total_comp_reviews} new reviews total. "
    if declining_comps:
        summary += f"{', '.join(declining_comps)} {'are' if len(declining_comps) > 1 else 'is'} trending downward. "
    summary += f"You received {own_new_reviews} new review{'s' if own_new_reviews != 1 else ''}."

    return {
        "week_start": week_ago.isoformat(),
        "week_end": today.isoformat(),
        "summary": summary,
        "own_new_reviews": own_new_reviews,
        "competitor_summaries": competitor_summaries,
        "opportunities": opportunities_found,
        "recommended_actions": actions,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ── Marketing Responses (Database-backed) ───────────────────────────────────


def get_marketing_responses(db: Session, shop_id: str, status_filter: str | None = None) -> dict:
    """Get all stored marketing responses."""
    query = db.query(MarketingResponse).filter(MarketingResponse.shop_id == shop_id)
    if status_filter:
        query = query.filter(MarketingResponse.status == status_filter)
    responses = query.order_by(MarketingResponse.created_at.desc()).all()

    return {
        "responses": [
            {
                "id": r.id,
                "competitor_name": r.competitor_name,
                "weakness": r.weakness,
                "opportunity_type": r.opportunity_type,
                "instagram_post": r.instagram_post,
                "email_content": r.email_content,
                "promotion_idea": r.promotion_idea,
                "priority": r.priority,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in responses
        ],
        "total": len(responses),
        "by_status": {
            "new": sum(1 for r in responses if r.status == "new"),
            "saved": sum(1 for r in responses if r.status == "saved"),
            "used": sum(1 for r in responses if r.status == "used"),
        },
    }


def update_marketing_response_status(db: Session, shop_id: str, response_id: str, new_status: str) -> bool:
    """Update a marketing response status (new/saved/used)."""
    resp = (
        db.query(MarketingResponse)
        .filter(MarketingResponse.id == response_id, MarketingResponse.shop_id == shop_id)
        .first()
    )
    if not resp:
        return False
    resp.status = new_status
    db.commit()
    return True


def generate_capitalize_response(db: Session, shop_id: str, review_id: str) -> dict | None:
    """Generate a full marketing response from a specific negative competitor review."""
    review = db.query(CompetitorReview).filter(CompetitorReview.id == review_id).first()
    if not review:
        return None

    competitor = db.query(Competitor).filter(Competitor.id == review.competitor_id).first()
    if not competitor or competitor.shop_id != shop_id:
        return None

    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    shop_name = shop.name if shop else SHOP_NAME_PLACEHOLDER

    action = _generate_opportunity_action(
        competitor.name, "negative_reviews", shop_name, _extract_negative_topics([review.text])[0] if review.text else "poor experience"
    )

    # Store in database
    mr = MarketingResponse(
        shop_id=shop_id,
        competitor_id=competitor.id,
        competitor_name=competitor.name,
        weakness=review.text or "Negative customer experience",
        opportunity_type="negative_reviews",
        instagram_post=action["instagram_post"],
        email_content=action["email_body"],
        promotion_idea=action["promotion_idea"],
        priority="good",
        status="new",
    )
    db.add(mr)
    db.commit()

    return {
        "id": mr.id,
        "competitor_name": competitor.name,
        "weakness": mr.weakness,
        "instagram_post": mr.instagram_post,
        "email_content": mr.email_content,
        "promotion_idea": mr.promotion_idea,
        "priority": mr.priority,
        "status": mr.status,
    }


# ── Trend Alerts ──────────────────────────────────────────────────────────


def get_trend_alerts(db: Session, shop_id: str) -> dict:
    """Generate real-time trend alerts for competitive changes."""
    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .all()
    )
    today = date.today()
    seven_ago = today - timedelta(days=7)
    fourteen_ago = today - timedelta(days=14)
    thirty_ago = today - timedelta(days=30)
    sixty_ago = today - timedelta(days=60)

    alerts = []

    for c in competitors:
        comp_reviews = (
            db.query(CompetitorReview)
            .filter(CompetitorReview.competitor_id == c.id)
            .order_by(CompetitorReview.review_date.desc())
            .all()
        )

        # Alert 1: Negative review spike (3+ in 7 days)
        recent_negative = [
            r for r in comp_reviews
            if r.review_date and r.review_date.date() >= seven_ago
            and r.sentiment == "negative"
        ]
        if len(recent_negative) >= 3:
            alerts.append({
                "type": "negative_spike",
                "severity": "critical",
                "icon": "1F6A8",
                "competitor": c.name,
                "title": f"{c.name} received {len(recent_negative)} negative reviews this week",
                "description": f"Customers are complaining — this is a prime opportunity to attract their dissatisfied base.",
                "timestamp": max(r.review_date for r in recent_negative).isoformat() if recent_negative else None,
                "data": {"count": len(recent_negative)},
            })

        # Alert 2: Rating drop > 0.2 in last month
        old_snap = (
            db.query(CompetitorSnapshot)
            .filter(CompetitorSnapshot.competitor_id == c.id, CompetitorSnapshot.date <= thirty_ago)
            .order_by(CompetitorSnapshot.date.desc())
            .first()
        )
        if old_snap and old_snap.rating and c.rating:
            drop = float(old_snap.rating) - float(c.rating)
            if drop >= 0.2:
                alerts.append({
                    "type": "rating_drop",
                    "severity": "warning",
                    "icon": "1F4C9",
                    "competitor": c.name,
                    "title": f"{c.name} rating dropped {drop:.1f} stars (from {float(old_snap.rating):.1f} to {float(c.rating):.1f})",
                    "description": f"A sustained decline in rating signals growing customer dissatisfaction.",
                    "timestamp": today.isoformat(),
                    "data": {"from_rating": float(old_snap.rating), "to_rating": float(c.rating), "drop": drop},
                })

        # Alert 3: Sentiment shift — compare last 14 days vs prior 14 days
        recent_reviews = [
            r for r in comp_reviews
            if r.review_date and r.review_date.date() >= fourteen_ago
        ]
        older_reviews = [
            r for r in comp_reviews
            if r.review_date and fourteen_ago > r.review_date.date() >= sixty_ago
        ]
        if len(recent_reviews) >= 3 and len(older_reviews) >= 3:
            recent_pos = sum(1 for r in recent_reviews if r.sentiment == "positive") / len(recent_reviews)
            older_pos = sum(1 for r in older_reviews if r.sentiment == "positive") / len(older_reviews)
            shift = round((recent_pos - older_pos) * 100, 1)
            if shift <= -20:
                alerts.append({
                    "type": "sentiment_decline",
                    "severity": "warning",
                    "icon": "1F61F",
                    "competitor": c.name,
                    "title": f"{c.name} sentiment dropped {abs(shift)}% recently",
                    "description": f"Positive sentiment fell from {round(older_pos * 100)}% to {round(recent_pos * 100)}%. Their customers are less happy.",
                    "timestamp": today.isoformat(),
                    "data": {"old_pct": round(older_pos * 100), "new_pct": round(recent_pos * 100)},
                })
            elif shift >= 20:
                alerts.append({
                    "type": "sentiment_rise",
                    "severity": "info",
                    "icon": "1F4C8",
                    "competitor": c.name,
                    "title": f"{c.name} sentiment improved {shift}% — watch out",
                    "description": f"They're getting better feedback. Monitor closely and strengthen your own service.",
                    "timestamp": today.isoformat(),
                    "data": {"old_pct": round(older_pos * 100), "new_pct": round(recent_pos * 100)},
                })

        # Alert 4: Review volume surge (2x+ more reviews than usual)
        recent_count = len([r for r in comp_reviews if r.review_date and r.review_date.date() >= seven_ago])
        older_weekly = len([r for r in comp_reviews if r.review_date and fourteen_ago <= r.review_date.date() < seven_ago])
        if recent_count >= 5 and older_weekly > 0 and recent_count >= older_weekly * 2:
            alerts.append({
                "type": "review_surge",
                "severity": "info",
                "icon": "1F4E2",
                "competitor": c.name,
                "title": f"{c.name} got {recent_count} reviews this week (up {round(recent_count / older_weekly, 1)}x)",
                "description": f"They may be running a campaign or something happened. Keep an eye on what's driving it.",
                "timestamp": today.isoformat(),
                "data": {"this_week": recent_count, "last_week": older_weekly},
            })

        # Alert 5: Competitor went quiet (0 reviews in 14 days when usually active)
        total_reviews = len(comp_reviews)
        recent_any = len([r for r in comp_reviews if r.review_date and r.review_date.date() >= fourteen_ago])
        if total_reviews >= 10 and recent_any == 0:
            alerts.append({
                "type": "gone_quiet",
                "severity": "info",
                "icon": "1F4A4",
                "competitor": c.name,
                "title": f"{c.name} has had zero new reviews in 2 weeks",
                "description": f"They might be losing visibility. Fill the gap with your own marketing push.",
                "timestamp": today.isoformat(),
                "data": {"total_reviews": total_reviews},
            })

    # Sort by severity
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 3))

    return {"alerts": alerts, "total": len(alerts)}


# ── Response Analysis ─────────────────────────────────────────────────────


def get_response_analysis(db: Session, shop_id: str) -> dict:
    """Analyze review response rates and times — your shop vs competitors."""
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    shop_name = shop.name if shop else SHOP_NAME_PLACEHOLDER

    # Own shop response metrics
    own_reviews = (
        db.query(Review)
        .filter(Review.shop_id == shop_id, Review.is_own_shop.is_(True))
        .all()
    )
    own_total = len(own_reviews)
    own_responded = sum(1 for r in own_reviews if r.response_text)
    own_response_rate = round(own_responded / own_total * 100, 1) if own_total > 0 else 0

    # Response rate by sentiment
    own_neg = [r for r in own_reviews if r.sentiment == "negative"]
    own_neg_responded = sum(1 for r in own_neg if r.response_text)
    own_neg_response_rate = round(own_neg_responded / len(own_neg) * 100, 1) if own_neg else 0

    own_pos = [r for r in own_reviews if r.sentiment == "positive"]
    own_pos_responded = sum(1 for r in own_pos if r.response_text)
    own_pos_response_rate = round(own_pos_responded / len(own_pos) * 100, 1) if own_pos else 0

    # Competitor response metrics (estimated from review patterns)
    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .all()
    )

    comp_analysis = []
    for c in competitors:
        comp_reviews = (
            db.query(CompetitorReview)
            .filter(CompetitorReview.competitor_id == c.id)
            .all()
        )
        total = len(comp_reviews)
        # Estimate response rate from high-rated reviews (as a proxy)
        high_rated = sum(1 for r in comp_reviews if r.rating and r.rating >= 4)
        est_response_rate = round(high_rated / total * 100, 1) if total > 0 else 0

        neg = [r for r in comp_reviews if r.sentiment == "negative"]
        neg_count = len(neg)
        avg_neg_rating = round(sum(r.rating for r in neg if r.rating) / neg_count, 1) if neg_count > 0 else 0

        comp_analysis.append({
            "name": c.name,
            "total_reviews": total,
            "estimated_response_rate": est_response_rate,
            "negative_review_count": neg_count,
            "avg_negative_rating": avg_neg_rating,
        })

    # Recommendations
    tips = []
    if own_neg_response_rate < 80:
        tips.append({
            "icon": "26A0",
            "text": f"You've only responded to {own_neg_response_rate}% of negative reviews. Aim for 100% — every response shows you care.",
            "priority": "high",
        })
    if own_response_rate < 50:
        tips.append({
            "icon": "1F4AC",
            "text": f"Your overall response rate is {own_response_rate}%. Responding to reviews (even positive ones) boosts engagement and visibility.",
            "priority": "medium",
        })
    if own_pos_response_rate < 30:
        tips.append({
            "icon": "2B50",
            "text": "Thank your positive reviewers! A quick thank-you reply encourages repeat visits and more reviews.",
            "priority": "low",
        })
    if not tips:
        tips.append({
            "icon": "1F389",
            "text": "Great job! You're staying on top of your review responses. Keep it up!",
            "priority": "low",
        })

    return {
        "own": {
            "name": shop_name,
            "total_reviews": own_total,
            "responded": own_responded,
            "response_rate": own_response_rate,
            "negative_response_rate": own_neg_response_rate,
            "positive_response_rate": own_pos_response_rate,
            "negative_count": len(own_neg),
            "positive_count": len(own_pos),
        },
        "competitors": comp_analysis,
        "tips": tips,
    }


# ── Competitive Advantages ────────────────────────────────────────────────


def get_competitive_advantages(db: Session, shop_id: str) -> dict:
    """Identify your specific advantages over each competitor."""
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    shop_name = shop.name if shop else SHOP_NAME_PLACEHOLDER

    own_reviews = (
        db.query(Review)
        .filter(Review.shop_id == shop_id, Review.is_own_shop.is_(True))
        .all()
    )
    own_avg = db.query(func.avg(Review.rating)).filter(
        Review.shop_id == shop_id, Review.is_own_shop.is_(True)
    ).scalar()
    own_rating = round(float(own_avg), 1) if own_avg else 0
    own_strengths, own_weaknesses = _extract_strengths_weaknesses(own_reviews)
    own_sentiment = _sentiment_score([type("R", (), {"sentiment": r.sentiment})() for r in own_reviews])

    competitors = (
        db.query(Competitor)
        .filter(Competitor.shop_id == shop_id)
        .all()
    )

    advantages = []
    for c in competitors:
        comp_reviews = (
            db.query(CompetitorReview)
            .filter(CompetitorReview.competitor_id == c.id)
            .all()
        )
        c_rating = float(c.rating) if c.rating else 0
        c_strengths, c_weaknesses = _extract_strengths_weaknesses(comp_reviews)
        c_sentiment = _sentiment_score(comp_reviews)

        your_wins = []
        their_wins = []

        # Rating comparison
        if own_rating > c_rating + 0.1:
            your_wins.append({
                "metric": "Rating",
                "yours": f"{own_rating}/5",
                "theirs": f"{c_rating}/5",
                "gap": f"+{round(own_rating - c_rating, 1)} stars",
            })
        elif c_rating > own_rating + 0.1:
            their_wins.append({
                "metric": "Rating",
                "yours": f"{own_rating}/5",
                "theirs": f"{c_rating}/5",
                "gap": f"-{round(c_rating - own_rating, 1)} stars",
            })

        # Sentiment comparison
        if own_sentiment > c_sentiment + 5:
            your_wins.append({
                "metric": "Positive Sentiment",
                "yours": f"{own_sentiment}%",
                "theirs": f"{c_sentiment}%",
                "gap": f"+{round(own_sentiment - c_sentiment, 1)}%",
            })
        elif c_sentiment > own_sentiment + 5:
            their_wins.append({
                "metric": "Positive Sentiment",
                "yours": f"{own_sentiment}%",
                "theirs": f"{c_sentiment}%",
                "gap": f"-{round(c_sentiment - own_sentiment, 1)}%",
            })

        # Weakness exploitation — things they're bad at that you're good at
        exploitable = []
        for weakness in c_weaknesses:
            if weakness != "No significant weaknesses" and weakness in own_strengths:
                exploitable.append(weakness)

        # Things they're strong at that you're weak at
        threats = []
        for strength in c_strengths:
            if strength != "No clear strengths identified" and strength in own_weaknesses:
                threats.append(strength)

        # Action advice
        advice = []
        if your_wins:
            advice.append(f"Promote your {your_wins[0]['metric'].lower()} advantage in local marketing.")
        if exploitable:
            advice.append(f"Highlight your {exploitable[0].lower()} — their customers want this.")
        if threats:
            advice.append(f"Improve your {threats[0].lower()} — {c.name} is beating you here.")
        if not advice:
            advice.append("Monitor this competitor and maintain your competitive position.")

        advantages.append({
            "competitor": c.name,
            "competitor_rating": c_rating,
            "your_wins": your_wins,
            "their_wins": their_wins,
            "exploitable_weaknesses": exploitable,
            "threats": threats,
            "your_strengths": own_strengths,
            "their_weaknesses": c_weaknesses,
            "advice": advice,
            "overall_position": "ahead" if len(your_wins) > len(their_wins) else ("behind" if len(their_wins) > len(your_wins) else "even"),
        })

    # Summary stats
    ahead_count = sum(1 for a in advantages if a["overall_position"] == "ahead")
    behind_count = sum(1 for a in advantages if a["overall_position"] == "behind")

    return {
        "shop_name": shop_name,
        "own_rating": own_rating,
        "advantages": advantages,
        "summary": {
            "ahead_of": ahead_count,
            "behind": behind_count,
            "even_with": len(advantages) - ahead_count - behind_count,
            "total_competitors": len(advantages),
        },
    }
