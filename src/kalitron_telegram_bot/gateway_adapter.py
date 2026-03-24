from __future__ import annotations

from dataclasses import dataclass

from kalitron_telegram_bot.application import ValidationGateway
from kalitron_telegram_bot.domain import (
    GatewayReceiptSource,
    InputChannel,
    ValidateIdentityCommand,
    ValidateReceiptCommand,
    ValidationResult,
)
from kalitron_telegram_bot.errors import ValidationCompatibilityError
from kalitron_telegram_bot.gateway_contract import (
    GatewayFilePart,
    GatewayIdentityRequest,
    GatewayReceiptRequest,
)
from kalitron_telegram_bot.gateway_http_client import GatewayHttpClient


@dataclass(slots=True)
class GatewayChannelMapping:
    receipt_source_by_channel: dict[InputChannel, GatewayReceiptSource]

    @classmethod
    def from_settings(
        cls,
        *,
        telegram_receipt_source: str | None = None,
        whatsapp_receipt_source: str | None = None,
    ) -> "GatewayChannelMapping":
        mapping: dict[InputChannel, GatewayReceiptSource] = {}
        if telegram_receipt_source:
            mapping[InputChannel.TELEGRAM] = cls._parse_receipt_source(
                "TELEGRAM_GATEWAY_RECEIPT_SOURCE",
                telegram_receipt_source,
            )
        if whatsapp_receipt_source:
            mapping[InputChannel.WHATSAPP] = cls._parse_receipt_source(
                "WHATSAPP_GATEWAY_RECEIPT_SOURCE",
                whatsapp_receipt_source,
            )
        return cls(receipt_source_by_channel=mapping)

    @staticmethod
    def _parse_receipt_source(
        setting_name: str, raw_value: str
    ) -> GatewayReceiptSource:
        try:
            return GatewayReceiptSource(raw_value.lower())
        except ValueError as exc:
            raise ValidationCompatibilityError(
                f"{setting_name} must be one of: whatsapp, crm, web, manual."
            ) from exc

    def receipt_source_for_channel(self, channel: InputChannel) -> GatewayReceiptSource:
        try:
            return self.receipt_source_by_channel[channel]
        except KeyError as exc:
            raise ValidationCompatibilityError(
                f"No gateway receipt source configured for channel '{channel.value}'."
            ) from exc


@dataclass(slots=True)
class GatewayValidationAdapter(ValidationGateway):
    http_client: GatewayHttpClient
    channel_mapping: GatewayChannelMapping

    async def validate_receipt(
        self, command: ValidateReceiptCommand
    ) -> ValidationResult:
        if not command.document.client_id:
            raise ValidationCompatibilityError(
                "Resolved client_id is required for receipt validation."
            )
        request = GatewayReceiptRequest(
            client_id=command.document.client_id,
            source=self.channel_mapping.receipt_source_for_channel(
                command.document.sender.channel
            ).value,
            file=GatewayFilePart(
                file_name=command.document.file_name,
                content=command.document.content,
                content_type=command.document.content_type,
            ),
        )
        return await self.http_client.send_receipt_validation(request)

    async def validate_identity(
        self, command: ValidateIdentityCommand
    ) -> ValidationResult:
        if not command.document.client_id:
            raise ValidationCompatibilityError(
                "Resolved client_id is required for identity validation."
            )
        request = GatewayIdentityRequest(
            client_id=command.document.client_id,
            document_type=command.document_type.value,
            file=GatewayFilePart(
                file_name=command.document.file_name,
                content=command.document.content,
                content_type=command.document.content_type,
            ),
        )
        return await self.http_client.send_identity_validation(request)
