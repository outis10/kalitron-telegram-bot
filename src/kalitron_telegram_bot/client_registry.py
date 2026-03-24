from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from kalitron_telegram_bot.application import ClientOnboardingRegistrar, ClientResolver
from kalitron_telegram_bot.domain import ChannelIdentity, InputChannel
from kalitron_telegram_bot.errors import ClientOnboardingError, ClientResolutionError


@dataclass(slots=True)
class ClientRegistryEntry:
    client_id: str
    channel: InputChannel
    user_id: str | None = None
    chat_id: str | None = None
    username: str | None = None
    phone_number: str | None = None


class CsvClientResolver(ClientResolver):
    def __init__(self, csv_path: str) -> None:
        self._csv_path = Path(csv_path)

    def resolve_client_id(self, identity: ChannelIdentity) -> str:
        entries = self._load_entries()
        candidates = [entry for entry in entries if entry.channel is identity.channel]

        for entry in candidates:
            if entry.user_id and identity.user_id and entry.user_id == identity.user_id:
                return entry.client_id
            if entry.chat_id and identity.chat_id and entry.chat_id == identity.chat_id:
                return entry.client_id
            if (
                entry.username
                and identity.username
                and entry.username == identity.username
            ):
                return entry.client_id
            if (
                entry.phone_number
                and identity.phone_number
                and entry.phone_number == identity.phone_number
            ):
                return entry.client_id

        raise ClientResolutionError(
            f"No client mapping found for channel '{identity.channel.value}'."
        )

    def _load_entries(self) -> list[ClientRegistryEntry]:
        if not self._csv_path.exists():
            raise ClientResolutionError(
                f"Client registry CSV not found at '{self._csv_path}'."
            )

        entries: list[ClientRegistryEntry] = []
        with self._csv_path.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            required_columns = {
                "client_id",
                "channel",
                "user_id",
                "chat_id",
                "username",
                "phone_number",
            }
            if not reader.fieldnames or not required_columns.issubset(
                reader.fieldnames
            ):
                raise ClientResolutionError(
                    "Client registry CSV must include: "
                    "client_id, channel, user_id, chat_id, username, phone_number."
                )

            for row in reader:
                channel_raw = (row.get("channel") or "").strip().lower()
                if not channel_raw:
                    continue

                try:
                    channel = InputChannel(channel_raw)
                except ValueError as exc:
                    raise ClientResolutionError(
                        f"Unsupported channel '{channel_raw}' in client registry."
                    ) from exc

                entries.append(
                    ClientRegistryEntry(
                        client_id=(row.get("client_id") or "").strip(),
                        channel=channel,
                        user_id=self._clean_optional(row.get("user_id")),
                        chat_id=self._clean_optional(row.get("chat_id")),
                        username=self._clean_optional(row.get("username")),
                        phone_number=self._clean_optional(row.get("phone_number")),
                    )
                )

        if not entries:
            raise ClientResolutionError("Client registry CSV is empty.")

        return entries

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        cleaned = (value or "").strip()
        return cleaned or None


@dataclass(slots=True)
class AccessCodeEntry:
    access_code: str
    client_id: str
    channel: InputChannel
    used: bool = False
    expires_at: datetime | None = None
    used_at: datetime | None = None


class CsvClientOnboardingRegistrar(ClientOnboardingRegistrar):
    def __init__(
        self, client_registry_csv_path: str, access_code_csv_path: str
    ) -> None:
        self._client_registry_csv_path = Path(client_registry_csv_path)
        self._access_code_csv_path = Path(access_code_csv_path)

    def register_identity(self, access_code: str, identity: ChannelIdentity) -> str:
        normalized_code = access_code.strip().upper()
        if not normalized_code:
            raise ClientOnboardingError("Debes enviar un codigo de acceso valido.")

        existing_client_id = self._try_resolve_existing(identity)
        if existing_client_id:
            return existing_client_id

        access_codes = self._load_access_codes()
        matched_entry = self._find_access_code(
            access_codes, normalized_code, identity.channel
        )
        if matched_entry is None:
            raise ClientOnboardingError("Codigo invalido, expirado o ya usado.")

        self._append_client_identity(matched_entry.client_id, identity)
        self._mark_access_code_as_used(access_codes, matched_entry)
        return matched_entry.client_id

    def _try_resolve_existing(self, identity: ChannelIdentity) -> str | None:
        try:
            return CsvClientResolver(
                str(self._client_registry_csv_path)
            ).resolve_client_id(identity)
        except ClientResolutionError:
            return None

    def _load_access_codes(self) -> list[AccessCodeEntry]:
        if not self._access_code_csv_path.exists():
            raise ClientOnboardingError(
                f"Access code CSV not found at '{self._access_code_csv_path}'."
            )

        entries: list[AccessCodeEntry] = []
        with self._access_code_csv_path.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            required_columns = {
                "access_code",
                "client_id",
                "channel",
                "used",
                "expires_at",
                "used_at",
            }
            if not reader.fieldnames or not required_columns.issubset(
                reader.fieldnames
            ):
                raise ClientOnboardingError(
                    "Access code CSV must include: "
                    "access_code, client_id, channel, used, expires_at, used_at."
                )

            for row in reader:
                raw_channel = (row.get("channel") or "").strip().lower()
                try:
                    channel = InputChannel(raw_channel)
                except ValueError as exc:
                    raise ClientOnboardingError(
                        f"Unsupported channel '{raw_channel}' in access code CSV."
                    ) from exc

                entries.append(
                    AccessCodeEntry(
                        access_code=(row.get("access_code") or "").strip().upper(),
                        client_id=(row.get("client_id") or "").strip(),
                        channel=channel,
                        used=(row.get("used") or "").strip().lower() == "true",
                        expires_at=self._parse_optional_datetime(row.get("expires_at")),
                        used_at=self._parse_optional_datetime(row.get("used_at")),
                    )
                )

        return entries

    @staticmethod
    def _find_access_code(
        access_codes: list[AccessCodeEntry],
        access_code: str,
        channel: InputChannel,
    ) -> AccessCodeEntry | None:
        for entry in access_codes:
            if (
                entry.channel is channel
                and entry.access_code == access_code
                and not entry.used
                and not CsvClientOnboardingRegistrar._is_expired(entry)
            ):
                return entry
        return None

    @staticmethod
    def _is_expired(entry: AccessCodeEntry) -> bool:
        if entry.expires_at is None:
            return False
        return entry.expires_at < datetime.now(UTC)

    def _append_client_identity(
        self, client_id: str, identity: ChannelIdentity
    ) -> None:
        if not self._client_registry_csv_path.exists():
            raise ClientOnboardingError(
                f"Client registry CSV not found at '{self._client_registry_csv_path}'."
            )

        with self._client_registry_csv_path.open(
            "a", newline="", encoding="utf-8"
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "client_id",
                    "channel",
                    "user_id",
                    "chat_id",
                    "username",
                    "phone_number",
                ],
            )
            writer.writerow(
                {
                    "client_id": client_id,
                    "channel": identity.channel.value,
                    "user_id": identity.user_id or "",
                    "chat_id": identity.chat_id or "",
                    "username": identity.username or "",
                    "phone_number": identity.phone_number or "",
                }
            )

    def _mark_access_code_as_used(
        self,
        access_codes: list[AccessCodeEntry],
        matched_entry: AccessCodeEntry,
    ) -> None:
        with self._access_code_csv_path.open(
            "w", newline="", encoding="utf-8"
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "access_code",
                    "client_id",
                    "channel",
                    "used",
                    "expires_at",
                    "used_at",
                ],
            )
            writer.writeheader()
            used_at_now = datetime.now(UTC).replace(microsecond=0).isoformat()
            for entry in access_codes:
                used = entry.used
                used_at = self._format_optional_datetime(entry.used_at)
                if (
                    entry.access_code == matched_entry.access_code
                    and entry.channel is matched_entry.channel
                    and entry.client_id == matched_entry.client_id
                ):
                    used = True
                    used_at = used_at_now
                writer.writerow(
                    {
                        "access_code": entry.access_code,
                        "client_id": entry.client_id,
                        "channel": entry.channel.value,
                        "used": "true" if used else "false",
                        "expires_at": self._format_optional_datetime(entry.expires_at),
                        "used_at": used_at,
                    }
                )

    @staticmethod
    def _parse_optional_datetime(value: str | None) -> datetime | None:
        cleaned = (value or "").strip()
        if not cleaned:
            return None
        normalized = cleaned.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ClientOnboardingError(
                f"Invalid datetime value '{cleaned}' in access code CSV."
            ) from exc
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _format_optional_datetime(value: datetime | None) -> str:
        if value is None:
            return ""
        return value.astimezone(UTC).replace(microsecond=0).isoformat()
