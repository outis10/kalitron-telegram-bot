from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kalitron_telegram_bot.domain import (
    CaseSubmissionDocument,
    ChannelIdentity,
    IncomingDocument,
    ValidateIdentityCommand,
    ValidateReceiptCommand,
    ValidationCase,
    ValidationResult,
)


class ClientResolver(Protocol):
    def resolve_client_id(self, identity: ChannelIdentity) -> str: ...


class ClientOnboardingRegistrar(Protocol):
    def register_identity(self, access_code: str, identity: ChannelIdentity) -> str: ...


class ValidationGateway(Protocol):
    async def validate_receipt(
        self, command: ValidateReceiptCommand
    ) -> ValidationResult: ...

    async def validate_identity(
        self, command: ValidateIdentityCommand
    ) -> ValidationResult: ...

    async def create_validation_case(
        self,
        client_id: str,
        identity: ChannelIdentity,
        documents: list[CaseSubmissionDocument],
    ) -> tuple[str, str]: ...

    async def get_validation_case(self, case_id: str) -> ValidationCase: ...


@dataclass(slots=True)
class ValidationUseCases:
    client_resolver: ClientResolver
    validation_gateway: ValidationGateway

    async def validate_receipt(
        self, command: ValidateReceiptCommand
    ) -> ValidationResult:
        resolved_command = ValidateReceiptCommand(
            document=self._resolve_document_client(command.document),
            document_type=command.document_type,
        )
        return await self.validation_gateway.validate_receipt(resolved_command)

    async def validate_identity(
        self, command: ValidateIdentityCommand
    ) -> ValidationResult:
        resolved_command = ValidateIdentityCommand(
            document=self._resolve_document_client(command.document),
            document_type=command.document_type,
        )
        return await self.validation_gateway.validate_identity(resolved_command)

    async def create_validation_case(
        self,
        client_id: str,
        identity: ChannelIdentity,
        documents: list[CaseSubmissionDocument],
    ) -> tuple[str, str]:
        resolved_documents = [
            CaseSubmissionDocument(
                document_type=document.document_type,
                document=self._resolve_document_client(
                    IncomingDocument(
                        sender=document.document.sender,
                        file_name=document.document.file_name,
                        content_type=document.document.content_type,
                        content=document.document.content,
                        client_id=client_id,
                    )
                ),
            )
            for document in documents
        ]
        return await self.validation_gateway.create_validation_case(
            client_id, identity, resolved_documents
        )

    async def get_validation_case(self, case_id: str) -> ValidationCase:
        return await self.validation_gateway.get_validation_case(case_id)

    def _resolve_document_client(self, document: IncomingDocument) -> IncomingDocument:
        client_id = document.client_id or self.client_resolver.resolve_client_id(
            document.sender
        )
        return IncomingDocument(
            sender=document.sender,
            file_name=document.file_name,
            content_type=document.content_type,
            content=document.content,
            client_id=client_id,
        )


@dataclass(slots=True)
class OnboardingUseCases:
    onboarding_registrar: ClientOnboardingRegistrar

    def register_identity(self, access_code: str, identity: ChannelIdentity) -> str:
        return self.onboarding_registrar.register_identity(access_code, identity)
