from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from kalitron_telegram_bot.domain import ValidationResult
from kalitron_telegram_bot.errors import ValidationRequestError
from kalitron_telegram_bot.gateway_contract import (
    GatewayIdentityRequest,
    GatewayReceiptRequest,
)


@dataclass(slots=True)
class GatewayHttpClient:
    base_url: str
    api_key: str
    timeout_seconds: float
    transport: Any = None
    _headers: dict[str, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._headers = {"X-API-Key": self.api_key}

    async def send_receipt_validation(
        self, request: GatewayReceiptRequest
    ) -> ValidationResult:
        payload = {
            "client_id": request.client_id,
            "source": request.source,
        }
        response = await self._post_multipart(
            path="/api/v1/validate/receipt",
            data=payload,
            file_name=request.file.file_name,
            content=request.file.content,
            content_type=request.file.content_type,
        )
        return self._parse_validation_result(response)

    async def send_identity_validation(
        self, request: GatewayIdentityRequest
    ) -> ValidationResult:
        payload = {
            "client_id": request.client_id,
            "document_type": request.document_type,
        }
        response = await self._post_multipart(
            path="/api/v1/validate/identity",
            data=payload,
            file_name=request.file.file_name,
            content=request.file.content,
            content_type=request.file.content_type,
        )
        return self._parse_validation_result(response)

    async def _post_multipart(
        self,
        *,
        path: str,
        data: dict[str, str],
        file_name: str,
        content: bytes,
        content_type: str,
    ) -> dict:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                headers=self._headers,
                data=data,
                files={"file": (file_name, content, content_type)},
            )

        if response.is_success:
            return response.json()

        detail = self._extract_error_detail(response)
        raise ValidationRequestError(response.status_code, detail)

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or "Gateway request failed."

        if isinstance(payload, dict) and "detail" in payload:
            detail = payload["detail"]
            if isinstance(detail, str):
                return detail
            return str(detail)

        return "Gateway request failed."

    @staticmethod
    def _parse_validation_result(payload: dict) -> ValidationResult:
        return ValidationResult(
            document_type=str(payload.get("document_type", "")),
            decision=str(payload.get("decision", "")),
            final_score=float(payload.get("final_score", 0)),
            requires_human_review=bool(payload.get("requires_human_review", False)),
            extracted_data=dict(payload.get("extracted_data", {})),
            fraud_indicators=list(payload.get("fraud_indicators", [])),
            breakdown=dict(payload.get("breakdown", {})),
            is_expired=payload.get("is_expired"),
        )
