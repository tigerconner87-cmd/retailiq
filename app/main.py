from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import auth, dashboard_api, pages

app = FastAPI(
    title="RetailIQ",
    description="Sales intelligence dashboard for retail shop owners",
    version="1.0.0",
)

# Create tables on startup (use Alembic in production)
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(auth.router)
app.include_router(dashboard_api.router)
app.include_router(pages.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
