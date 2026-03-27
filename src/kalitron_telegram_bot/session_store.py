from kalitron_telegram_bot.domain import ClientCaseSession, PendingValidation


class SessionStore:
    def __init__(self) -> None:
        self._pending_by_chat: dict[int, PendingValidation] = {}
        self._case_by_chat: dict[int, ClientCaseSession] = {}

    def set_pending(self, chat_id: int, pending: PendingValidation) -> None:
        self._pending_by_chat[chat_id] = pending

    def pop_pending(self, chat_id: int) -> PendingValidation | None:
        return self._pending_by_chat.pop(chat_id, None)

    def get_pending(self, chat_id: int) -> PendingValidation | None:
        return self._pending_by_chat.get(chat_id)

    def clear_pending(self, chat_id: int) -> None:
        self._pending_by_chat.pop(chat_id, None)

    def set_case(self, chat_id: int, case_session: ClientCaseSession) -> None:
        self._case_by_chat[chat_id] = case_session

    def get_case(self, chat_id: int) -> ClientCaseSession | None:
        return self._case_by_chat.get(chat_id)

    def pop_case(self, chat_id: int) -> ClientCaseSession | None:
        return self._case_by_chat.pop(chat_id, None)
