from dataclasses import dataclass, field
from enum import Enum


class InputChannel(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


class ValidationKind(str, Enum):
    RECEIPT = "receipt"
    IDENTITY = "identity"


class IdentityDocumentType(str, Enum):
    INE = "INE"
    INE_REVERSO = "INE_REVERSO"
    PASAPORTE = "PASAPORTE"
    LICENCIA = "LICENCIA"


class ReceiptDocumentType(str, Enum):
    RECEIPT = "RECEIPT"
    ADDRESS_PROOF = "ADDRESS_PROOF"


class CaseStage(str, Enum):
    COLLECTING = "COLLECTING"
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"


class RemoteCaseStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    WAITING_AUTHORIZATION = "WAITING_AUTHORIZATION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class GatewayReceiptSource(str, Enum):
    WHATSAPP = "whatsapp"
    CRM = "crm"
    WEB = "web"
    MANUAL = "manual"


@dataclass(slots=True)
class PendingValidation:
    kind: ValidationKind
    identity_document_type: IdentityDocumentType | None = None
    receipt_document_type: ReceiptDocumentType = ReceiptDocumentType.RECEIPT


@dataclass(slots=True)
class ClientCaseSession:
    client_id: str
    stage: CaseStage = CaseStage.COLLECTING
    remote_case_id: str | None = None
    remote_status: RemoteCaseStatus | None = None
    uploaded_documents: dict[str, "IncomingDocument"] = field(default_factory=dict)
    last_error: str | None = None

    required_documents: tuple[str, ...] = (
        IdentityDocumentType.INE.value,
        IdentityDocumentType.INE_REVERSO.value,
        ReceiptDocumentType.ADDRESS_PROOF.value,
    )

    def next_expected_document_type(self) -> str | None:
        for document_type in self.required_documents:
            if document_type not in self.uploaded_documents:
                return document_type
        return None

    def is_complete(self) -> bool:
        return self.next_expected_document_type() is None


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
    document_type: ReceiptDocumentType = ReceiptDocumentType.RECEIPT


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


@dataclass(slots=True)
class CaseDocumentResult:
    document_id: str
    document_type: str
    file_name: str
    status: str
    error: str | None
    result: dict


@dataclass(slots=True)
class ValidationCase:
    case_id: str
    client_id: str
    channel: str
    chat_id: str
    status: RemoteCaseStatus
    authorization_status: str | None
    rejection_reason_code: str | None
    rejection_reason_text: str | None
    documents: list[CaseDocumentResult]
    consolidated_data: dict
    created_at: str
    updated_at: str


@dataclass(slots=True)
class CaseSubmissionDocument:
    document_type: str
    document: IncomingDocument
