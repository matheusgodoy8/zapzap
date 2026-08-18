"""Local attendant-identification settings."""

from __future__ import annotations

from zapzap.core.config.settings.base import BaseSettings


class AttendantSignatureSettings(BaseSettings):
    """Semantic access to one account's local signature preferences."""

    def __init__(self, account_id: str | int) -> None:
        account_key = str(account_id).strip()
        if not account_key:
            raise ValueError("account_id must not be empty")
        self.account_id = account_id
        self._prefix = f"attendant_signature/accounts/{account_key}"

    def _setting(self, field: str, default):
        return (f"{self._prefix}/{field}", default)

    @property
    def enabled(self) -> bool:
        return self._get_bool(self._setting("enabled", False))

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._set_bool(self._setting("enabled", False), value)

    @property
    def attendant_name(self) -> str:
        return self._get_str(self._setting("name", "")).strip()

    @attendant_name.setter
    def attendant_name(self, value: str) -> None:
        self._set_str(self._setting("name", ""), value.strip())

    @property
    def sign_text_messages(self) -> bool:
        return self._get_bool(
            self._setting("sign_text_messages", True)
        )

    @sign_text_messages.setter
    def sign_text_messages(self, value: bool) -> None:
        self._set_bool(
            self._setting("sign_text_messages", True),
            value,
        )

    @property
    def sign_media_captions(self) -> bool:
        return self._get_bool(
            self._setting("sign_media_captions", True)
        )

    @sign_media_captions.setter
    def sign_media_captions(self, value: bool) -> None:
        self._set_bool(
            self._setting("sign_media_captions", True),
            value,
        )

    @property
    def sign_empty_media(self) -> bool:
        return self._get_bool(self._setting("sign_empty_media", False))

    @sign_empty_media.setter
    def sign_empty_media(self, value: bool) -> None:
        self._set_bool(
            self._setting("sign_empty_media", False),
            value,
        )

    def runtime_config(self, *, debug: bool = False) -> dict[str, object]:
        """Return the safely serializable configuration consumed by JavaScript."""
        name = self.attendant_name
        return {
            "enabled": self.enabled and bool(name),
            "attendantName": name,
            "signTextMessages": self.sign_text_messages,
            "signMediaCaptions": self.sign_media_captions,
            "signEmptyMedia": self.sign_empty_media,
            "debug": bool(debug),
        }
