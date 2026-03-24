from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    gateway_base_url: str = Field(..., alias="GATEWAY_BASE_URL")
    gateway_api_key: str = Field(..., alias="GATEWAY_API_KEY")
    gateway_timeout_seconds: float = Field(30.0, alias="GATEWAY_TIMEOUT_SECONDS")
    client_registry_csv_path: str = Field(
        "config/client_registry.csv",
        alias="CLIENT_REGISTRY_CSV_PATH",
    )
    access_code_csv_path: str = Field(
        "config/access_codes.csv",
        alias="ACCESS_CODE_CSV_PATH",
    )
    telegram_gateway_receipt_source: str | None = Field(
        None,
        alias="TELEGRAM_GATEWAY_RECEIPT_SOURCE",
    )
    whatsapp_gateway_receipt_source: str | None = Field(
        None,
        alias="WHATSAPP_GATEWAY_RECEIPT_SOURCE",
    )


def get_settings() -> Settings:
    return Settings()
