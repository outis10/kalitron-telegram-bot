from dataclasses import dataclass

from kalitron_telegram_bot.domain import ValidationResult


@dataclass(slots=True)
class GatewayFilePart:
    file_name: str
    content: bytes
    content_type: str


@dataclass(slots=True)
class GatewayReceiptRequest:
    client_id: str
    source: str
    document_type: str
    file: GatewayFilePart


@dataclass(slots=True)
class GatewayIdentityRequest:
    client_id: str
    document_type: str
    file: GatewayFilePart


@dataclass(slots=True)
class GatewayValidationResponse:
    result: ValidationResult
