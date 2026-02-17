from app.connectors.base import BasePOSConnector
from app.connectors.square import SquareConnector
from app.connectors.shopify import ShopifyConnector
from app.connectors.clover import CloverConnector
from app.connectors.google_places import GooglePlacesConnector

CONNECTOR_MAP: dict[str, type[BasePOSConnector]] = {
    "square": SquareConnector,
    "shopify": ShopifyConnector,
    "clover": CloverConnector,
}


def get_pos_connector(pos_system: str, credentials: dict | None = None) -> BasePOSConnector:
    cls = CONNECTOR_MAP.get(pos_system)
    if not cls:
        raise ValueError(f"Unsupported POS system: {pos_system}")
    return cls(credentials=credentials or {})
