from dataclasses import dataclass

from kalitron_telegram_bot.domain import ValidationCase, ValidationResult


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


@dataclass(slots=True)
class GatewayCaseDocumentRequest:
    document_type: str
    file_name: str
    content_type: str
    content_base64: str


@dataclass(slots=True)
class GatewayCreateCaseRequest:
    client_id: str
    channel: str
    chat_id: str
    documents: list[GatewayCaseDocumentRequest]


@dataclass(slots=True)
class GatewayCreateCaseResponse:
    case_id: str
    status: str


@dataclass(slots=True)
class GatewayCaseStatusResponse:
    case: ValidationCase
