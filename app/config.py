from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://retailiq:retailiq@db:5432/retailiq"
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    SQUARE_ACCESS_TOKEN: str = ""
    SHOPIFY_ACCESS_TOKEN: str = ""
    SHOPIFY_SHOP_DOMAIN: str = ""
    CLOVER_ACCESS_TOKEN: str = ""
    CLOVER_MERCHANT_ID: str = ""

    GOOGLE_PLACES_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENCLAW_BRIDGE_TOKEN: str = "forge-openclaw-bridge-2026"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_FROM_EMAIL: str = "alerts@forgeapp.com"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
