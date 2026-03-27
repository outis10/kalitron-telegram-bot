from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from kalitron_telegram_bot.domain import ValidationResult
from kalitron_telegram_bot.errors import (
    ValidationRequestError,
    ValidationTransportError,
)
from kalitron_telegram_bot.gateway_contract import (
    GatewayCaseStatusResponse,
    GatewayCreateCaseRequest,
    GatewayCreateCaseResponse,
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
            "document_type": request.document_type,
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

    async def create_validation_case(
        self, request: GatewayCreateCaseRequest
    ) -> GatewayCreateCaseResponse:
        response = await self._post_json(
            path="/api/v1/validation-cases",
            payload={
                "client_id": request.client_id,
                "channel": request.channel,
                "chat_id": request.chat_id,
                "documents": [
                    {
                        "document_type": document.document_type,
                        "file_name": document.file_name,
                        "content_type": document.content_type,
                        "content_base64": document.content_base64,
                    }
                    for document in request.documents
                ],
            },
        )
        return GatewayCreateCaseResponse(
            case_id=str(response.get("case_id", "")),
            status=str(response.get("status", "")),
        )

    async def get_validation_case(self, case_id: str) -> GatewayCaseStatusResponse:
        response = await self._get_json(path=f"/api/v1/validation-cases/{case_id}")
        return GatewayCaseStatusResponse(case=self._parse_validation_case(response))

    async def _post_multipart(
        self,
        *,
        path: str,
        data: dict[str, str],
        file_name: str,
        content: bytes,
        content_type: str,
    ) -> dict:
        try:
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
        except httpx.TimeoutException as exc:
            raise ValidationTransportError("El gateway no respondió a tiempo.") from exc
        except httpx.RequestError as exc:
            raise ValidationTransportError(
                "No fue posible conectar con el gateway."
            ) from exc

        if response.is_success:
            return response.json()

        detail = self._extract_error_detail(response)
        raise ValidationRequestError(response.status_code, detail)

    async def _post_json(self, *, path: str, payload: dict) -> dict:
        response = await self._request_json("POST", path=path, json=payload)
        return response

    async def _get_json(self, *, path: str) -> dict:
        response = await self._request_json("GET", path=path)
        return response

    async def _request_json(
        self, method: str, *, path: str, json: dict | None = None
    ) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=self._headers,
                    json=json,
                )
        except httpx.TimeoutException as exc:
            raise ValidationTransportError("El gateway no respondió a tiempo.") from exc
        except httpx.RequestError as exc:
            raise ValidationTransportError(
                "No fue posible conectar con el gateway."
            ) from exc

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

    @staticmethod
    def _parse_validation_case(payload: dict):
        from kalitron_telegram_bot.domain import (
            CaseDocumentResult,
            RemoteCaseStatus,
            ValidationCase,
        )

        return ValidationCase(
            case_id=str(payload.get("case_id", "")),
            client_id=str(payload.get("client_id", "")),
            channel=str(payload.get("channel", "")),
            chat_id=str(payload.get("chat_id", "")),
            status=RemoteCaseStatus(str(payload.get("status", "FAILED"))),
            authorization_status=payload.get("authorization_status"),
            rejection_reason_code=payload.get("rejection_reason_code"),
            rejection_reason_text=payload.get("rejection_reason_text"),
            documents=[
                CaseDocumentResult(
                    document_id=str(document.get("document_id", "")),
                    document_type=str(document.get("document_type", "")),
                    file_name=str(document.get("file_name", "")),
                    status=str(document.get("status", "")),
                    error=document.get("error"),
                    result=dict(document.get("result", {})),
                )
                for document in payload.get("documents", [])
            ],
            consolidated_data=dict(payload.get("consolidated_data", {})),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
        )
