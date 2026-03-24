from dataclasses import dataclass

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from kalitron_telegram_bot.handlers import TelegramBotHandlers


@dataclass(slots=True)
class TelegramChannelAdapter:
    application: Application
    handlers: TelegramBotHandlers

    def register(self) -> None:
        self.application.add_handler(CommandHandler("start", self.handlers.start))
        self.application.add_handler(CommandHandler("receipt", self.handlers.receipt))
        self.application.add_handler(CommandHandler("identity", self.handlers.identity))
        self.application.add_handler(
            MessageHandler(
                filters.PHOTO | filters.Document.IMAGE, self.handlers.handle_file
            )
        )
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.text_message)
        )
