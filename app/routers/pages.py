from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.dependencies import get_current_user_optional, get_db
from sqlalchemy.orm import Session
from app.services.analytics import get_shop_for_user
from app.services.auth import is_trial_active, get_trial_days_remaining

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
    return templates.TemplateResponse("register.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # If onboarding not completed, redirect to onboarding
    if not user.onboarding_completed and user.email != "demo@retailiq.com":
        return RedirectResponse(url="/dashboard/onboarding", status_code=302)

    # Check trial status
    trial_active = is_trial_active(user)
    if not trial_active:
        return RedirectResponse(url="/dashboard/upgrade", status_code=302)

    shop = get_shop_for_user(db, user.id)
    trial_days = get_trial_days_remaining(user)
    welcome = request.query_params.get("welcome", "")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "shop": shop,
        "trial_days": trial_days,
        "show_trial_banner": user.email != "demo@retailiq.com" and trial_days < 90,
        "welcome": welcome,
    })


@router.get("/dashboard/onboarding", response_class=HTMLResponse)
def onboarding_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Already completed onboarding? Go to dashboard
    if user.onboarding_completed:
        return RedirectResponse(url="/dashboard", status_code=302)

    shop = get_shop_for_user(db, user.id)
    return templates.TemplateResponse("onboarding.html", {
        "request": request,
        "user": user,
        "shop": shop,
    })


@router.get("/dashboard/upgrade", response_class=HTMLResponse)
def upgrade_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    trial_days = get_trial_days_remaining(user)
    trial_active = is_trial_active(user)

    return templates.TemplateResponse("upgrade.html", {
        "request": request,
        "user": user,
        "trial_active": trial_active,
        "trial_days": trial_days,
    })


@router.get("/dashboard/goals", response_class=HTMLResponse)
def goals_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    shop = get_shop_for_user(db, user.id)
    trial_days = get_trial_days_remaining(user)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "shop": shop,
        "active_section": "goals",
        "trial_days": trial_days,
        "show_trial_banner": user.email != "demo@retailiq.com" and trial_days < 90,
    })


@router.get("/dashboard/marketing", response_class=HTMLResponse)
def marketing_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    shop = get_shop_for_user(db, user.id)
    trial_days = get_trial_days_remaining(user)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "shop": shop,
        "active_section": "marketing",
        "trial_days": trial_days,
        "show_trial_banner": user.email != "demo@retailiq.com" and trial_days < 90,
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
    trial_days = get_trial_days_remaining(user)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "shop": shop,
        "active_section": "competitors",
        "trial_days": trial_days,
        "show_trial_banner": user.email != "demo@retailiq.com" and trial_days < 90,
    })


@router.get("/dashboard/briefing", response_class=HTMLResponse)
def briefing_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.onboarding_completed and user.email != "demo@retailiq.com":
        return RedirectResponse(url="/dashboard/onboarding", status_code=302)
    if not is_trial_active(user):
        return RedirectResponse(url="/dashboard/upgrade", status_code=302)
    shop = get_shop_for_user(db, user.id)
    trial_days = get_trial_days_remaining(user)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "shop": shop,
        "active_section": "briefing",
        "trial_days": trial_days,
        "show_trial_banner": user.email != "demo@retailiq.com" and trial_days < 90,
    })


@router.get("/dashboard/win-back", response_class=HTMLResponse)
def winback_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.onboarding_completed and user.email != "demo@retailiq.com":
        return RedirectResponse(url="/dashboard/onboarding", status_code=302)
    if not is_trial_active(user):
        return RedirectResponse(url="/dashboard/upgrade", status_code=302)
    shop = get_shop_for_user(db, user.id)
    trial_days = get_trial_days_remaining(user)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "shop": shop,
        "active_section": "winback",
        "trial_days": trial_days,
        "show_trial_banner": user.email != "demo@retailiq.com" and trial_days < 90,
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
    trial_days = get_trial_days_remaining(user)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "shop": shop,
        "active_section": "competitors",
        "sub_section": "weekly-report",
        "trial_days": trial_days,
        "show_trial_banner": user.email != "demo@retailiq.com" and trial_days < 90,
    })
