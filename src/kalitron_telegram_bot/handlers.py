from __future__ import annotations

from dataclasses import dataclass

from telegram import Update
from telegram.ext import ContextTypes

from kalitron_telegram_bot.application import OnboardingUseCases, ValidationUseCases
from kalitron_telegram_bot.domain import (
    CaseStage,
    CaseSubmissionDocument,
    ChannelIdentity,
    ClientCaseSession,
    IdentityDocumentType,
    IncomingDocument,
    InputChannel,
    PendingValidation,
    ReceiptDocumentType,
    RemoteCaseStatus,
    ValidateIdentityCommand,
    ValidateReceiptCommand,
    ValidationCase,
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
            "Usa /client <CLIENT_ID> para iniciar un expediente de 3 documentos.\n"
            "Usa /receipt [RECEIPT|ADDRESS_PROOF] y luego envía una imagen para validar un recibo.\n"
            "Usa /identity <INE|INE_REVERSO|PASAPORTE|LICENCIA> y luego envía una imagen para validar una identificación.\n"
            "Usa /status para consultar el avance del expediente actual.\n"
            "Si aún no estás registrado, envía: ALTA TU_CODIGO"
        )

    async def client(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.message:
            return

        if not context.args or not context.args[0].strip():
            await update.message.reply_text("Usa /client <CLIENT_ID>.")
            return

        client_id = context.args[0].strip()
        self.session_store.clear_pending(update.effective_chat.id)
        self.session_store.set_case(
            update.effective_chat.id,
            ClientCaseSession(client_id=client_id),
        )
        await update.message.reply_text(
            "Expediente iniciado para "
            f"{client_id}. Envía primero la imagen de INE, luego INE_REVERSO y al final ADDRESS_PROOF."
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        if not update.effective_chat or not update.message:
            return

        case_session = self.session_store.get_case(update.effective_chat.id)
        if case_session:
            if case_session.remote_case_id:
                try:
                    remote_case = await self.validation_use_cases.get_validation_case(
                        case_session.remote_case_id
                    )
                except (
                    ValidationRequestError,
                    ValidationTransportError,
                    ValidationIntegrationError,
                ) as exc:
                    await update.message.reply_text(self._format_processing_error(exc))
                    return
                case_session.remote_status = remote_case.status
                if remote_case.status in {
                    RemoteCaseStatus.APPROVED,
                    RemoteCaseStatus.REJECTED,
                    RemoteCaseStatus.FAILED,
                }:
                    self.session_store.pop_case(update.effective_chat.id)
                await update.message.reply_text(
                    self._format_remote_case_status(remote_case)
                )
                return

            await update.message.reply_text(self._format_case_status(case_session))
            return

        pending = self.session_store.get_pending(update.effective_chat.id)
        if pending:
            await update.message.reply_text(
                "Hay una validación individual pendiente. Envía la imagen solicitada."
            )
            return

        await update.message.reply_text(
            "No hay expediente activo. Usa /client <CLIENT_ID>."
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

        case_session = self.session_store.get_case(update.effective_chat.id)
        if case_session:
            await self._handle_case_file(update, case_session)
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

    async def _handle_case_file(
        self, update: Update, case_session: ClientCaseSession
    ) -> None:
        assert update.effective_chat is not None
        assert update.message is not None

        if case_session.stage is CaseStage.PROCESSING:
            await update.message.reply_text(
                "El expediente ya está en procesamiento. Usa /status para consultar el avance."
            )
            return

        try:
            submission = await self._build_submission(update)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return

        next_document_type = case_session.next_expected_document_type()
        if next_document_type is None:
            await update.message.reply_text(
                "El expediente ya tiene los 3 documentos. Usa /status."
            )
            return

        case_session.uploaded_documents[next_document_type] = IncomingDocument(
            sender=submission.sender,
            file_name=submission.file_name,
            content_type=submission.content_type,
            content=submission.content,
            client_id=case_session.client_id,
        )
        case_session.last_error = None

        await update.message.reply_text(f"Documento {next_document_type} recibido.")

        following_document_type = case_session.next_expected_document_type()
        if following_document_type is not None:
            progress = len(case_session.uploaded_documents)
            await update.message.reply_text(
                f"Avance del expediente: {progress}/3. Envía ahora {following_document_type}."
            )
            return

        case_session.stage = CaseStage.PROCESSING
        await update.message.reply_text(
            "Se recibieron los 3 documentos. Expediente en proceso de verificación."
        )
        await self._submit_case(update, case_session)

    async def _submit_case(
        self, update: Update, case_session: ClientCaseSession
    ) -> None:
        assert update.effective_chat is not None
        assert update.message is not None

        try:
            (
                case_id,
                remote_status,
            ) = await self.validation_use_cases.create_validation_case(
                client_id=case_session.client_id,
                identity=self._build_sender_identity(update),
                documents=[
                    CaseSubmissionDocument(
                        document_type=document_type,
                        document=case_session.uploaded_documents[document_type],
                    )
                    for document_type in case_session.required_documents
                ],
            )
        except (
            ClientResolutionError,
            ValidationCompatibilityError,
            ValidationRequestError,
            ValidationTransportError,
            ValidationIntegrationError,
        ) as exc:
            case_session.stage = CaseStage.FAILED
            case_session.last_error = self._format_processing_error(exc)
            await update.message.reply_text(case_session.last_error)
            return

        case_session.remote_case_id = case_id
        case_session.remote_status = RemoteCaseStatus(remote_status)
        await update.message.reply_text(
            f"Expediente enviado al gateway. Case ID: {case_id}. Estado: {remote_status}. Usa /status para consultar el avance."
        )

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

    @staticmethod
    def _format_processing_error(exc: Exception) -> str:
        if isinstance(exc, ClientResolutionError):
            return (
                f"Acceso no autorizado: {exc}. Si tienes codigo, envia ALTA <codigo>."
            )
        if isinstance(exc, ValidationCompatibilityError):
            return f"Configuración incompatible: {exc}"
        if isinstance(exc, ValidationRequestError):
            return f"El gateway respondió con {exc.status_code}: {exc.detail}"
        if isinstance(exc, ValidationTransportError):
            return str(exc)
        return f"No se pudo completar la validación: {exc}"

    @staticmethod
    def _format_case_status(case_session: ClientCaseSession) -> str:
        uploaded = ", ".join(case_session.uploaded_documents) or "ninguno"
        next_document_type = case_session.next_expected_document_type()
        lines = [
            f"Cliente: {case_session.client_id}",
            f"Estado: {case_session.stage.value}",
            f"Documentos recibidos: {uploaded}",
        ]
        if next_document_type:
            lines.append(f"Siguiente documento: {next_document_type}")
        if case_session.remote_case_id:
            lines.append(f"Case ID remoto: {case_session.remote_case_id}")
        if case_session.remote_status:
            lines.append(f"Estado remoto: {case_session.remote_status.value}")
        if case_session.last_error:
            lines.append(f"Último error: {case_session.last_error}")
        return "\n".join(lines)

    @staticmethod
    def _format_remote_case_status(remote_case: ValidationCase) -> str:
        lines = [
            f"Case ID: {remote_case.case_id}",
            f"Cliente: {remote_case.client_id}",
            f"Estado: {remote_case.status.value}",
        ]
        if remote_case.authorization_status:
            lines.append(f"Autorización: {remote_case.authorization_status}")
        if remote_case.rejection_reason_text:
            lines.append(f"Motivo de rechazo: {remote_case.rejection_reason_text}")
        if remote_case.documents:
            lines.append(
                "Documentos: "
                + ", ".join(
                    f"{document.document_type}={document.status}"
                    for document in remote_case.documents
                )
            )
        return "\n".join(lines)
