import logging

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import Base, engine
from app.routers import ai, auth, dashboard_api, data_hub, pages

log = logging.getLogger(__name__)

app = FastAPI(
    title="Forge",
    description="Sales intelligence dashboard for retail shop owners",
    version="2.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Columns added in v2.0 that don't exist in the original schema.
# PostgreSQL ADD COLUMN IF NOT EXISTS is idempotent — safe to run every boot.
_ALTER_STMTS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_step INTEGER DEFAULT 0",
    "ALTER TABLE shops ADD COLUMN IF NOT EXISTS category VARCHAR(100) DEFAULT 'retail'",
    "ALTER TABLE shops ADD COLUMN IF NOT EXISTS store_size_sqft INTEGER",
    "ALTER TABLE shops ADD COLUMN IF NOT EXISTS staff_count INTEGER DEFAULT 1",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS sku VARCHAR(100)",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS stock_quantity INTEGER",
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS segment VARCHAR(20) DEFAULT 'regular'",
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS avg_order_value NUMERIC(12,2) DEFAULT 0",
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS avg_days_between_visits FLOAT",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS discount NUMERIC(12,2) DEFAULT 0",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50) DEFAULT 'card'",
    "ALTER TABLE daily_snapshots ADD COLUMN IF NOT EXISTS total_cost NUMERIC(12,2) DEFAULT 0",
    "ALTER TABLE daily_snapshots ADD COLUMN IF NOT EXISTS items_sold INTEGER DEFAULT 0",
    "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS response_text TEXT",
    "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS responded_at TIMESTAMP",
    "ALTER TABLE competitors ADD COLUMN IF NOT EXISTS category VARCHAR(100)",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'general'",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS is_snoozed BOOLEAN DEFAULT false",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS snoozed_until TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_start_date TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_end_date TIMESTAMP",
    "ALTER TABLE shops ADD COLUMN IF NOT EXISTS city VARCHAR(255)",
    "ALTER TABLE shop_settings ADD COLUMN IF NOT EXISTS google_api_key VARCHAR(255) DEFAULT ''",
    "ALTER TABLE shop_settings ADD COLUMN IF NOT EXISTS anthropic_api_key VARCHAR(255) DEFAULT ''",
    "ALTER TABLE shop_settings ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT true",
    "ALTER TABLE shop_settings ADD COLUMN IF NOT EXISTS ai_personality VARCHAR(50) DEFAULT 'professional'",
]


@app.on_event("startup")
def on_startup():
    # 1. create_all — creates any tables that don't exist yet (idempotent, fast)
    Base.metadata.create_all(bind=engine)

    # 2. Add missing columns to tables that already existed before v2.0
    with engine.begin() as conn:
        for stmt in _ALTER_STMTS:
            conn.execute(text(stmt))

    # 3. Add performance indexes (idempotent — IF NOT EXISTS)
    _INDEX_STMTS = [
        "CREATE INDEX IF NOT EXISTS ix_transactions_shop_timestamp ON transactions (shop_id, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_daily_snapshots_shop_date ON daily_snapshots (shop_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transaction_items_transaction ON transaction_items (transaction_id)",
        "CREATE INDEX IF NOT EXISTS ix_transaction_items_product ON transaction_items (product_id)",
        "CREATE INDEX IF NOT EXISTS ix_reviews_shop ON reviews (shop_id)",
        "CREATE INDEX IF NOT EXISTS ix_hourly_snapshots_shop_date ON hourly_snapshots (shop_id, date)",
        "CREATE INDEX IF NOT EXISTS ix_customers_shop ON customers (shop_id)",
        "CREATE INDEX IF NOT EXISTS ix_alerts_shop_read ON alerts (shop_id, is_read)",
        "CREATE INDEX IF NOT EXISTS ix_competitors_shop ON competitors (shop_id)",
        "CREATE INDEX IF NOT EXISTS ix_expenses_shop ON expenses (shop_id)",
    ]
    with engine.begin() as conn:
        for stmt in _INDEX_STMTS:
            conn.execute(text(stmt))

    log.info("Schema sync complete")

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(ai.router)
app.include_router(auth.router)
app.include_router(dashboard_api.router)
app.include_router(data_hub.router)
app.include_router(pages.router)


@app.get("/health")
def health_check():
    checks = {"api": "ok"}
    # DB check
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    # Redis check
    try:
        import redis as _redis
        r = _redis.from_url("redis://redis:6379/0", socket_timeout=1)
        r.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"
    overall = "ok" if checks.get("database") == "ok" else "degraded"
    return {"status": overall, "version": "2.0.0", "checks": checks}


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse("500.html", {"request": request}, status_code=500)
