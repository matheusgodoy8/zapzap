"""Model for local attendant-identification settings."""

from __future__ import annotations

from zapzap.core.config.settings.attendant_signature import (
    AttendantSignatureSettings,
)
from zapzap.features.accounts.domain.user import User


class AttendantSignatureSettingsModel:
    """Expose the attendant signature domain to its settings page."""

    def __init__(self, account_provider=None) -> None:
        self._account_provider = account_provider or User.select
        self._settings = None

    def accounts(self):
        return list(self._account_provider())

    @property
    def account_id(self):
        return self._settings.account_id if self._settings else None

    def select_account(self, account_id) -> None:
        self._settings = AttendantSignatureSettings(account_id)

    def _selected_settings(self) -> AttendantSignatureSettings:
        if self._settings is None:
            raise RuntimeError("No attendant-signature account selected")
        return self._settings

    @property
    def enabled(self) -> bool:
        return self._selected_settings().enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._selected_settings().enabled = value

    @property
    def attendant_name(self) -> str:
        return self._selected_settings().attendant_name

    @attendant_name.setter
    def attendant_name(self, value: str) -> None:
        self._selected_settings().attendant_name = value

    @property
    def sign_text_messages(self) -> bool:
        return self._selected_settings().sign_text_messages

    @sign_text_messages.setter
    def sign_text_messages(self, value: bool) -> None:
        self._selected_settings().sign_text_messages = value

    @property
    def sign_media_captions(self) -> bool:
        return self._selected_settings().sign_media_captions

    @sign_media_captions.setter
    def sign_media_captions(self, value: bool) -> None:
        self._selected_settings().sign_media_captions = value

    @property
    def sign_empty_media(self) -> bool:
        return self._selected_settings().sign_empty_media

    @sign_empty_media.setter
    def sign_empty_media(self, value: bool) -> None:
        self._selected_settings().sign_empty_media = value
