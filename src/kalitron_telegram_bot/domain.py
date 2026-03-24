from dataclasses import dataclass
from enum import Enum


class InputChannel(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


class ValidationKind(str, Enum):
    RECEIPT = "receipt"
    IDENTITY = "identity"


class IdentityDocumentType(str, Enum):
    INE = "INE"
    PASAPORTE = "PASAPORTE"
    LICENCIA = "LICENCIA"


class GatewayReceiptSource(str, Enum):
    WHATSAPP = "whatsapp"
    CRM = "crm"
    WEB = "web"
    MANUAL = "manual"


@dataclass(slots=True)
class PendingValidation:
    kind: ValidationKind
    document_type: IdentityDocumentType | None = None


@dataclass(slots=True)
class ChannelIdentity:
    channel: InputChannel
    user_id: str | None = None
    chat_id: str | None = None
    username: str | None = None
    phone_number: str | None = None


@dataclass(slots=True)
class IncomingDocument:
    sender: ChannelIdentity
    file_name: str
    content_type: str
    content: bytes
    client_id: str | None = None


@dataclass(slots=True)
class ValidateReceiptCommand:
    document: IncomingDocument


@dataclass(slots=True)
class ValidateIdentityCommand:
    document: IncomingDocument
    document_type: IdentityDocumentType


@dataclass(slots=True)
class ValidationResult:
    document_type: str
    decision: str
    final_score: float
    requires_human_review: bool
    extracted_data: dict
    fraud_indicators: list[str]
    breakdown: dict
    is_expired: bool | None = None
