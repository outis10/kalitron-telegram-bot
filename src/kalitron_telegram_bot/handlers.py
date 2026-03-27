from __future__ import annotations

from dataclasses import dataclass

from telegram import Update
from telegram.ext import ContextTypes

from kalitron_telegram_bot.application import OnboardingUseCases, ValidationUseCases
from kalitron_telegram_bot.domain import (
    ChannelIdentity,
    IdentityDocumentType,
    IncomingDocument,
    InputChannel,
    PendingValidation,
    ReceiptDocumentType,
    ValidateIdentityCommand,
    ValidateReceiptCommand,
    ValidationKind,
    ValidationResult,
)
from kalitron_telegram_bot.errors import (
    ClientOnboardingError,
    ClientResolutionError,
    ValidationCompatibilityError,
    ValidationIntegrationError,
    ValidationRequestError,
    ValidationTransportError,
)
from kalitron_telegram_bot.session_store import SessionStore

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


@dataclass(slots=True)
class TelegramBotHandlers:
    onboarding_use_cases: OnboardingUseCases
    validation_use_cases: ValidationUseCases
    session_store: SessionStore

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        if not update.message:
            return

        await update.message.reply_text(
            "Usa /receipt [RECEIPT|ADDRESS_PROOF] y luego envía una imagen para validar un recibo.\n"
            "Usa /identity <INE|INE_REVERSO|PASAPORTE|LICENCIA> y luego envía una imagen para validar una identificación.\n"
            "Si aún no estás registrado, envía: ALTA TU_CODIGO"
        )

    async def text_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:  # noqa: ARG002
        if not update.message or not update.message.text:
            return

        text = update.message.text.strip()
        if not text:
            return

        upper_text = text.upper()
        if not upper_text.startswith("ALTA "):
            await update.message.reply_text(
                "Mensaje no reconocido. Usa ALTA <codigo>, /receipt o /identity."
            )
            return

        parts = text.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            await update.message.reply_text("Usa ALTA <codigo>.")
            return

        identity = self._build_sender_identity(update)
        try:
            self.onboarding_use_cases.register_identity(
                parts[1].strip(),
                identity,
            )
        except ClientOnboardingError as exc:
            await update.message.reply_text(f"No se pudo completar el alta: {exc}")
            return

        await update.message.reply_text(
            "Alta completada. Ya puedes usar /receipt o /identity."
        )

    async def receipt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        if not update.effective_chat or not update.message:
            return

        document_type = ReceiptDocumentType.RECEIPT
        if context.args:
            try:
                document_type = ReceiptDocumentType(context.args[0].upper())
            except ValueError:
                await update.message.reply_text(
                    "Tipo inválido. Usa RECEIPT o ADDRESS_PROOF."
                )
                return

        self.session_store.set_pending(
            update.effective_chat.id,
            PendingValidation(
                kind=ValidationKind.RECEIPT,
                receipt_document_type=document_type,
            ),
        )
        await update.message.reply_text(
            f"Envía la imagen del documento para {document_type.value} en JPG, PNG o WebP."
        )

    async def identity(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.effective_chat or not update.message:
            return

        if not context.args:
            await update.message.reply_text("Usa /identity <INE|PASAPORTE|LICENCIA>.")
            return

        try:
            document_type = IdentityDocumentType(context.args[0].upper())
        except ValueError:
            await update.message.reply_text(
                "Tipo inválido. Usa INE, PASAPORTE o LICENCIA."
            )
            return

        self.session_store.set_pending(
            update.effective_chat.id,
            PendingValidation(
                kind=ValidationKind.IDENTITY,
                identity_document_type=document_type,
            ),
        )
        await update.message.reply_text(
            f"Envía la imagen de la identificación para {document_type.value}."
        )

    async def handle_file(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:  # noqa: ARG002
        if not update.effective_chat or not update.message:
            return

        pending = self.session_store.get_pending(update.effective_chat.id)
        if not pending:
            await update.message.reply_text(
                "Primero indica qué quieres validar con /receipt o /identity."
            )
            return

        try:
            submission = await self._build_submission(update)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return

        await update.message.reply_text("Procesando documento...")

        try:
            if pending.kind is ValidationKind.RECEIPT:
                result = await self.validation_use_cases.validate_receipt(
                    ValidateReceiptCommand(
                        document=submission,
                        document_type=pending.receipt_document_type,
                    )
                )
            else:
                if pending.identity_document_type is None:
                    raise ValidationCompatibilityError(
                        "Falta document_type para la validación de identidad."
                    )
                result = await self.validation_use_cases.validate_identity(
                    ValidateIdentityCommand(
                        document=submission,
                        document_type=pending.identity_document_type,
                    )
                )
        except ClientResolutionError as exc:
            await update.message.reply_text(
                f"Acceso no autorizado: {exc}. Si tienes codigo, envia ALTA <codigo>."
            )
            return
        except ValidationCompatibilityError as exc:
            await update.message.reply_text(f"Configuración incompatible: {exc}")
            return
        except ValidationRequestError as exc:
            await update.message.reply_text(
                f"El gateway respondió con {exc.status_code}: {exc.detail}"
            )
            return
        except ValidationTransportError as exc:
            await update.message.reply_text(str(exc))
            return
        except ValidationIntegrationError as exc:
            await update.message.reply_text(
                f"No se pudo completar la validación: {exc}"
            )
            return

        self.session_store.pop_pending(update.effective_chat.id)
        await update.message.reply_text(self._format_result(result))

    async def _build_submission(self, update: Update) -> IncomingDocument:
        assert update.effective_user is not None
        assert update.message is not None

        if update.message.photo:
            telegram_file = await update.message.photo[-1].get_file()
            content = await telegram_file.download_as_bytearray()
            return IncomingDocument(
                sender=self._build_sender_identity(update),
                file_name=f"telegram-photo-{telegram_file.file_unique_id}.jpg",
                content_type="image/jpeg",
                content=bytes(content),
            )

        document = update.message.document
        if not document:
            raise ValueError("Envía una imagen como foto o archivo.")

        mime_type = (document.mime_type or "").lower()
        if mime_type not in ALLOWED_MIME_TYPES:
            raise ValueError("Formato no soportado. Usa JPG, PNG o WebP.")

        telegram_file = await document.get_file()
        content = await telegram_file.download_as_bytearray()
        file_name = (
            document.file_name or f"telegram-document-{telegram_file.file_unique_id}"
        )
        return IncomingDocument(
            sender=self._build_sender_identity(update),
            file_name=file_name,
            content_type=mime_type,
            content=bytes(content),
        )

    @staticmethod
    def _build_sender_identity(update: Update) -> ChannelIdentity:
        assert update.effective_user is not None
        return ChannelIdentity(
            channel=InputChannel.TELEGRAM,
            user_id=str(update.effective_user.id),
            chat_id=str(update.effective_chat.id) if update.effective_chat else None,
            username=update.effective_user.username,
        )

    @staticmethod
    def _format_result(result: ValidationResult) -> str:
        lines = [
            f"Documento: {result.document_type}",
            f"Decisión: {result.decision}",
            f"Score final: {result.final_score:.2f}",
            f"Requiere revisión humana: {'sí' if result.requires_human_review else 'no'}",
        ]

        if result.is_expired is not None:
            lines.append(f"Expirado: {'sí' if result.is_expired else 'no'}")

        if result.extracted_data:
            extracted = ", ".join(
                f"{key}={value}"
                for key, value in result.extracted_data.items()
                if value
            )
            if extracted:
                lines.append(f"Datos extraídos: {extracted}")

        if result.fraud_indicators:
            lines.append("Indicadores de fraude: " + ", ".join(result.fraud_indicators))

        return "\n".join(lines)
