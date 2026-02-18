from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import auth, dashboard_api, pages

app = FastAPI(
    title="RetailIQ",
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
    return {"status": "ok", "version": "2.0.0"}


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
