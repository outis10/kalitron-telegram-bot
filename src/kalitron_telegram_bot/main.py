from telegram.ext import Application

from kalitron_telegram_bot.application import OnboardingUseCases, ValidationUseCases
from kalitron_telegram_bot.client_registry import (
    CsvClientOnboardingRegistrar,
    CsvClientResolver,
)
from kalitron_telegram_bot.config import get_settings
from kalitron_telegram_bot.gateway_adapter import (
    GatewayChannelMapping,
    GatewayValidationAdapter,
)
from kalitron_telegram_bot.gateway_http_client import GatewayHttpClient
from kalitron_telegram_bot.handlers import TelegramBotHandlers
from kalitron_telegram_bot.session_store import SessionStore
from kalitron_telegram_bot.telegram_adapter import TelegramChannelAdapter


def build_application() -> Application:
    settings = get_settings()
    gateway_http_client = GatewayHttpClient(
        base_url=settings.gateway_base_url,
        api_key=settings.gateway_api_key,
        timeout_seconds=settings.gateway_timeout_seconds,
    )
    gateway_adapter = GatewayValidationAdapter(
        http_client=gateway_http_client,
        channel_mapping=GatewayChannelMapping.from_settings(
            telegram_receipt_source=settings.telegram_gateway_receipt_source,
            whatsapp_receipt_source=settings.whatsapp_gateway_receipt_source,
        ),
    )
    handlers = TelegramBotHandlers(
        onboarding_use_cases=OnboardingUseCases(
            onboarding_registrar=CsvClientOnboardingRegistrar(
                client_registry_csv_path=settings.client_registry_csv_path,
                access_code_csv_path=settings.access_code_csv_path,
            )
        ),
        validation_use_cases=ValidationUseCases(
            client_resolver=CsvClientResolver(settings.client_registry_csv_path),
            validation_gateway=gateway_adapter,
        ),
        session_store=SessionStore(),
    )

    application = Application.builder().token(settings.telegram_bot_token).build()
    TelegramChannelAdapter(application=application, handlers=handlers).register()
    return application


def main() -> None:
    build_application().run_polling()


if __name__ == "__main__":
    main()
