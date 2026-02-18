from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.dependencies import get_current_user_optional, get_db
from sqlalchemy.orm import Session
from app.services.analytics import get_shop_for_user

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def landing_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    shop = get_shop_for_user(db, user.id)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "shop": shop,
    })


@router.get("/dashboard/competitors", response_class=HTMLResponse)
def competitors_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    shop = get_shop_for_user(db, user.id)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "shop": shop,
        "active_section": "competitors",
    })


@router.get("/dashboard/competitors/weekly-report", response_class=HTMLResponse)
def weekly_report_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    shop = get_shop_for_user(db, user.id)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "shop": shop,
        "active_section": "competitors",
        "sub_section": "weekly-report",
    })
