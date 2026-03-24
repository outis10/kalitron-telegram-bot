from kalitron_telegram_bot.domain import PendingValidation


class SessionStore:
    def __init__(self) -> None:
        self._pending_by_chat: dict[int, PendingValidation] = {}

    def set_pending(self, chat_id: int, pending: PendingValidation) -> None:
        self._pending_by_chat[chat_id] = pending

    def pop_pending(self, chat_id: int) -> PendingValidation | None:
        return self._pending_by_chat.pop(chat_id, None)

    def get_pending(self, chat_id: int) -> PendingValidation | None:
        return self._pending_by_chat.get(chat_id)
