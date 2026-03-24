"""Backward-compatible gateway module.

Prefer `gateway_adapter.py` plus `gateway_http_client.py`.
"""

from kalitron_telegram_bot.errors import (
    ValidationCompatibilityError as GatewayCompatibilityError,
)
from kalitron_telegram_bot.errors import (
    ValidationIntegrationError as GatewayClientError,
)
from kalitron_telegram_bot.errors import ValidationRequestError as GatewayRequestError
from kalitron_telegram_bot.gateway_http_client import GatewayHttpClient as GatewayClient

__all__ = [
    "GatewayClient",
    "GatewayClientError",
    "GatewayCompatibilityError",
    "GatewayRequestError",
]
