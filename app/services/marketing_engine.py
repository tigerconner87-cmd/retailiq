"""AI Marketing Content Engine for RetailIQ.

Generates ready-to-use marketing content based on actual shop data:
content calendar, social posts, email campaigns, promotions, and
performance tracking.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Competitor, CompetitorReview, Customer, DailySnapshot,
    MarketingResponse, Product, Shop, Transaction, TransactionItem,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_top_products(db: Session, shop_id: str, days: int = 30, limit: int = 10):
    """Get top-selling products by units sold in the last N days."""
    since = datetime.combine(date.today() - timedelta(days=days), datetime.min.time())
    rows = (
        db.query(
            Product.name,
            Product.category,
            func.sum(TransactionItem.quantity).label("units"),
            func.sum(TransactionItem.total).label("revenue"),
            Product.price,
        )
        .join(TransactionItem, TransactionItem.product_id == Product.id)
        .join(Transaction, TransactionItem.transaction_id == Transaction.id)
        .filter(Transaction.shop_id == shop_id, Transaction.timestamp >= since)
        .group_by(Product.id, Product.name, Product.category, Product.price)
        .order_by(func.sum(TransactionItem.quantity).desc())
        .limit(limit)
        .all()
    )
    return [
        {"name": r.name, "category": r.category, "units": int(r.units),
         "revenue": float(r.revenue), "price": float(r.price)}
        for r in rows
    ]


def _get_weakest_day(db: Session, shop_id: str) -> dict:
    """Find the day of week with lowest average transactions."""
    since = date.today() - timedelta(days=60)
    rows = (
        db.query(DailySnapshot.date, DailySnapshot.transaction_count)
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= since)
        .all()
    )
    day_totals = {}
    day_counts = {}
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for r in rows:
        dow = r.date.weekday()
        day_totals[dow] = day_totals.get(dow, 0) + r.transaction_count
        day_counts[dow] = day_counts.get(dow, 0) + 1

    if not day_totals:
        return {"day": "Tuesday", "avg_tx": 40}

    weakest = min(day_totals.keys(), key=lambda d: day_totals[d] / max(1, day_counts[d]))
    return {
        "day": day_names[weakest],
        "avg_tx": round(day_totals[weakest] / max(1, day_counts[weakest])),
    }


def _get_customer_segments(db: Session, shop_id: str) -> dict:
    """Get customer counts by segment."""
    segments = (
        db.query(Customer.segment, func.count(Customer.id))
        .filter(Customer.shop_id == shop_id)
        .group_by(Customer.segment)
        .all()
    )
    result = {"vip": 0, "regular": 0, "at_risk": 0, "lost": 0, "total": 0}
    for seg, count in segments:
        if seg in result:
            result[seg] = count
        result["total"] += count
    return result


def _get_at_risk_customers(db: Session, shop_id: str) -> int:
    """Count customers who haven't visited in 30+ days."""
    cutoff = datetime.combine(date.today() - timedelta(days=30), datetime.min.time())
    return (
        db.query(func.count(Customer.id))
        .filter(
            Customer.shop_id == shop_id,
            Customer.last_seen < cutoff,
            Customer.visit_count > 0,
        )
        .scalar()
    ) or 0


def _get_competitor_weaknesses(db: Session, shop_id: str) -> list[dict]:
    """Get competitors with recent negative reviews."""
    comps = db.query(Competitor).filter(Competitor.shop_id == shop_id).all()
    weaknesses = []
    week_ago = datetime.now() - timedelta(days=14)

    for c in comps:
        neg_reviews = (
            db.query(CompetitorReview)
            .filter(
                CompetitorReview.competitor_id == c.id,
                CompetitorReview.sentiment == "negative",
                CompetitorReview.review_date >= week_ago,
            )
            .all()
        )
        if neg_reviews:
            topics = set()
            for r in neg_reviews:
                txt = (r.text or "").lower()
                if "service" in txt or "staff" in txt or "rude" in txt or "wait" in txt:
                    topics.add("poor customer service")
                if "price" in txt or "expensive" in txt or "overpriced" in txt:
                    topics.add("high prices")
                if "quality" in txt or "broke" in txt or "fell apart" in txt:
                    topics.add("quality issues")
                if "dirty" in txt or "messy" in txt or "disorganized" in txt:
                    topics.add("messy store")
                if "hours" in txt or "closed" in txt:
                    topics.add("unreliable hours")
            weaknesses.append({
                "name": c.name,
                "rating": float(c.rating) if c.rating else 0,
                "neg_count": len(neg_reviews),
                "topics": list(topics) if topics else ["negative experience"],
            })

    return sorted(weaknesses, key=lambda w: w["neg_count"], reverse=True)


def _get_shop_name(db: Session, shop_id: str) -> str:
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    return shop.name if shop else "Our Shop"


def _get_monthly_revenue(db: Session, shop_id: str) -> float:
    """Get current month's total revenue."""
    month_start = date.today().replace(day=1)
    result = (
        db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0))
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= month_start)
        .scalar()
    )
    return float(result) if result else 0.0


def _get_season() -> str:
    """Get current season name."""
    month = date.today().month
    if month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    elif month in (9, 10, 11):
        return "fall"
    return "winter"


# ── Content Calendar ─────────────────────────────────────────────────────────

def get_content_calendar(db: Session, shop_id: str) -> dict:
    """Generate a weekly content calendar with 1-2 posts per day."""
    shop_name = _get_shop_name(db, shop_id)
    top_products = _get_top_products(db, shop_id, days=14, limit=8)
    weaknesses = _get_competitor_weaknesses(db, shop_id)
    at_risk = _get_at_risk_customers(db, shop_id)
    segments = _get_customer_segments(db, shop_id)
    season = _get_season()

    p = top_products  # shorthand
    p1 = p[0]["name"] if len(p) > 0 else "our top product"
    p2 = p[1]["name"] if len(p) > 1 else "our popular item"
    p3 = p[2]["name"] if len(p) > 2 else "our featured product"
    p4 = p[3]["name"] if len(p) > 3 else "our best seller"
    p5 = p[4]["name"] if len(p) > 4 else "our newest item"

    comp_weakness = ""
    comp_name = ""
    if weaknesses:
        comp_name = weaknesses[0]["name"]
        comp_weakness = weaknesses[0]["topics"][0] if weaknesses[0]["topics"] else "poor reviews"

    season_adj = {"spring": "Fresh", "summer": "Sunny", "fall": "Cozy", "winter": "Warm"}
    season_emoji = {"spring": "🌸", "summer": "☀️", "fall": "🍂", "winter": "❄️"}
    s_adj = season_adj.get(season, "Great")
    s_emoji = season_emoji.get(season, "✨")

    today = date.today()
    monday = today - timedelta(days=today.weekday())

    days = []
    day_content = [
        # Monday
        [
            {
                "platform": "instagram",
                "time": "10:00 AM",
                "content": f"New week, new arrivals! Our {p1} is flying off the shelves 🔥 Come grab yours before they're gone! #ShopLocal #NewWeek #{shop_name.replace(' ', '')}",
                "content_type": "product_spotlight",
            },
        ],
        # Tuesday
        [
            {
                "platform": "email",
                "time": "2:00 PM",
                "content": f"Win-back email to {at_risk} customers who haven't visited in 30+ days — Subject: \"We miss you! Here's 15% off your next visit\"",
                "content_type": "win_back",
            },
            {
                "platform": "instagram",
                "time": "6:00 PM",
                "content": f"Tuesday Treat! 🎁 Pop in today and check out our {p2} — customers can't stop raving about {'them' if 'Set' in p2 or 'Jeans' in p2 else 'it'}! #TuesdayTreat #ShopLocal",
                "content_type": "engagement",
            },
        ],
        # Wednesday
        [
            {
                "platform": "instagram",
                "time": "6:00 PM",
                "content": f"Did you know our {p3} is rated #1 by our customers? See why everyone's talking about {'them' if 'Set' in p3 or 'Jeans' in p3 else 'it'} 👖 #BestSeller #CustomerFavorite",
                "content_type": "social_proof",
            },
        ],
        # Thursday
        [
            {
                "platform": "facebook",
                "time": "11:00 AM",
                "content": f"While other shops struggle with service (looking at the reviews 👀), we pride ourselves on making every visit special. Come experience the {shop_name} difference! #CustomerFirst #QualityMatters",
                "content_type": "competitive_edge",
            },
            {
                "platform": "instagram",
                "time": "5:00 PM",
                "content": f"{s_adj} picks for the season! {s_emoji} Our {p4} is perfect for {season}. Stop by and see what's new! #SeasonalStyle #ShopLocal",
                "content_type": "seasonal",
            },
        ],
        # Friday
        [
            {
                "platform": "instagram",
                "time": "9:00 AM",
                "content": f"Weekend ready! 🛍️ Check out our top 5 picks for the perfect weekend: {p1}, {p2}, {p3}, {p4}, and {p5}. Which one is your must-have?",
                "content_type": "product_spotlight",
            },
        ],
        # Saturday
        [
            {
                "platform": "instagram_story",
                "time": "12:00 PM",
                "content": f"Behind the scenes at {shop_name}! 📦 Watch us unpack this week's new arrivals. Swipe up to shop! #BTS #NewArrivals #ShopLocal",
                "content_type": "behind_scenes",
            },
            {
                "platform": "instagram",
                "time": "4:00 PM",
                "content": f"Saturday shopping vibes ✨ Our VIP customers ({segments['vip']} strong!) know the best finds are here. Join them today! #SaturdayShopping #VIPLife",
                "content_type": "engagement",
            },
        ],
        # Sunday
        [
            {
                "platform": "email",
                "time": "5:00 PM",
                "content": f"Weekly recap email — This week's bestsellers: {p1}, {p2}, {p3}. Plus, a sneak peek at what's coming next week! Subject: \"This Week at {shop_name} + What's Next 🎉\"",
                "content_type": "newsletter",
            },
        ],
    ]

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    for i, name in enumerate(day_names):
        d = monday + timedelta(days=i)
        days.append({
            "day": name,
            "date": d.isoformat(),
            "posts": day_content[i],
        })

    return {
        "week_start": monday.isoformat(),
        "week_end": (monday + timedelta(days=6)).isoformat(),
        "days": days,
        "stats": {
            "total_posts": sum(len(d["posts"]) for d in days),
            "platforms": {"instagram": 6, "facebook": 1, "email": 2, "instagram_story": 1},
        },
    }


# ── Social Posts Library ─────────────────────────────────────────────────────

def get_social_posts(db: Session, shop_id: str, category: str = None) -> dict:
    """Generate a library of 20+ social media posts by category."""
    shop_name = _get_shop_name(db, shop_id)
    top_products = _get_top_products(db, shop_id, days=30, limit=10)
    weaknesses = _get_competitor_weaknesses(db, shop_id)
    segments = _get_customer_segments(db, shop_id)
    season = _get_season()
    hashtag = f"#{shop_name.replace(' ', '')}"

    p = top_products
    posts = []

    # ── Product Spotlight (5 posts)
    for i in range(min(5, len(p))):
        prod = p[i]
        templates = [
            f"✨ SPOTLIGHT: Our {prod['name']} is a customer favorite! {prod['units']} sold this month and counting. Come see why everyone loves {'them' if 'Set' in prod['name'] or 'Jeans' in prod['name'] else 'it'}! {hashtag} #ProductSpotlight #ShopLocal",
            f"🔥 TRENDING: {prod['name']} — one of our most popular items! Handpicked quality at ${prod['price']:.0f}. Limited stock, don't miss out! {hashtag} #TrendingNow #MustHave",
            f"💎 Why do customers keep coming back for our {prod['name']}? Because quality speaks for itself. ${prod['price']:.0f} well spent! {hashtag} #QualityFirst #BestSeller",
            f"🛍️ Best seller alert! Our {prod['name']} ({prod['category']}) has been flying off the shelves. Get yours before they're gone! {hashtag} #BestSeller #ShopSmall",
            f"⭐ Customer pick of the week: {prod['name']}! {prod['units']} happy customers can't be wrong. Come in and see for yourself! {hashtag} #CustomerFavorite #WeeklyPick",
        ]
        posts.append({
            "id": f"ps-{i}",
            "category": "product_spotlight",
            "platform": "instagram",
            "best_time": ["10:00 AM", "2:00 PM", "6:00 PM", "12:00 PM", "4:00 PM"][i],
            "caption": templates[i],
            "hashtags": f"#ShopLocal #{prod['category'].replace(' ', '')} {hashtag} #SmallBusiness #RetailTherapy",
            "product_name": prod["name"],
        })

    # ── Customer Appreciation (3 posts)
    appreciation_posts = [
        {
            "caption": f"💚 To our {segments['total']} amazing customers — THANK YOU! Every visit, every purchase, every smile makes what we do worthwhile. You're not just customers, you're family. {hashtag} #ThankYou #CustomerAppreciation #ShopLocal",
            "best_time": "11:00 AM",
        },
        {
            "caption": f"🌟 Shoutout to our {segments['vip']} VIP customers! You've been with us through thick and thin, and we see you. Something special is coming your way soon... stay tuned! {hashtag} #VIPLove #LoyalCustomers",
            "best_time": "3:00 PM",
        },
        {
            "caption": f"📸 We love seeing your purchases in action! Tag us in your photos and show us how you style your {shop_name} finds. Best photo this week gets a surprise gift! {hashtag} #ShowUs #CustomerStyle #Regram",
            "best_time": "5:00 PM",
        },
    ]
    for i, ap in enumerate(appreciation_posts):
        posts.append({
            "id": f"ca-{i}",
            "category": "customer_appreciation",
            "platform": "instagram",
            "best_time": ap["best_time"],
            "caption": ap["caption"],
            "hashtags": f"#CustomerLove #ThankYou {hashtag} #Community #ShopSmall",
        })

    # ── Behind the Scenes (3 posts)
    bts_posts = [
        {
            "caption": f"📦 Unboxing day at {shop_name}! Watch us reveal this week's new arrivals. Hint: there's something in here you've been asking for... 👀 {hashtag} #BTS #NewArrivals #Unboxing",
            "best_time": "12:00 PM",
            "platform": "instagram_story",
        },
        {
            "caption": f"☕ A day in the life at {shop_name}! From morning coffee to final customer goodbye, here's what makes our little shop tick. It's not just a store — it's a passion. {hashtag} #DayInTheLife #ShopOwnerLife #BehindTheScenes",
            "best_time": "9:00 AM",
            "platform": "instagram",
        },
        {
            "caption": f"🎨 How we curate our collection: every item at {shop_name} is handpicked with YOU in mind. Quality over quantity, always. Here's a peek at our selection process! {hashtag} #Curated #HandPicked #QualityMatters",
            "best_time": "2:00 PM",
            "platform": "instagram",
        },
    ]
    for i, bp in enumerate(bts_posts):
        posts.append({
            "id": f"bts-{i}",
            "category": "behind_scenes",
            "platform": bp["platform"],
            "best_time": bp["best_time"],
            "caption": bp["caption"],
            "hashtags": f"#BehindTheScenes #ShopOwnerLife {hashtag} #SmallBiz #Authentic",
        })

    # ── Competitive Edge (4 posts)
    comp_posts = [
        f"🏆 What sets us apart? Our customers tell us it's the service. While some shops leave you waiting, we make every visit personal. Come see the difference! {hashtag} #CustomerFirst #ServiceMatters #ShopLocal",
        f"⭐ 4.3+ stars and counting! Our customers consistently rate us as one of the best shops in the area. We don't just sell products — we build relationships. {hashtag} #TopRated #TrustedShop #QualityService",
        f"💡 Tired of overpriced, low-quality finds? At {shop_name}, every item is quality-checked and fairly priced. No surprises, no disappointments. Just great products. {hashtag} #FairPrices #QualityGuarantee #ValueForMoney",
        f"🏠 Shopping should be a joy, not a chore! Clean store, organized shelves, friendly staff, and unique finds — that's the {shop_name} promise. Open every day, reliable hours. {hashtag} #ShoppingJoy #ReliableHours #WelcomingStore",
    ]
    for i, caption in enumerate(comp_posts):
        posts.append({
            "id": f"ce-{i}",
            "category": "competitive_edge",
            "platform": ["instagram", "facebook", "instagram", "facebook"][i],
            "best_time": ["11:00 AM", "1:00 PM", "5:00 PM", "10:00 AM"][i],
            "caption": caption,
            "hashtags": f"#CompetitiveEdge #BetterChoice {hashtag} #ShopLocal #StandOut",
        })

    # ── Seasonal/Trending (3 posts)
    season_map = {
        "spring": [
            f"🌸 Spring is here and so are our fresh new arrivals! Bright colors, light fabrics, and that fresh-start energy. Pop in and refresh your {season} wardrobe! {hashtag} #SpringCollection #FreshStart #NewSeason",
            f"🌷 {season.capitalize()} cleaning? Don't forget to refresh your style too! Our {p[0]['name'] if p else 'new collection'} is perfect for the season. {hashtag} #SpringRefresh #SeasonalStyle",
            f"🌿 Sustainable, curated, and ready for {season}. Our handpicked collection is designed to make you feel good AND do good. {hashtag} #SustainableFashion #SpringVibes #EcoFriendly",
        ],
        "summer": [
            f"☀️ Summer vibes! Beat the heat with our latest picks. Cool fabrics, hot styles! {hashtag} #SummerStyle #BeatTheHeat #HotPicks",
            f"🏖️ Summer essential: our {p[0]['name'] if p else 'top picks'}! Perfect for those long sunny days. {hashtag} #SummerEssentials #MustHave",
            f"🌊 Making waves this summer with our curated collection. Fresh finds for sunny days ahead! {hashtag} #SummerCollection #FreshFinds",
        ],
        "fall": [
            f"🍂 Fall is here! Cozy sweaters, warm colors, and your favorite {shop_name} finds. Come get cozy with us! {hashtag} #FallVibes #CozyUp #AutumnStyle",
            f"🎃 Falling for our new collection! Our {p[0]['name'] if p else 'seasonal picks'} are perfect for the cooler days ahead. {hashtag} #FallFavorites #SeasonalStyle",
            f"☕ Pumpkin spice and everything nice — including our curated fall collection. Warm up with us! {hashtag} #FallCollection #WarmUp #ShopLocal",
        ],
        "winter": [
            f"❄️ Winter warmth starts here! Cozy up with our handpicked collection of winter essentials. Perfect for gifts or self-care! {hashtag} #WinterWarmth #CozyVibes #GiftIdeas",
            f"🎁 Gift shopping? We've got you covered! Our {p[0]['name'] if p else 'curated gifts'} makes the perfect present. {hashtag} #GiftGuide #PerfectPresent #HolidayShopping",
            f"⛄ Baby it's cold outside... but it's warm and welcoming at {shop_name}! Come browse our winter collection over a cup of cocoa. {hashtag} #WinterShopping #WarmWelcome",
        ],
    }
    for i, caption in enumerate(season_map.get(season, season_map["winter"])):
        posts.append({
            "id": f"st-{i}",
            "category": "seasonal",
            "platform": ["instagram", "facebook", "instagram"][i],
            "best_time": ["10:00 AM", "12:00 PM", "4:00 PM"][i],
            "caption": caption,
            "hashtags": f"#{season.capitalize()} #SeasonalStyle {hashtag} #ShopLocal #Trending",
        })

    # ── User Generated Content Prompts (2 posts)
    ugc_posts = [
        f"📸 CONTEST TIME! Share a photo of your favorite {shop_name} purchase and tag us! Best photo this week wins a $25 gift card. GO! {hashtag} #Contest #ShareYourStyle #WinPrizes #CustomerPhotos",
        f"💬 What's YOUR favorite {shop_name} product? Drop it in the comments! We're curious what our community loves most. Top answer gets featured in our next post! {hashtag} #TellUs #CommunityVoice #Favorites",
    ]
    for i, caption in enumerate(ugc_posts):
        posts.append({
            "id": f"ugc-{i}",
            "category": "ugc",
            "platform": "instagram",
            "best_time": ["3:00 PM", "6:00 PM"][i],
            "caption": caption,
            "hashtags": f"#UGC #Community {hashtag} #ShareYourStyle #CustomerLove",
        })

    # Filter by category if specified
    if category:
        posts = [p for p in posts if p["category"] == category]

    categories = [
        {"id": "product_spotlight", "label": "Product Spotlight", "count": 5, "emoji": "✨"},
        {"id": "customer_appreciation", "label": "Customer Appreciation", "count": 3, "emoji": "💚"},
        {"id": "behind_scenes", "label": "Behind the Scenes", "count": 3, "emoji": "📦"},
        {"id": "competitive_edge", "label": "Competitive Edge", "count": 4, "emoji": "🏆"},
        {"id": "seasonal", "label": f"Seasonal ({season.capitalize()})", "count": 3, "emoji": "🗓️"},
        {"id": "ugc", "label": "User Generated Content", "count": 2, "emoji": "📸"},
    ]

    return {"posts": posts, "total": len(posts), "categories": categories}


# ── Email Campaigns ──────────────────────────────────────────────────────────

def get_email_campaigns(db: Session, shop_id: str) -> dict:
    """Generate ready-to-send email campaign templates."""
    shop_name = _get_shop_name(db, shop_id)
    top_products = _get_top_products(db, shop_id, days=30, limit=5)
    segments = _get_customer_segments(db, shop_id)
    at_risk = _get_at_risk_customers(db, shop_id)
    monthly_rev = _get_monthly_revenue(db, shop_id)
    season = _get_season()

    p1 = top_products[0]["name"] if top_products else "our featured item"
    p2 = top_products[1]["name"] if len(top_products) > 1 else "popular picks"
    p3 = top_products[2]["name"] if len(top_products) > 2 else "trending finds"

    campaigns = [
        {
            "id": "camp-winback",
            "name": "Win-Back Campaign",
            "type": "win_back",
            "subject": f"We miss you! Here's 15% off your next visit to {shop_name} 💛",
            "preview_text": f"It's been a while since your last visit. We've got new arrivals waiting for you!",
            "body": f"""Hi {{{{first_name}}}},

It's been a while since we've seen you at {shop_name}, and honestly? We miss you!

A lot has changed since your last visit:
- 🆕 New arrivals including {p1} and {p2}
- ⭐ We've added {len(top_products)} new customer favorites
- 🎨 Fresh store layout with even better curated sections

As a special welcome back, here's 15% off your next purchase:

Use code: WELCOMEBACK15

Valid for the next 14 days. We can't wait to see you again!

Warm regards,
The {shop_name} Team

P.S. This offer is exclusively for you — our valued customers we haven't seen in a while. 💛""",
            "target_audience": f"Inactive customers ({at_risk} people who haven't visited in 30+ days)",
            "target_count": at_risk,
            "estimated_open_rate": "32-38%",
            "estimated_revenue": f"${at_risk * 45:.0f}",
            "emoji": "💛",
        },
        {
            "id": "camp-vip",
            "name": "VIP Appreciation",
            "type": "vip",
            "subject": f"You're one of our top customers, {{{{first_name}}}}! A special thank you inside 🌟",
            "preview_text": f"Exclusive early access + a personal thank you from the {shop_name} team",
            "body": f"""Dear {{{{first_name}}}},

You're one of our {segments['vip']} VIP customers at {shop_name}, and we wanted to take a moment to say THANK YOU.

Your support means the world to us. As a small business, every customer matters — but customers like you are truly special.

As our way of saying thanks, we're giving you:

🎁 EXCLUSIVE VIP PERKS:
- Early access to all new arrivals (48 hours before everyone else)
- A personal 20% off code: VIP20LOVE
- Priority service on your next visit — just mention you're a VIP!

Our newest arrivals include {p1}, {p2}, and {p3} — and you get first dibs!

With gratitude,
The {shop_name} Team""",
            "target_audience": f"VIP customers (top {segments['vip']} spenders)",
            "target_count": segments["vip"],
            "estimated_open_rate": "45-55%",
            "estimated_revenue": f"${segments['vip'] * 85:.0f}",
            "emoji": "🌟",
        },
        {
            "id": "camp-newproduct",
            "name": "New Product Launch",
            "type": "new_product",
            "subject": f"Just dropped: {p1} is here! Be the first to grab it 🔥",
            "preview_text": f"Fresh arrivals just landed at {shop_name}. See what's new!",
            "body": f"""Hey {{{{first_name}}}}!

🔥 NEW DROP ALERT!

We're excited to announce our latest arrivals at {shop_name}:

✨ {p1} — Our newest customer favorite
✨ {p2} — Trending and almost sold out
✨ {p3} — Perfect for the {season} season

These items are already generating buzz, and we expect them to sell fast!

👉 Visit us this week to see the full new collection

📍 {shop_name}
⏰ Open daily — check our hours on Google

See you soon!
The {shop_name} Team""",
            "target_audience": f"All active customers ({segments['regular'] + segments['vip']} people)",
            "target_count": segments["regular"] + segments["vip"],
            "estimated_open_rate": "28-35%",
            "estimated_revenue": f"${(segments['regular'] + segments['vip']) * 35:.0f}",
            "emoji": "🔥",
        },
        {
            "id": "camp-newsletter",
            "name": "Weekly Newsletter",
            "type": "newsletter",
            "subject": f"This Week at {shop_name}: Bestsellers + What's Coming Next 🎉",
            "preview_text": f"Your weekly dose of {shop_name} news, deals, and inspiration",
            "body": f"""Happy Sunday, {{{{first_name}}}}! 🎉

Here's your weekly recap from {shop_name}:

📊 THIS WEEK'S BESTSELLERS:
1. {p1} — Still our #1!
2. {p2} — Customers love this one
3. {p3} — Don't miss out

💰 BY THE NUMBERS:
- Revenue this month: ${monthly_rev:,.0f}
- Happy customers served: {segments['total']}+
- New arrivals this week: 5+ items

🔮 COMING NEXT WEEK:
- New seasonal collection drops Wednesday
- Special event this Saturday (details coming!)
- A surprise collaboration announcement 👀

📸 COMMUNITY SPOTLIGHT:
Tag us @{shop_name.replace(' ', '').lower()} in your photos for a chance to be featured!

See you at the shop!
The {shop_name} Team""",
            "target_audience": f"Newsletter subscribers ({segments['total']} customers)",
            "target_count": segments["total"],
            "estimated_open_rate": "25-30%",
            "estimated_revenue": f"${segments['total'] * 12:.0f}",
            "emoji": "🎉",
        },
        {
            "id": "camp-seasonal",
            "name": f"{season.capitalize()} Sale",
            "type": "seasonal",
            "subject": f"{season.capitalize()} Sale at {shop_name}! Up to 25% off selected items 🏷️",
            "preview_text": f"Our biggest {season} sale is here. Don't miss these deals!",
            "body": f"""{{{{first_name}}}}, our {season.capitalize()} Sale is HERE! 🏷️

For a limited time, enjoy amazing deals at {shop_name}:

🏷️ THE DEALS:
- 25% off all {top_products[0]['category'] if top_products else 'Apparel'} items
- Buy 2, get 1 free on {top_products[1]['category'] if len(top_products) > 1 else 'Accessories'}
- Free gift with purchases over $50

🌟 STAFF PICKS FOR {season.upper()}:
- {p1} — Now ${top_products[0]['price'] * 0.75:.0f} (was ${top_products[0]['price']:.0f})
- {p2} — The perfect {season} essential
- {p3} — While supplies last!

⏰ Sale runs this week only!
📍 Visit us in store or DM us to reserve items

Don't wait — our {season} sale items sell fast!

{shop_name} Team""",
            "target_audience": f"All customers ({segments['total']} people)",
            "target_count": segments["total"],
            "estimated_open_rate": "35-42%",
            "estimated_revenue": f"${segments['total'] * 28:.0f}",
            "emoji": "🏷️",
        },
        {
            "id": "camp-review",
            "name": "Review Request",
            "type": "review_request",
            "subject": f"Loved your visit? Tell the world! ⭐ (takes 30 seconds)",
            "preview_text": f"Your Google review helps {shop_name} reach more customers like you",
            "body": f"""Hi {{{{first_name}}}},

Thank you for shopping with us at {shop_name}! 🙏

We noticed you visited recently, and we'd LOVE to hear about your experience.

⭐ Would you mind leaving us a quick Google review?

It takes less than 30 seconds and it makes a HUGE difference for our small business:
- Helps other shoppers discover us
- Lets us know what we're doing right
- Motivates our team to keep improving

👉 [Leave a Review on Google]

Every review counts — whether it's 5 words or 50. We read every single one!

As a thank you, mention your review on your next visit for a surprise gift 🎁

Thank you for being part of our community!

With love,
The {shop_name} Team""",
            "target_audience": f"Recent happy customers ({segments['regular']} regulars)",
            "target_count": segments["regular"],
            "estimated_open_rate": "30-36%",
            "estimated_revenue": "Brand value (boosts Google ranking)",
            "emoji": "⭐",
        },
    ]

    return {"campaigns": campaigns, "total": len(campaigns)}


# ── Promotions ───────────────────────────────────────────────────────────────

def get_promotions(db: Session, shop_id: str) -> dict:
    """Generate promotion ideas with full execution plans."""
    shop_name = _get_shop_name(db, shop_id)
    top_products = _get_top_products(db, shop_id, days=30, limit=6)
    weakest = _get_weakest_day(db, shop_id)
    weaknesses = _get_competitor_weaknesses(db, shop_id)
    segments = _get_customer_segments(db, shop_id)
    season = _get_season()

    p1 = top_products[0] if top_products else {"name": "Top Product", "price": 30}
    p2 = top_products[1] if len(top_products) > 1 else {"name": "Popular Item", "price": 25}

    comp = weaknesses[0] if weaknesses else {"name": "competitor", "topics": ["slow service"]}

    promotions = [
        {
            "id": "promo-flash",
            "name": f"{weakest['day']} Traffic Booster",
            "type": "flash_sale",
            "description": f"20% off everything this {weakest['day']} only! {weakest['day']} is your slowest day (avg {weakest['avg_tx']} transactions). A targeted flash sale can boost traffic by 40-60%.",
            "target_audience": f"All customers — drive {weakest['day']} foot traffic",
            "estimated_revenue": f"${weakest['avg_tx'] * 65 * 0.5:.0f} additional revenue",
            "duration": f"One day ({weakest['day']} only)",
            "execution_steps": [
                f"Post on Instagram/Facebook by {weakest['day']} 8 AM",
                "Send email blast to full customer list the night before",
                "Update in-store signage with flash sale banners",
                "Track transaction count vs normal to measure impact",
            ],
            "social_post": f"🔥 FLASH SALE! This {weakest['day']} only — 20% off EVERYTHING at {shop_name}! Don't miss out. Doors open at 9 AM! #FlashSale #{weakest['day']}Deal #ShopLocal",
            "emoji": "🔥",
            "priority": "high",
        },
        {
            "id": "promo-bundle",
            "name": f"Bundle Deal: {p1['name']} + {p2['name']}",
            "type": "bundle",
            "description": f"Buy {p1['name']} + {p2['name']} together and save 15%! These are your top 2 sellers — bundling them creates urgency and increases average order value.",
            "target_audience": "All shoppers — increase average order value",
            "estimated_revenue": f"${(p1['price'] + p2['price']) * 0.85 * 30:.0f} from 30 bundles sold",
            "duration": "2 weeks",
            "execution_steps": [
                f"Create a display pairing {p1['name']} and {p2['name']} together",
                "Print bundle deal signs for the display",
                "Post about the bundle on Instagram with styled photo",
                f"Bundle price: ${(p1['price'] + p2['price']) * 0.85:.0f} (save ${(p1['price'] + p2['price']) * 0.15:.0f})",
            ],
            "social_post": f"🎁 BUNDLE & SAVE! Get our {p1['name']} + {p2['name']} together for just ${(p1['price'] + p2['price']) * 0.85:.0f} (save ${(p1['price'] + p2['price']) * 0.15:.0f})! This week at {shop_name} 🛍️ #BundleDeal #SaveMore #ShopSmart",
            "emoji": "🎁",
            "priority": "medium",
        },
        {
            "id": "promo-loyalty",
            "name": "Loyalty Stamp Card",
            "type": "loyalty",
            "description": f"Visit 5 times this month, get 25% off your next purchase! Turn regular customers into VIPs. You have {segments['regular']} regular customers who could be upgraded.",
            "target_audience": f"Regular customers ({segments['regular']} people)",
            "estimated_revenue": f"${segments['regular'] * 15:.0f} additional from repeat visits",
            "duration": "Ongoing (monthly reset)",
            "execution_steps": [
                "Print loyalty stamp cards (business card sized)",
                "Train staff to offer cards at checkout",
                "Stamp each visit — 5th stamp = 25% off coupon",
                "Post about the loyalty program on social media",
                "Track card redemptions to measure ROI",
            ],
            "social_post": f"🏆 NEW: {shop_name} Loyalty Rewards! Visit 5 times, earn 25% off your next purchase. Pick up your card on your next visit! Because loyalty deserves to be rewarded 💛 #LoyaltyRewards #ShopLocal #{shop_name.replace(' ', '')}",
            "emoji": "🏆",
            "priority": "high",
        },
        {
            "id": "promo-competitor",
            "name": f"Win Customers from {comp['name']}",
            "type": "competitor_counter",
            "description": f"{comp['name']} has {comp.get('neg_count', 'several')} recent negative reviews about {comp['topics'][0]}. Run a targeted campaign highlighting YOUR strengths in that exact area.",
            "target_audience": f"Dissatisfied {comp['name']} customers + local shoppers",
            "estimated_revenue": "$800-$1,500 from captured competitor customers",
            "duration": "2 weeks",
            "execution_steps": [
                f"Create social posts highlighting your excellent {comp['topics'][0].replace('poor ', '')}",
                f"Run a 'New Customer Welcome' offer: 10% off first purchase",
                f"Post at peak times when {comp['name']}'s negative reviews are visible",
                "Track new customer acquisitions during campaign period",
            ],
            "social_post": f"Looking for a shop that values YOUR time? At {shop_name}, great service isn't a bonus — it's our promise. First time here? Enjoy 10% off! #CustomerFirst #NewCustomerWelcome #ShopLocal",
            "emoji": "🎯",
            "priority": "hot",
        },
        {
            "id": "promo-seasonal",
            "name": f"{season.capitalize()} Refresh Sale",
            "type": "seasonal",
            "description": f"Capitalize on the {season} season with a themed promotion. Feature seasonal products and create urgency with limited-time pricing.",
            "target_audience": "All customers + walk-in traffic",
            "estimated_revenue": f"${segments['total'] * 18:.0f} additional seasonal revenue",
            "duration": "1 week",
            "execution_steps": [
                f"Create a {season}-themed window display",
                f"Select 10-15 seasonal items for 15-20% off",
                "Email campaign with seasonal imagery",
                "Daily Instagram stories showing seasonal picks",
                "Partner with a local cafe for cross-promotion",
            ],
            "social_post": f"🗓️ {season.capitalize()} Refresh Sale this week! 15-20% off selected seasonal items. New season, new finds, new you! Stop by {shop_name} 🛍️ #{season.capitalize()}Sale #SeasonalRefresh #ShopLocal",
            "emoji": "🗓️",
            "priority": "medium",
        },
        {
            "id": "promo-newcustomer",
            "name": "New Customer Welcome",
            "type": "new_customer",
            "description": f"First time at {shop_name}? Enjoy 20% off your first purchase! This evergreen promotion captures walk-in traffic and converts browsers into buyers.",
            "target_audience": "New customers / walk-in traffic",
            "estimated_revenue": "$600-$1,000/month from new customer conversions",
            "duration": "Ongoing",
            "execution_steps": [
                "Create 'Welcome! First time? Ask about our 20% off!' window sign",
                "Train staff to identify and welcome first-time visitors",
                "Collect email at checkout for future marketing",
                "Give first-time buyers a loyalty card too",
                "Post about it weekly on social media to drive awareness",
            ],
            "social_post": f"👋 First time at {shop_name}? Welcome! Enjoy 20% off your entire first purchase. No catch, no minimum — just our way of saying hello! #WelcomeOffer #NewCustomer #FirstVisit #ShopLocal",
            "emoji": "👋",
            "priority": "medium",
        },
    ]

    return {"promotions": promotions, "total": len(promotions)}


# ── Performance Tracking ─────────────────────────────────────────────────────

def get_marketing_performance(db: Session, shop_id: str) -> dict:
    """Get marketing performance metrics."""
    responses = (
        db.query(MarketingResponse)
        .filter(MarketingResponse.shop_id == shop_id)
        .all()
    )

    total = len(responses)
    used = sum(1 for r in responses if r.status == "used")
    saved = sum(1 for r in responses if r.status == "saved")
    new = sum(1 for r in responses if r.status == "new")

    # Estimate impact based on industry averages
    monthly_rev = _get_monthly_revenue(db, shop_id)
    active_marketing_boost = 0.08  # 8% revenue boost from active marketing
    estimated_impact = monthly_rev * active_marketing_boost if used > 0 else 0

    # Content generated counts (static + dynamic)
    content_generated = 20 + total  # Social posts + marketing responses
    calendar_posts = 10  # Weekly calendar posts
    email_campaigns = 6

    return {
        "overview": {
            "content_generated": content_generated,
            "calendar_posts_this_week": calendar_posts,
            "email_campaigns_ready": email_campaigns,
            "promotions_active": 6,
        },
        "marketing_responses": {
            "total": total,
            "used": used,
            "saved": saved,
            "new": new,
        },
        "estimated_impact": {
            "monthly_revenue": round(monthly_rev, 2),
            "marketing_boost_pct": active_marketing_boost * 100,
            "estimated_additional_revenue": round(estimated_impact, 2),
        },
        "engagement": {
            "total_content_pieces": content_generated + calendar_posts + email_campaigns,
            "pieces_used": used,
            "pieces_saved": saved,
            "usage_rate": round(used / max(1, total) * 100, 1),
        },
        "connect_cta": {
            "title": "Connect Your Instagram",
            "description": "Link your Instagram account to track real post performance, engagement rates, and follower growth directly in RetailIQ.",
            "status": "coming_soon",
        },
    }


# ── Content Performance Predictor ────────────────────────────────────────


def predict_content_performance(db: Session, shop_id: str, content_text: str, platform: str = "instagram") -> dict:
    """Predict how well a social media post might perform based on heuristics."""
    shop_name = _get_shop_name(db, shop_id)
    top_products = _get_top_products(db, shop_id, days=14, limit=5)
    top_names = [p["name"].lower() for p in top_products]
    text = content_text.lower()

    score = 50  # baseline
    factors = []

    # Length analysis
    char_count = len(content_text)
    if 100 <= char_count <= 200:
        score += 10
        factors.append({"factor": "Optimal length (100-200 chars)", "impact": "+10", "type": "positive"})
    elif char_count < 50:
        score -= 10
        factors.append({"factor": "Too short — add more detail", "impact": "-10", "type": "negative"})
    elif char_count > 300:
        score -= 5
        factors.append({"factor": "A bit long — consider trimming", "impact": "-5", "type": "negative"})

    # Emoji usage
    import re
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001f926-\U0001f937"
        "\U00010000-\U0010ffff\u200d\u2640-\u2642\u2600-\u2B55\u23cf"
        "\u23e9\u231a\ufe0f\u3030]+", flags=re.UNICODE)
    emoji_count = len(emoji_pattern.findall(content_text))
    if 1 <= emoji_count <= 5:
        score += 8
        factors.append({"factor": f"Good emoji usage ({emoji_count} emojis)", "impact": "+8", "type": "positive"})
    elif emoji_count == 0:
        score -= 5
        factors.append({"factor": "No emojis — add 2-3 for better engagement", "impact": "-5", "type": "negative"})
    elif emoji_count > 8:
        score -= 3
        factors.append({"factor": "Too many emojis — looks spammy", "impact": "-3", "type": "negative"})

    # Hashtag analysis
    hashtags = re.findall(r'#\w+', content_text)
    if 3 <= len(hashtags) <= 8:
        score += 8
        factors.append({"factor": f"Good hashtag count ({len(hashtags)})", "impact": "+8", "type": "positive"})
    elif len(hashtags) == 0:
        score -= 10
        factors.append({"factor": "No hashtags — add 5-8 relevant ones", "impact": "-10", "type": "negative"})
    elif len(hashtags) > 15:
        score -= 5
        factors.append({"factor": "Too many hashtags — keep under 10", "impact": "-5", "type": "negative"})

    # Call to action
    cta_phrases = ["come", "visit", "shop", "grab", "get yours", "stop by", "check out", "don't miss", "link in bio", "dm us"]
    has_cta = any(phrase in text for phrase in cta_phrases)
    if has_cta:
        score += 10
        factors.append({"factor": "Has a call to action", "impact": "+10", "type": "positive"})
    else:
        score -= 8
        factors.append({"factor": "Missing call to action", "impact": "-8", "type": "negative"})

    # Mentions trending products
    mentions_product = any(name in text for name in top_names)
    if mentions_product:
        score += 7
        factors.append({"factor": "References a trending product", "impact": "+7", "type": "positive"})

    # Shop name mentioned
    if shop_name.lower() in text:
        score += 5
        factors.append({"factor": "Mentions your shop name", "impact": "+5", "type": "positive"})

    # Urgency words
    urgency_words = ["limited", "last chance", "today only", "this week", "don't miss", "hurry", "while supplies last", "ending soon"]
    has_urgency = any(w in text for w in urgency_words)
    if has_urgency:
        score += 8
        factors.append({"factor": "Creates urgency", "impact": "+8", "type": "positive"})

    # Question/engagement prompt
    if "?" in content_text:
        score += 5
        factors.append({"factor": "Asks a question — drives comments", "impact": "+5", "type": "positive"})

    # Platform-specific adjustments
    if platform == "instagram" and "#ShopLocal" in content_text:
        score += 3
        factors.append({"factor": "#ShopLocal boosts discovery on Instagram", "impact": "+3", "type": "positive"})

    score = max(10, min(100, score))

    # Rating
    if score >= 80:
        rating = "Excellent"
        color = "success"
    elif score >= 60:
        rating = "Good"
        color = "primary"
    elif score >= 40:
        rating = "Average"
        color = "warning"
    else:
        rating = "Needs Work"
        color = "danger"

    # Suggestions
    suggestions = []
    if not has_cta:
        suggestions.append("Add a call to action like 'Visit us today!' or 'Link in bio'")
    if emoji_count == 0:
        suggestions.append("Add 2-3 emojis to grab attention")
    if len(hashtags) < 3:
        suggestions.append("Add 5-8 relevant hashtags for discovery")
    if not has_urgency:
        suggestions.append("Add urgency words like 'this week only' or 'limited time'")
    if not mentions_product:
        suggestions.append(f"Mention a trending product like {top_products[0]['name']}" if top_products else "Mention a specific product")

    return {
        "score": score,
        "rating": rating,
        "color": color,
        "factors": factors,
        "suggestions": suggestions,
        "platform": platform,
        "char_count": char_count,
        "hashtag_count": len(hashtags),
        "emoji_count": emoji_count,
    }


# ── Hashtag Generator ────────────────────────────────────────────────────


def generate_hashtags(db: Session, shop_id: str, topic: str = "") -> dict:
    """Generate optimized Instagram hashtags based on shop data and topic."""
    shop_name = _get_shop_name(db, shop_id)
    top_products = _get_top_products(db, shop_id, days=30, limit=5)
    season = _get_season()
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    city = shop.city or "local"
    category = shop.category or "retail"

    clean_name = shop_name.replace(" ", "")

    # Build hashtag sets by category
    brand_tags = [
        f"#{clean_name}",
        f"#{clean_name}Shop",
        f"#ShopAt{clean_name}",
    ]

    local_tags = [
        "#ShopLocal",
        "#SupportLocal",
        "#SmallBusiness",
        "#ShopSmall",
        f"#{city.replace(' ', '')}Shopping" if city != "local" else "#LocalFinds",
        f"#{city.replace(' ', '')}Shops" if city != "local" else "#NearMe",
    ]

    category_map = {
        "retail": ["#RetailTherapy", "#ShoppingTime", "#NewFinds", "#MustHave"],
        "clothing": ["#Fashion", "#StyleInspo", "#OOTD", "#WardrobeEssentials"],
        "accessories": ["#Accessories", "#JewelryLovers", "#StyleStatement", "#TreatYourself"],
        "home": ["#HomeDecor", "#HomeStyling", "#InteriorInspo", "#HomefindsILove"],
        "boutique": ["#BoutiqueFinds", "#UniqueFinds", "#CuratedCollection", "#BoutiqueLife"],
        "gift": ["#GiftIdeas", "#PerfectGift", "#GiftGuide", "#ThoughtfulGifts"],
    }
    category_tags = category_map.get(category.lower(), category_map["retail"])

    season_map = {
        "spring": ["#SpringStyle", "#SpringFinds", "#FreshLooks", "#SpringVibes"],
        "summer": ["#SummerStyle", "#SummerEssentials", "#SunnyDays", "#SummerVibes"],
        "fall": ["#FallFashion", "#AutumnVibes", "#CozyUp", "#FallFinds"],
        "winter": ["#WinterStyle", "#CozyVibes", "#HolidayShopping", "#WinterWarmth"],
    }
    seasonal_tags = season_map.get(season, season_map["winter"])

    engagement_tags = [
        "#CustomerFavorite", "#BestSeller", "#TopRated", "#TrendingNow",
        "#NewArrivals", "#JustDropped", "#LimitedEdition", "#StaffPick",
    ]

    product_tags = []
    for p in top_products[:3]:
        clean = p["name"].replace(" ", "").replace("-", "")
        cat_clean = (p["category"] or "").replace(" ", "")
        product_tags.append(f"#{clean}")
        if cat_clean:
            product_tags.append(f"#{cat_clean}")

    # Topic-specific tags
    topic_tags = []
    if topic:
        topic_lower = topic.lower()
        if "sale" in topic_lower or "discount" in topic_lower:
            topic_tags = ["#Sale", "#Deals", "#Discount", "#SaveBig", "#FlashSale"]
        elif "new" in topic_lower or "arrival" in topic_lower:
            topic_tags = ["#NewArrivals", "#JustDropped", "#FreshFinds", "#NewInStore"]
        elif "vip" in topic_lower or "loyalty" in topic_lower:
            topic_tags = ["#VIP", "#LoyaltyRewards", "#ExclusiveOffer", "#MembersOnly"]
        elif "review" in topic_lower or "rating" in topic_lower:
            topic_tags = ["#5Stars", "#CustomerReview", "#HappyCustomers", "#Testimonial"]
        elif "behind" in topic_lower or "bts" in topic_lower:
            topic_tags = ["#BTS", "#BehindTheScenes", "#ShopOwnerLife", "#DayInTheLife"]

    # Combine and deduplicate
    all_tags = brand_tags + local_tags + category_tags + seasonal_tags + engagement_tags + product_tags + topic_tags
    seen = set()
    unique_tags = []
    for t in all_tags:
        lower = t.lower()
        if lower not in seen:
            seen.add(lower)
            unique_tags.append(t)

    # Split into sets for easy copying
    sets = {
        "brand": brand_tags[:3],
        "local": local_tags[:5],
        "category": category_tags[:4],
        "seasonal": seasonal_tags[:4],
        "engagement": engagement_tags[:5],
        "product": product_tags[:4],
    }
    if topic_tags:
        sets["topic"] = topic_tags[:5]

    # Recommended set (mix of high and low competition)
    recommended = brand_tags[:2] + local_tags[:2] + category_tags[:2] + seasonal_tags[:1] + engagement_tags[:2]
    if product_tags:
        recommended.append(product_tags[0])

    return {
        "recommended": recommended[:10],
        "all_tags": unique_tags,
        "sets": sets,
        "total": len(unique_tags),
        "copy_all": " ".join(recommended[:10]),
        "tip": "Use 8-12 hashtags per post. Mix branded, local, and category tags for best reach.",
    }


# ── Weekly Marketing Report ──────────────────────────────────────────────


def get_weekly_marketing_report(db: Session, shop_id: str) -> dict:
    """Generate a comprehensive weekly marketing report."""
    shop_name = _get_shop_name(db, shop_id)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    last_week_start = week_start - timedelta(days=7)

    # Revenue data
    this_week_rev = float(
        db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0))
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= week_start, DailySnapshot.date <= today)
        .scalar() or 0
    )
    last_week_rev = float(
        db.query(func.coalesce(func.sum(DailySnapshot.total_revenue), 0))
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= last_week_start, DailySnapshot.date < week_start)
        .scalar() or 0
    )
    rev_change = round((this_week_rev - last_week_rev) / last_week_rev * 100, 1) if last_week_rev > 0 else 0

    # Transaction data
    this_week_tx = (
        db.query(func.coalesce(func.sum(DailySnapshot.transaction_count), 0))
        .filter(DailySnapshot.shop_id == shop_id, DailySnapshot.date >= week_start, DailySnapshot.date <= today)
        .scalar() or 0
    )

    # Top products this week
    top = _get_top_products(db, shop_id, days=7, limit=5)

    # Customer segments
    segments = _get_customer_segments(db, shop_id)

    # Competitor weaknesses
    weaknesses = _get_competitor_weaknesses(db, shop_id)

    # Marketing responses used
    responses = (
        db.query(MarketingResponse)
        .filter(MarketingResponse.shop_id == shop_id)
        .all()
    )
    used_count = sum(1 for r in responses if r.status == "used")

    # Content performance estimate
    content_score = min(95, 45 + used_count * 8 + len(top) * 3)

    # Recommendations
    recs = []
    if rev_change < -5:
        recs.append({
            "icon": "1F4C9",
            "text": f"Revenue is down {abs(rev_change)}% this week. Push a flash sale or featured product campaign.",
            "priority": "high",
        })
    if segments["at_risk"] > 10:
        recs.append({
            "icon": "26A0",
            "text": f"You have {segments['at_risk']} at-risk customers. Send a win-back email with a 15% off code.",
            "priority": "high",
        })
    if used_count == 0:
        recs.append({
            "icon": "1F4DD",
            "text": "You haven't used any generated marketing content yet. Try posting one of our AI-generated social posts!",
            "priority": "medium",
        })
    if weaknesses:
        w = weaknesses[0]
        recs.append({
            "icon": "1F3AF",
            "text": f"{w['name']} has {w['neg_count']} recent negative reviews. Run a targeted campaign highlighting your strengths.",
            "priority": "medium",
        })
    recs.append({
        "icon": "1F4F1",
        "text": "Post at least 3 times this week on Instagram. Consistency is key for small business growth.",
        "priority": "low",
    })

    return {
        "period": {"start": week_start.isoformat(), "end": week_end.isoformat()},
        "shop_name": shop_name,
        "revenue": {
            "this_week": this_week_rev,
            "last_week": last_week_rev,
            "change_pct": rev_change,
            "transactions": int(this_week_tx),
        },
        "top_products": top[:5],
        "customers": segments,
        "content": {
            "score": content_score,
            "pieces_generated": 20 + len(responses),
            "pieces_used": used_count,
            "calendar_posts": 10,
        },
        "competitor_opportunities": len(weaknesses),
        "recommendations": recs,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ── Email Template Builder ───────────────────────────────────────────────


def build_email_template(db: Session, shop_id: str, template_type: str, custom_params: dict = None) -> dict:
    """Build a custom email template based on type and shop data."""
    shop_name = _get_shop_name(db, shop_id)
    top_products = _get_top_products(db, shop_id, days=30, limit=5)
    segments = _get_customer_segments(db, shop_id)
    season = _get_season()

    p = custom_params or {}
    discount = p.get("discount", "15")
    product_name = p.get("product_name", top_products[0]["name"] if top_products else "our featured item")
    event_name = p.get("event_name", f"{season.capitalize()} Collection Launch")
    event_date = p.get("event_date", "this Saturday")

    templates = {
        "welcome": {
            "name": "Welcome Email",
            "subject": f"Welcome to {shop_name}! Here's a special gift for you 🎁",
            "preview": f"Your first-time discount is waiting...",
            "body": f"""Hi {{{{first_name}}}},

Welcome to the {shop_name} family! 🎉

We're thrilled to have you as a new customer. Here at {shop_name}, we believe shopping should be a joy — and we're committed to making every visit special.

🎁 YOUR WELCOME GIFT:
Use code WELCOME{discount} for {discount}% off your next purchase!

Here's what makes {shop_name} special:
- ✨ Handpicked, quality-checked products
- 💛 Personalized service from our friendly team
- 🆕 New arrivals every week
- 🏆 Top-rated by our community

Our current bestsellers:
{chr(10).join(f'- {p["name"]} (${p["price"]:.0f})' for p in top_products[:3])}

We can't wait to see you again!

Warm regards,
The {shop_name} Team""",
            "target": "New customers",
            "est_open_rate": "45-55%",
        },
        "flash_sale": {
            "name": "Flash Sale Alert",
            "subject": f"FLASH SALE: {discount}% off EVERYTHING at {shop_name}! Today only ⚡",
            "preview": f"Our biggest flash sale is here — don't miss it!",
            "body": f"""{{{{first_name}}}}, this is NOT a drill! ⚡

🔥 FLASH SALE — {discount}% OFF EVERYTHING

For the next 24 hours only, enjoy {discount}% off your entire purchase at {shop_name}!

🛍️ HOT PICKS:
{chr(10).join(f'- {p["name"]} — NOW ${p["price"] * (1 - int(discount)/100):.0f} (was ${p["price"]:.0f})' for p in top_products[:4])}

⏰ This offer expires TONIGHT at midnight!

Use code: FLASH{discount}

📍 Visit us in store or DM us to hold items
No exclusions. No minimum purchase. Just amazing deals!

Don't wait — when it's gone, it's gone!

{shop_name} Team""",
            "target": "All customers",
            "est_open_rate": "38-45%",
        },
        "event_invite": {
            "name": "Event Invitation",
            "subject": f"You're invited! {event_name} at {shop_name} 🎪",
            "preview": f"Join us for an exclusive event...",
            "body": f"""{{{{first_name}}}}, you're invited! 🎪

📅 {event_name.upper()}

Join us {event_date} at {shop_name} for an exclusive event:

🎉 WHAT TO EXPECT:
- First look at our new {season} collection
- Refreshments and treats
- Exclusive event-only discounts ({discount}% off)
- Meet our team and fellow {shop_name} fans
- Raffle prizes (gift cards up to $100!)

📍 Where: {shop_name}
📅 When: {event_date}
⏰ Time: 10 AM - 4 PM

🎟️ RSVP by replying to this email or DM us on Instagram

Space is limited — let us know you're coming!

See you there,
The {shop_name} Team""",
            "target": "VIP + Regular customers",
            "est_open_rate": "35-42%",
        },
        "product_launch": {
            "name": "New Product Launch",
            "subject": f"Just dropped: {product_name} is here! 🚀",
            "preview": f"Be the first to get our newest arrival",
            "body": f"""{{{{first_name}}}}, we're SO excited about this one! 🚀

Introducing: {product_name.upper()}

After weeks of curating, testing, and perfecting — it's finally here.

✨ WHY YOU'LL LOVE IT:
- Handpicked quality you can trust
- Unique design you won't find elsewhere
- Perfect for the {season} season
- Already generating buzz from our testers!

🏷️ Launch Week Special: Get {discount}% off with code LAUNCH{discount}

Limited initial stock — first come, first served!

📍 Available in-store now
📱 DM us to hold one

{shop_name} — Where great finds find you.

The {shop_name} Team""",
            "target": "All subscribers",
            "est_open_rate": "30-38%",
        },
        "thank_you": {
            "name": "Post-Purchase Thank You",
            "subject": f"Thank you for shopping at {shop_name}! 💛",
            "preview": f"A personal thank you + a special surprise...",
            "body": f"""Hi {{{{first_name}}}},

Just wanted to say THANK YOU for your recent purchase at {shop_name}! 💛

Your support means everything to us as a small business. Every purchase helps us keep doing what we love — curating amazing products for amazing customers like you.

🎁 AS A THANK YOU:
Here's {discount}% off your next visit: THANKS{discount}
(Valid for 30 days)

📸 Love your purchase? We'd love to see it!
Tag us on Instagram for a chance to be featured.

⭐ Got 30 seconds? A Google review helps us reach more customers like you and keeps our small business thriving.

Thank you for being part of the {shop_name} community!

With gratitude,
The {shop_name} Team""",
            "target": "Recent purchasers",
            "est_open_rate": "40-50%",
        },
    }

    template = templates.get(template_type, templates["welcome"])

    return {
        "template": template,
        "template_type": template_type,
        "available_types": [
            {"id": "welcome", "name": "Welcome Email", "emoji": "🎁"},
            {"id": "flash_sale", "name": "Flash Sale Alert", "emoji": "⚡"},
            {"id": "event_invite", "name": "Event Invitation", "emoji": "🎪"},
            {"id": "product_launch", "name": "Product Launch", "emoji": "🚀"},
            {"id": "thank_you", "name": "Post-Purchase Thank You", "emoji": "💛"},
        ],
        "variables": ["{{first_name}}"],
        "shop_name": shop_name,
    }
