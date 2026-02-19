from datetime import datetime, timedelta

import bcrypt as _bcrypt
from jose import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, Shop


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:72]
    return _bcrypt.hashpw(pw, _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    pw = plain.encode("utf-8")[:72]
    return _bcrypt.checkpw(pw, hashed.encode("utf-8"))


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def register_user(
    db: Session,
    email: str,
    password: str,
    full_name: str,
    shop_name: str,
    pos_system: str,
    shop_type: str = "general_retail",
    city: str = "",
) -> User:
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("Email already registered")

    now = datetime.utcnow()
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        trial_start_date=now,
        trial_end_date=now + timedelta(days=14),
    )
    db.add(user)
    db.flush()

    shop = Shop(
        user_id=user.id,
        name=shop_name,
        pos_system=pos_system,
        category=shop_type,
        city=city,
    )
    db.add(shop)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def is_trial_active(user: User) -> bool:
    """Check if user's trial is still active. Demo account never expires."""
    if user.email == "demo@forgeapp.com":
        return True
    if not user.trial_end_date:
        return True  # No trial set = legacy user, treat as active
    return datetime.utcnow() < user.trial_end_date


def get_trial_days_remaining(user: User) -> int:
    """Get number of days remaining in trial."""
    if user.email == "demo@forgeapp.com":
        return 99  # Demo never expires
    if not user.trial_end_date:
        return 99
    delta = user.trial_end_date - datetime.utcnow()
    return max(0, delta.days)
