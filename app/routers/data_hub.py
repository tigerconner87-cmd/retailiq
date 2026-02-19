"""Data Hub router — manual entry, CSV import, product/customer CRUD, Google Places integration."""

import hashlib
import logging
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Optional

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models import (
    Competitor,
    CompetitorReview,
    Customer,
    DailySnapshot,
    PlanInterest,
    Product,
    Review,
    Shop,
    Transaction,
    TransactionItem,
    User,
    new_id,
)
from app.services.analytics import get_shop_for_user
from app.services.cache import cache_get, cache_set

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["data-hub"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_shop(db: Session, user: User) -> Shop:
    shop = get_shop_for_user(db, user.id)
    if not shop:
        raise HTTPException(status_code=404, detail="No shop found for this user")
    return shop


POSITIVE_KEYWORDS = {
    "great", "excellent", "amazing", "wonderful", "fantastic", "love",
    "best", "perfect", "friendly", "delicious", "recommend",
}
NEGATIVE_KEYWORDS = {
    "terrible", "awful", "worst", "rude", "dirty", "slow",
    "cold", "bad", "horrible", "disappointed", "never",
}


def _analyze_sentiment(text: str) -> str:
    if not text:
        return "neutral"
    words = text.lower().split()
    pos = sum(1 for w in words if w in POSITIVE_KEYWORDS)
    neg = sum(1 for w in words if w in NEGATIVE_KEYWORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


# ---------------------------------------------------------------------------
# Pydantic request/response bodies
# ---------------------------------------------------------------------------

class DailyEntryItem(BaseModel):
    product_name: str
    quantity: int
    unit_price: float


class DailyEntryRequest(BaseModel):
    date: str
    revenue: float
    transactions: int
    walk_in_customers: int
    notes: Optional[str] = None
    items: list[DailyEntryItem] = []


class CsvImportMapping(BaseModel):
    date_col: str
    revenue_col: str
    product_col: Optional[str] = None
    quantity_col: Optional[str] = None
    customer_col: Optional[str] = None


class CsvImportRequest(BaseModel):
    data: list[list]
    mapping: CsvImportMapping
    file_name: str


class ProductCreateRequest(BaseModel):
    name: str
    category: Optional[str] = None
    price: float
    cost: Optional[float] = None
    sku: Optional[str] = None


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    cost: Optional[float] = None
    sku: Optional[str] = None


class CustomerCreateRequest(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None


class CustomerUpdateRequest(BaseModel):
    email: Optional[str] = None
    segment: Optional[str] = None


class ConnectionNotifyRequest(BaseModel):
    email: str
    integration: str


class GoogleConnectRequest(BaseModel):
    place_id: str
    name: str
    address: str
    lat: float
    lng: float


class GoogleCompetitorRequest(BaseModel):
    place_id: str
    name: str
    address: str
    rating: Optional[float] = None
    review_count: Optional[int] = 0
    lat: Optional[float] = None
    lng: Optional[float] = None
    category: Optional[str] = None


class GoogleSyncReviewsRequest(BaseModel):
    place_id: str


# ---------------------------------------------------------------------------
# 1. POST /daily-entry
# ---------------------------------------------------------------------------

@router.post("/daily-entry")
def save_daily_entry(
    body: DailyEntryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)

    try:
        entry_date = datetime.strptime(body.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Create the day-level Transaction record
    tx = Transaction(
        id=new_id(),
        shop_id=shop.id,
        subtotal=body.revenue,
        tax=0,
        discount=0,
        total=body.revenue,
        items_count=body.transactions,
        payment_method="manual",
        timestamp=entry_date,
    )
    db.add(tx)

    total_items_sold = 0

    # Process line items
    for item in body.items:
        # Look up existing product or create one
        product = (
            db.query(Product)
            .filter(Product.shop_id == shop.id, Product.name == item.product_name)
            .first()
        )
        if not product:
            product = Product(
                id=new_id(),
                shop_id=shop.id,
                name=item.product_name,
                price=item.unit_price,
                is_active=True,
            )
            db.add(product)
            db.flush()

        ti = TransactionItem(
            id=new_id(),
            transaction_id=tx.id,
            product_id=product.id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total=round(item.quantity * item.unit_price, 2),
        )
        db.add(ti)
        total_items_sold += item.quantity

    # Create or update DailySnapshot
    snap_date = entry_date.date() if isinstance(entry_date, datetime) else entry_date
    snapshot = (
        db.query(DailySnapshot)
        .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date == snap_date)
        .first()
    )
    avg_tx_val = round(body.revenue / body.transactions, 2) if body.transactions > 0 else 0

    if snapshot:
        snapshot.total_revenue = float(snapshot.total_revenue or 0) + body.revenue
        snapshot.transaction_count = (snapshot.transaction_count or 0) + body.transactions
        snapshot.items_sold = (snapshot.items_sold or 0) + total_items_sold
        snapshot.unique_customers = (snapshot.unique_customers or 0) + body.walk_in_customers
        snapshot.avg_transaction_value = (
            round(float(snapshot.total_revenue) / snapshot.transaction_count, 2)
            if snapshot.transaction_count > 0
            else 0
        )
    else:
        snapshot = DailySnapshot(
            id=new_id(),
            shop_id=shop.id,
            date=snap_date,
            total_revenue=body.revenue,
            transaction_count=body.transactions,
            avg_transaction_value=avg_tx_val,
            items_sold=total_items_sold,
            unique_customers=body.walk_in_customers,
            new_customers=body.walk_in_customers,
        )
        db.add(snapshot)

    db.commit()

    # Comparison: same weekday previous week
    prev_week_date = snap_date - timedelta(days=7)
    prev_snapshot = (
        db.query(DailySnapshot)
        .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date == prev_week_date)
        .first()
    )

    comparison_message = "No data from the same day last week to compare."
    if prev_snapshot and prev_snapshot.total_revenue and float(prev_snapshot.total_revenue) > 0:
        pct_change = round(
            (body.revenue - float(prev_snapshot.total_revenue))
            / float(prev_snapshot.total_revenue)
            * 100,
            1,
        )
        direction = "up" if pct_change >= 0 else "down"
        comparison_message = (
            f"Revenue is {direction} {abs(pct_change)}% compared to the same day last week "
            f"(${float(prev_snapshot.total_revenue):,.2f})."
        )

    return {
        "detail": "Daily entry saved",
        "date": body.date,
        "revenue": body.revenue,
        "transactions": body.transactions,
        "items_created": len(body.items),
        "comparison": comparison_message,
    }


# ---------------------------------------------------------------------------
# 2. GET /entry-history
# ---------------------------------------------------------------------------

@router.get("/entry-history")
def get_entry_history(
    days: int = Query(90),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    cutoff = date.today() - timedelta(days=days)

    snapshots = (
        db.query(DailySnapshot.date)
        .filter(DailySnapshot.shop_id == shop.id, DailySnapshot.date >= cutoff)
        .order_by(DailySnapshot.date.desc())
        .all()
    )

    logged_dates = sorted([s.date for s in snapshots], reverse=True)

    # Calculate streak (consecutive recent days)
    streak = 0
    check_date = date.today()
    date_set = set(logged_dates)
    while check_date in date_set:
        streak += 1
        check_date -= timedelta(days=1)

    return {
        "dates": [d.isoformat() for d in logged_dates],
        "total_logged": len(logged_dates),
        "streak": streak,
    }


# ---------------------------------------------------------------------------
# 3. POST /csv-upload
# ---------------------------------------------------------------------------

@router.post("/csv-upload")
async def csv_upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_shop(db, user)  # auth check

    contents = await file.read()
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError:
        text = contents.decode("latin-1")

    df = pd.read_csv(StringIO(text))

    file_id = hashlib.md5((file.filename or "upload").encode()).hexdigest()

    preview = df.head(5).fillna("").to_dict(orient="records")

    return {
        "columns": list(df.columns),
        "preview": preview,
        "row_count": len(df),
        "file_id": file_id,
    }


# ---------------------------------------------------------------------------
# 4. POST /csv-import
# ---------------------------------------------------------------------------

@router.post("/csv-import")
def csv_import(
    body: CsvImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    mapping = body.mapping

    imported = 0
    skipped = 0
    errors: list[str] = []

    for row_idx, row in enumerate(body.data):
        try:
            if not row or len(row) == 0:
                skipped += 1
                continue

            # Build a dict from header indices
            # Rows are raw arrays; mapping cols are column names.
            # We need the header row to resolve indices. If data[0] is the header, use it.
            # Convention: data already excludes header — caller provides column names in mapping.
            # We'll treat each row as positional matching the order of columns in the first row
            # But since we don't have column names here, assume data includes header as row 0
            # and mapping col names correspond to those headers.
            # Safest: build index map from first row if it looks like a header.
            pass
        except Exception:
            pass

    # Re-process with proper header handling
    if not body.data:
        return {"imported": 0, "skipped": 0, "errors": ["No data provided"]}

    # Detect if first row is a header
    header = body.data[0] if body.data else []
    data_rows = body.data[1:] if body.data else []

    # Build column index map
    col_map: dict[str, int] = {}
    for idx, col_name in enumerate(header):
        col_map[str(col_name).strip()] = idx

    date_idx = col_map.get(mapping.date_col)
    revenue_idx = col_map.get(mapping.revenue_col)
    product_idx = col_map.get(mapping.product_col) if mapping.product_col else None
    quantity_idx = col_map.get(mapping.quantity_col) if mapping.quantity_col else None
    customer_idx = col_map.get(mapping.customer_col) if mapping.customer_col else None

    if date_idx is None or revenue_idx is None:
        return {"imported": 0, "skipped": 0, "errors": ["Date or revenue column not found in data"]}

    imported = 0
    skipped = 0
    errors = []

    for row_idx, row in enumerate(data_rows):
        try:
            if not row or len(row) == 0:
                skipped += 1
                continue

            # Parse date
            raw_date = str(row[date_idx]).strip()
            try:
                tx_date = datetime.strptime(raw_date, "%Y-%m-%d")
            except ValueError:
                try:
                    tx_date = datetime.strptime(raw_date, "%m/%d/%Y")
                except ValueError:
                    errors.append(f"Row {row_idx + 1}: Invalid date '{raw_date}'")
                    skipped += 1
                    continue

            # Parse revenue
            try:
                revenue = float(str(row[revenue_idx]).replace("$", "").replace(",", "").strip())
            except (ValueError, IndexError):
                errors.append(f"Row {row_idx + 1}: Invalid revenue value")
                skipped += 1
                continue

            # Create Transaction
            tx = Transaction(
                id=new_id(),
                shop_id=shop.id,
                subtotal=revenue,
                tax=0,
                discount=0,
                total=revenue,
                items_count=1,
                payment_method="csv_import",
                timestamp=tx_date,
            )
            db.add(tx)

            # Create Product if mapped
            if product_idx is not None and product_idx < len(row):
                product_name = str(row[product_idx]).strip()
                if product_name:
                    product = (
                        db.query(Product)
                        .filter(Product.shop_id == shop.id, Product.name == product_name)
                        .first()
                    )
                    if not product:
                        product = Product(
                            id=new_id(),
                            shop_id=shop.id,
                            name=product_name,
                            price=revenue,
                            is_active=True,
                        )
                        db.add(product)
                        db.flush()

                    qty = 1
                    if quantity_idx is not None and quantity_idx < len(row):
                        try:
                            qty = int(float(str(row[quantity_idx]).strip()))
                        except (ValueError, TypeError):
                            qty = 1

                    ti = TransactionItem(
                        id=new_id(),
                        transaction_id=tx.id,
                        product_id=product.id,
                        quantity=qty,
                        unit_price=revenue,
                        total=revenue,
                    )
                    db.add(ti)

            imported += 1

        except Exception as exc:
            errors.append(f"Row {row_idx + 1}: {str(exc)}")
            skipped += 1

    db.commit()

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:50],
    }


# ---------------------------------------------------------------------------
# 5. GET /products
# ---------------------------------------------------------------------------

@router.get("/products")
def list_products(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    products = (
        db.query(Product)
        .filter(Product.shop_id == shop.id, Product.is_active.is_(True))
        .order_by(Product.name)
        .all()
    )
    return {
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "price": float(p.price),
                "cost": float(p.cost) if p.cost else None,
                "sku": p.sku,
                "stock_quantity": p.stock_quantity,
                "is_active": p.is_active,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in products
        ],
        "total": len(products),
    }


# ---------------------------------------------------------------------------
# 6. POST /products
# ---------------------------------------------------------------------------

@router.post("/products")
def create_product(
    body: ProductCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    product = Product(
        id=new_id(),
        shop_id=shop.id,
        name=body.name,
        category=body.category,
        price=body.price,
        cost=body.cost,
        sku=body.sku,
        is_active=True,
    )
    db.add(product)
    db.commit()
    return {
        "detail": "Product created",
        "id": product.id,
        "name": product.name,
    }


# ---------------------------------------------------------------------------
# 7. PUT /products/{product_id}
# ---------------------------------------------------------------------------

@router.put("/products/{product_id}")
def update_product(
    product_id: str,
    body: ProductUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.shop_id == shop.id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if body.name is not None:
        product.name = body.name
    if body.category is not None:
        product.category = body.category
    if body.price is not None:
        product.price = body.price
    if body.cost is not None:
        product.cost = body.cost
    if body.sku is not None:
        product.sku = body.sku

    db.commit()
    return {"detail": "Product updated", "id": product.id}


# ---------------------------------------------------------------------------
# 8. DELETE /products/{product_id}
# ---------------------------------------------------------------------------

@router.delete("/products/{product_id}")
def deactivate_product(
    product_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.shop_id == shop.id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.is_active = False
    db.commit()
    return {"detail": "Product deactivated", "id": product.id}


# ---------------------------------------------------------------------------
# 9. GET /customers
# ---------------------------------------------------------------------------

@router.get("/customers")
def list_customers(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str = Query(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    query = db.query(Customer).filter(Customer.shop_id == shop.id)

    if search:
        term = f"%{search}%"
        query = query.filter(Customer.email.ilike(term))

    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page)

    customers = (
        query.order_by(Customer.total_spent.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "customers": [
            {
                "id": c.id,
                "email": c.email,
                "segment": c.segment,
                "visit_count": c.visit_count,
                "total_spent": float(c.total_spent) if c.total_spent else 0,
                "avg_order_value": float(c.avg_order_value) if c.avg_order_value else 0,
                "first_seen": c.first_seen.isoformat() if c.first_seen else None,
                "last_seen": c.last_seen.isoformat() if c.last_seen else None,
            }
            for c in customers
        ],
        "total": total,
        "page": page,
        "pages": pages,
    }


# ---------------------------------------------------------------------------
# 10. POST /customers
# ---------------------------------------------------------------------------

@router.post("/customers")
def create_customer(
    body: CustomerCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    now = datetime.utcnow()

    # Customer model doesn't have name or phone columns.
    # Store name in email if email is blank; phone is ignored.
    email_value = body.email or body.name or None

    customer = Customer(
        id=new_id(),
        shop_id=shop.id,
        email=email_value,
        segment="regular",
        first_seen=now,
        last_seen=now,
        visit_count=0,
        total_spent=0,
        avg_order_value=0,
    )
    db.add(customer)
    db.commit()
    return {
        "detail": "Customer created",
        "id": customer.id,
        "email": customer.email,
    }


# ---------------------------------------------------------------------------
# 11. PUT /customers/{customer_id}
# ---------------------------------------------------------------------------

@router.put("/customers/{customer_id}")
def update_customer(
    customer_id: str,
    body: CustomerUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.shop_id == shop.id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if body.email is not None:
        customer.email = body.email
    if body.segment is not None:
        customer.segment = body.segment

    db.commit()
    return {"detail": "Customer updated", "id": customer.id}


# ---------------------------------------------------------------------------
# 12. DELETE /customers/{customer_id}
# ---------------------------------------------------------------------------

@router.delete("/customers/{customer_id}")
def delete_customer(
    customer_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.shop_id == shop.id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    db.delete(customer)
    db.commit()
    return {"detail": "Customer deleted", "id": customer_id}


# ---------------------------------------------------------------------------
# 13. POST /csv-upload-products
# ---------------------------------------------------------------------------

@router.post("/csv-upload-products")
async def csv_upload_products(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)

    contents = await file.read()
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError:
        text = contents.decode("latin-1")

    df = pd.read_csv(StringIO(text))

    created = 0
    for _, row in df.iterrows():
        name = str(row.get("name", row.get("Name", row.get("product_name", "")))).strip()
        if not name:
            continue

        price_raw = row.get("price", row.get("Price", 0))
        try:
            price = float(str(price_raw).replace("$", "").replace(",", "").strip())
        except (ValueError, TypeError):
            price = 0

        cost_raw = row.get("cost", row.get("Cost", None))
        cost = None
        if cost_raw is not None:
            try:
                cost = float(str(cost_raw).replace("$", "").replace(",", "").strip())
            except (ValueError, TypeError):
                cost = None

        category = str(row.get("category", row.get("Category", ""))).strip() or None
        sku = str(row.get("sku", row.get("SKU", ""))).strip() or None

        product = Product(
            id=new_id(),
            shop_id=shop.id,
            name=name,
            category=category,
            price=price,
            cost=cost,
            sku=sku,
            is_active=True,
        )
        db.add(product)
        created += 1

    db.commit()
    return {"detail": f"{created} products created", "created": created}


# ---------------------------------------------------------------------------
# 14. POST /csv-upload-customers
# ---------------------------------------------------------------------------

@router.post("/csv-upload-customers")
async def csv_upload_customers(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)

    contents = await file.read()
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError:
        text = contents.decode("latin-1")

    df = pd.read_csv(StringIO(text))
    now = datetime.utcnow()

    created = 0
    for _, row in df.iterrows():
        email = str(row.get("email", row.get("Email", ""))).strip() or None
        segment = str(row.get("segment", row.get("Segment", "regular"))).strip()

        customer = Customer(
            id=new_id(),
            shop_id=shop.id,
            email=email,
            segment=segment if segment in ("vip", "regular", "at_risk", "lost") else "regular",
            first_seen=now,
            last_seen=now,
            visit_count=0,
            total_spent=0,
            avg_order_value=0,
        )
        db.add(customer)
        created += 1

    db.commit()
    return {"detail": f"{created} customers created", "created": created}


# ---------------------------------------------------------------------------
# 15. POST /connections/notify
# ---------------------------------------------------------------------------

@router.post("/connections/notify")
def connections_notify(
    body: ConnectionNotifyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pi = PlanInterest(
        id=new_id(),
        user_id=user.id,
        email=body.email,
        plan=body.integration,
        billing_cycle="monthly",
    )
    db.add(pi)
    db.commit()
    return {"detail": "Interest recorded", "integration": body.integration}


# ---------------------------------------------------------------------------
# Google Places — mock data
# ---------------------------------------------------------------------------

MOCK_PLACES = [
    {
        "place_id": "mock_place_001",
        "name": "Main Street Coffee House",
        "address": "123 Main St, Anytown, USA",
        "rating": 4.5,
        "review_count": 238,
        "lat": 40.7128,
        "lng": -74.0060,
    },
    {
        "place_id": "mock_place_002",
        "name": "Downtown Boutique Shop",
        "address": "456 Oak Ave, Anytown, USA",
        "rating": 4.2,
        "review_count": 152,
        "lat": 40.7138,
        "lng": -74.0070,
    },
    {
        "place_id": "mock_place_003",
        "name": "Harbor View General Store",
        "address": "789 Harbor Blvd, Anytown, USA",
        "rating": 4.7,
        "review_count": 312,
        "lat": 40.7148,
        "lng": -74.0080,
    },
    {
        "place_id": "mock_place_004",
        "name": "Elm Street Market",
        "address": "321 Elm St, Anytown, USA",
        "rating": 3.9,
        "review_count": 97,
        "lat": 40.7158,
        "lng": -74.0090,
    },
]

MOCK_REVIEWS = [
    {
        "author_name": "Jane D.",
        "rating": 5,
        "text": "Absolutely amazing experience! The staff was friendly and the products are perfect quality. I love this place and would recommend it to everyone.",
        "time": 1700000000,
    },
    {
        "author_name": "Mike R.",
        "rating": 4,
        "text": "Great selection and excellent service. A bit slow during peak hours but overall a wonderful shop.",
        "time": 1699500000,
    },
    {
        "author_name": "Sarah L.",
        "rating": 2,
        "text": "Disappointed with my last visit. The service was slow and the store felt dirty. Bad experience overall.",
        "time": 1699000000,
    },
]


# ---------------------------------------------------------------------------
# 16. GET /google/search
# ---------------------------------------------------------------------------

@router.get("/google/search")
async def google_search(
    query: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_shop(db, user)  # auth check

    api_key = settings.GOOGLE_PLACES_API_KEY

    if not api_key:
        # Return mock results
        filtered = [p for p in MOCK_PLACES if query.lower() in p["name"].lower()] or MOCK_PLACES
        return {"results": filtered}

    # Check cache
    cache_key = f"riq:google_search:{hashlib.md5(query.encode()).hexdigest()}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": api_key}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Google Places API error")

    data = resp.json()
    results = []
    for place in data.get("results", [])[:10]:
        results.append({
            "place_id": place.get("place_id"),
            "name": place.get("name"),
            "address": place.get("formatted_address"),
            "rating": place.get("rating"),
            "review_count": place.get("user_ratings_total", 0),
            "lat": place.get("geometry", {}).get("location", {}).get("lat"),
            "lng": place.get("geometry", {}).get("location", {}).get("lng"),
        })

    response = {"results": results}
    cache_set(cache_key, response, ttl=300)
    return response


# ---------------------------------------------------------------------------
# 17. POST /google/connect
# ---------------------------------------------------------------------------

@router.post("/google/connect")
def google_connect(
    body: GoogleConnectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)
    shop.google_place_id = body.place_id
    shop.address = body.address
    shop.latitude = body.lat
    shop.longitude = body.lng
    db.commit()
    return {
        "detail": "Shop connected to Google Place",
        "place_id": body.place_id,
        "name": body.name,
    }


# ---------------------------------------------------------------------------
# 18. POST /google/add-competitor
# ---------------------------------------------------------------------------

@router.post("/google/add-competitor")
def google_add_competitor(
    body: GoogleCompetitorRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)

    # Check if competitor with same place_id already exists
    existing = (
        db.query(Competitor)
        .filter(
            Competitor.shop_id == shop.id,
            Competitor.google_place_id == body.place_id,
        )
        .first()
    )
    if existing:
        return {"detail": "Competitor already exists", "id": existing.id}

    competitor = Competitor(
        id=new_id(),
        shop_id=shop.id,
        name=body.name,
        google_place_id=body.place_id,
        address=body.address,
        category=body.category,
        rating=body.rating,
        review_count=body.review_count or 0,
        latitude=body.lat,
        longitude=body.lng,
    )
    db.add(competitor)
    db.commit()
    return {
        "detail": "Competitor added",
        "id": competitor.id,
        "name": competitor.name,
    }


# ---------------------------------------------------------------------------
# 19. GET /google/nearby
# ---------------------------------------------------------------------------

@router.get("/google/nearby")
async def google_nearby(
    lat: float = Query(...),
    lng: float = Query(...),
    type: str = Query("store"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_shop(db, user)  # auth check

    api_key = settings.GOOGLE_PLACES_API_KEY

    if not api_key:
        return {"results": MOCK_PLACES}

    cache_key = f"riq:google_nearby:{lat:.4f}:{lng:.4f}:{type}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": 5000,
        "type": type,
        "key": api_key,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Google Places API error")

    data = resp.json()
    results = []
    for place in data.get("results", [])[:10]:
        results.append({
            "place_id": place.get("place_id"),
            "name": place.get("name"),
            "address": place.get("formatted_address", place.get("vicinity", "")),
            "rating": place.get("rating"),
            "review_count": place.get("user_ratings_total", 0),
            "lat": place.get("geometry", {}).get("location", {}).get("lat"),
            "lng": place.get("geometry", {}).get("location", {}).get("lng"),
        })

    response = {"results": results}
    cache_set(cache_key, response, ttl=300)
    return response


# ---------------------------------------------------------------------------
# 20. POST /google/sync-reviews
# ---------------------------------------------------------------------------

@router.post("/google/sync-reviews")
async def google_sync_reviews(
    body: GoogleSyncReviewsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = _get_shop(db, user)

    api_key = settings.GOOGLE_PLACES_API_KEY
    reviews_data = []

    if not api_key:
        # Use mock reviews
        reviews_data = MOCK_REVIEWS
    else:
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": body.place_id,
            "fields": "reviews,rating,user_ratings_total",
            "key": api_key,
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)

        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Google Places API error")

        data = resp.json()
        reviews_data = data.get("result", {}).get("reviews", [])

    synced = 0

    # Determine if this place_id belongs to the shop or a competitor
    is_own_shop = shop.google_place_id == body.place_id

    competitor = None
    if not is_own_shop:
        competitor = (
            db.query(Competitor)
            .filter(
                Competitor.shop_id == shop.id,
                Competitor.google_place_id == body.place_id,
            )
            .first()
        )

    for review in reviews_data:
        author = review.get("author_name", "Anonymous")
        rating = review.get("rating", 0)
        text = review.get("text", "")
        review_time = review.get("time")

        review_date = None
        if review_time:
            try:
                review_date = datetime.utcfromtimestamp(review_time)
            except (ValueError, TypeError, OSError):
                review_date = datetime.utcnow()

        sentiment = _analyze_sentiment(text)

        if is_own_shop:
            # Store as a Review for the shop
            existing = (
                db.query(Review)
                .filter(
                    Review.shop_id == shop.id,
                    Review.author_name == author,
                    Review.review_date == review_date,
                )
                .first()
            )
            if not existing:
                rev = Review(
                    id=new_id(),
                    shop_id=shop.id,
                    source="google",
                    author_name=author,
                    rating=rating,
                    text=text,
                    review_date=review_date,
                    sentiment=sentiment,
                    is_own_shop=True,
                )
                db.add(rev)
                synced += 1
        elif competitor:
            # Store as a CompetitorReview
            existing = (
                db.query(CompetitorReview)
                .filter(
                    CompetitorReview.competitor_id == competitor.id,
                    CompetitorReview.author_name == author,
                    CompetitorReview.review_date == review_date,
                )
                .first()
            )
            if not existing:
                cr = CompetitorReview(
                    id=new_id(),
                    competitor_id=competitor.id,
                    author_name=author,
                    rating=rating,
                    text=text,
                    review_date=review_date,
                    sentiment=sentiment,
                )
                db.add(cr)
                synced += 1

    db.commit()

    return {
        "detail": f"Synced {synced} reviews",
        "synced": synced,
        "place_id": body.place_id,
        "is_own_shop": is_own_shop,
    }
