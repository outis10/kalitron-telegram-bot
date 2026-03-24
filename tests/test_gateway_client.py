import asyncio

import httpx
import pytest

from kalitron_telegram_bot.application import ValidationUseCases
from kalitron_telegram_bot.client_registry import (
    CsvClientOnboardingRegistrar,
    CsvClientResolver,
)
from kalitron_telegram_bot.domain import (
    ChannelIdentity,
    GatewayReceiptSource,
    IdentityDocumentType,
    IncomingDocument,
    InputChannel,
    ValidateIdentityCommand,
    ValidateReceiptCommand,
)
from kalitron_telegram_bot.errors import (
    ClientOnboardingError,
    ClientResolutionError,
    ValidationCompatibilityError,
    ValidationRequestError,
)
from kalitron_telegram_bot.gateway_adapter import (
    GatewayChannelMapping,
    GatewayValidationAdapter,
)
from kalitron_telegram_bot.gateway_contract import (
    GatewayFilePart,
    GatewayIdentityRequest,
    GatewayReceiptRequest,
)
from kalitron_telegram_bot.gateway_http_client import GatewayHttpClient


class DummyGatewayHttpClient:
    def __init__(self) -> None:
        self.receipt_request: GatewayReceiptRequest | None = None
        self.identity_request: GatewayIdentityRequest | None = None

    async def send_receipt_validation(self, request: GatewayReceiptRequest):
        self.receipt_request = request
        return GatewayHttpClient._parse_validation_result(
            {
                "document_type": "RECEIPT",
                "decision": "AUTO_APPROVED",
                "final_score": 98.2,
                "requires_human_review": False,
                "extracted_data": {"issuer": "OXXO"},
                "fraud_indicators": [],
                "breakdown": {"rules_score": 1.0},
            }
        )

    async def send_identity_validation(self, request: GatewayIdentityRequest):
        self.identity_request = request
        return GatewayHttpClient._parse_validation_result(
            {
                "document_type": "INE",
                "decision": "AUTO_APPROVED",
                "final_score": 99.0,
                "requires_human_review": False,
                "is_expired": False,
                "extracted_data": {"full_name": "Jane Doe"},
                "fraud_indicators": [],
                "breakdown": {"rules_score": 1.0},
            }
        )


def _build_transport(handler):
    return httpx.MockTransport(handler)


def test_gateway_adapter_maps_telegram_receipt_to_configured_gateway_source():
    http_client = DummyGatewayHttpClient()
    adapter = GatewayValidationAdapter(
        http_client=http_client,  # type: ignore[arg-type]
        channel_mapping=GatewayChannelMapping.from_settings(
            telegram_receipt_source="manual"
        ),
    )

    result = asyncio.run(
        adapter.validate_receipt(
            ValidateReceiptCommand(
                document=IncomingDocument(
                    sender=ChannelIdentity(
                        channel=InputChannel.TELEGRAM,
                        user_id="1",
                    ),
                    client_id="12345",
                    file_name="receipt.png",
                    content_type="image/png",
                    content=b"png",
                )
            )
        )
    )

    assert http_client.receipt_request is not None
    assert http_client.receipt_request.source == GatewayReceiptSource.MANUAL.value
    assert result.document_type == "RECEIPT"


def test_gateway_adapter_passes_identity_without_source_mapping():
    http_client = DummyGatewayHttpClient()
    adapter = GatewayValidationAdapter(
        http_client=http_client,  # type: ignore[arg-type]
        channel_mapping=GatewayChannelMapping.from_settings(
            telegram_receipt_source="manual"
        ),
    )

    asyncio.run(
        adapter.validate_identity(
            ValidateIdentityCommand(
                document=IncomingDocument(
                    sender=ChannelIdentity(
                        channel=InputChannel.TELEGRAM,
                        user_id="1",
                    ),
                    client_id="12345",
                    file_name="ine.png",
                    content_type="image/png",
                    content=b"png",
                ),
                document_type=IdentityDocumentType.INE,
            )
        )
    )

    assert http_client.identity_request is not None
    assert http_client.identity_request.document_type == "INE"


def test_invalid_channel_mapping_value_is_rejected():
    with pytest.raises(ValidationCompatibilityError):
        GatewayChannelMapping.from_settings(telegram_receipt_source="telegram")


def test_missing_channel_mapping_is_rejected():
    mapping = GatewayChannelMapping.from_settings()

    with pytest.raises(ValidationCompatibilityError):
        mapping.receipt_source_for_channel(InputChannel.TELEGRAM)


def test_csv_client_resolver_resolves_by_telegram_user_id(tmp_path):
    csv_path = tmp_path / "clients.csv"
    csv_path.write_text(
        "client_id,channel,user_id,chat_id,username,phone_number\n"
        "client-001,telegram,12345,999,alice,\n",
        encoding="utf-8",
    )
    resolver = CsvClientResolver(str(csv_path))

    client_id = resolver.resolve_client_id(
        ChannelIdentity(channel=InputChannel.TELEGRAM, user_id="12345")
    )

    assert client_id == "client-001"


def test_use_cases_resolve_client_id_before_gateway_call(tmp_path):
    csv_path = tmp_path / "clients.csv"
    csv_path.write_text(
        "client_id,channel,user_id,chat_id,username,phone_number\n"
        "client-001,telegram,12345,999,alice,\n",
        encoding="utf-8",
    )
    use_cases = ValidationUseCases(
        client_resolver=CsvClientResolver(str(csv_path)),
        validation_gateway=GatewayValidationAdapter(
            http_client=DummyGatewayHttpClient(),  # type: ignore[arg-type]
            channel_mapping=GatewayChannelMapping.from_settings(
                telegram_receipt_source="manual"
            ),
        ),
    )

    result = asyncio.run(
        use_cases.validate_receipt(
            ValidateReceiptCommand(
                document=IncomingDocument(
                    sender=ChannelIdentity(
                        channel=InputChannel.TELEGRAM,
                        user_id="12345",
                        chat_id="999",
                        username="alice",
                    ),
                    file_name="receipt.png",
                    content_type="image/png",
                    content=b"png",
                )
            )
        )
    )

    assert result.document_type == "RECEIPT"


def test_csv_client_resolver_rejects_unknown_identity(tmp_path):
    csv_path = tmp_path / "clients.csv"
    csv_path.write_text(
        "client_id,channel,user_id,chat_id,username,phone_number\n"
        "client-001,telegram,12345,999,alice,\n",
        encoding="utf-8",
    )
    resolver = CsvClientResolver(str(csv_path))

    with pytest.raises(ClientResolutionError):
        resolver.resolve_client_id(
            ChannelIdentity(channel=InputChannel.TELEGRAM, user_id="77777")
        )


def test_csv_onboarding_registers_identity_and_consumes_code(tmp_path):
    registry_path = tmp_path / "client_registry.csv"
    codes_path = tmp_path / "access_codes.csv"
    registry_path.write_text(
        "client_id,channel,user_id,chat_id,username,phone_number\n"
        "client-whatsapp-demo,whatsapp,,,,5215555555555\n",
        encoding="utf-8",
    )
    codes_path.write_text(
        "access_code,client_id,channel,used,expires_at,used_at\n"
        "ABC123XYZ,client-001,telegram,false,2099-12-31T23:59:59+00:00,\n",
        encoding="utf-8",
    )

    registrar = CsvClientOnboardingRegistrar(
        client_registry_csv_path=str(registry_path),
        access_code_csv_path=str(codes_path),
    )

    client_id = registrar.register_identity(
        "ABC123XYZ",
        ChannelIdentity(
            channel=InputChannel.TELEGRAM,
            user_id="12345",
            chat_id="999",
            username="alice",
        ),
    )

    assert client_id == "client-001"
    registry_content = registry_path.read_text(encoding="utf-8")
    codes_content = codes_path.read_text(encoding="utf-8")
    assert "client-001,telegram,12345,999,alice," in registry_content
    assert "ABC123XYZ,client-001,telegram,true" in codes_content
    assert "2099-12-31T23:59:59+00:00" in codes_content


def test_csv_onboarding_rejects_expired_code(tmp_path):
    registry_path = tmp_path / "client_registry.csv"
    codes_path = tmp_path / "access_codes.csv"
    registry_path.write_text(
        "client_id,channel,user_id,chat_id,username,phone_number\n"
        "client-whatsapp-demo,whatsapp,,,,5215555555555\n",
        encoding="utf-8",
    )
    codes_path.write_text(
        "access_code,client_id,channel,used,expires_at,used_at\n"
        "ABC123XYZ,client-001,telegram,false,2000-01-01T00:00:00+00:00,\n",
        encoding="utf-8",
    )

    registrar = CsvClientOnboardingRegistrar(
        client_registry_csv_path=str(registry_path),
        access_code_csv_path=str(codes_path),
    )

    with pytest.raises(ClientOnboardingError):
        registrar.register_identity(
            "ABC123XYZ",
            ChannelIdentity(channel=InputChannel.TELEGRAM, user_id="12345"),
        )


def test_csv_onboarding_rejects_invalid_code(tmp_path):
    registry_path = tmp_path / "client_registry.csv"
    codes_path = tmp_path / "access_codes.csv"
    registry_path.write_text(
        "client_id,channel,user_id,chat_id,username,phone_number\n"
        "client-whatsapp-demo,whatsapp,,,,5215555555555\n",
        encoding="utf-8",
    )
    codes_path.write_text(
        "access_code,client_id,channel,used,expires_at,used_at\n"
        "ABC123XYZ,client-001,telegram,true,2099-12-31T23:59:59+00:00,2026-01-01T00:00:00+00:00\n",
        encoding="utf-8",
    )

    registrar = CsvClientOnboardingRegistrar(
        client_registry_csv_path=str(registry_path),
        access_code_csv_path=str(codes_path),
    )

    with pytest.raises(ClientOnboardingError):
        registrar.register_identity(
            "ABC123XYZ",
            ChannelIdentity(channel=InputChannel.TELEGRAM, user_id="12345"),
        )


def test_gateway_http_client_sends_receipt_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["header"] = request.headers.get("X-API-Key")
        captured["body"] = request.read().decode("utf-8", errors="ignore")
        return httpx.Response(
            200,
            json={
                "document_type": "RECEIPT",
                "decision": "AUTO_APPROVED",
                "final_score": 98.2,
                "requires_human_review": False,
                "extracted_data": {"issuer": "OXXO"},
                "fraud_indicators": [],
                "breakdown": {"rules_score": 1.0},
            },
        )

    client = GatewayHttpClient(
        base_url="http://gateway.test",
        api_key="secret",
        timeout_seconds=5.0,
        transport=_build_transport(handler),
    )

    result = asyncio.run(
        client.send_receipt_validation(
            GatewayReceiptRequest(
                client_id="12345",
                source="manual",
                file=GatewayFilePart(
                    file_name="receipt.png",
                    content=b"png",
                    content_type="image/png",
                ),
            )
        )
    )

    assert captured["path"] == "/api/v1/validate/receipt"
    assert captured["header"] == "secret"
    assert 'name="source"' in captured["body"]
    assert "manual" in captured["body"]
    assert result.document_type == "RECEIPT"


def test_error_detail_is_propagated():
    response = httpx.Response(415, json={"detail": "Unsupported file type"})
    assert GatewayHttpClient._extract_error_detail(response) == "Unsupported file type"


def test_gateway_request_error_exposes_status_code():
    error = ValidationRequestError(503, "Temporarily unavailable")
    assert error.status_code == 503
    assert error.detail == "Temporarily unavailable"
