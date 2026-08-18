"""Controller for local attendant identification."""

from __future__ import annotations

from gettext import gettext as _

from PyQt6.QtWidgets import QApplication

from zapzap.features.settings.pages.attendant_signature.model import (
    AttendantSignatureSettingsModel,
)
from zapzap.features.settings.pages.attendant_signature.view import (
    AttendantSignatureSettingsView,
)


class AttendantSignatureSettingsController(AttendantSignatureSettingsView):
    """Persist settings and update only the selected WhatsApp account."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = AttendantSignatureSettingsModel()
        self._loading_account = False
        self._populate_accounts()
        self._connect_signals()
        self._select_initial_account()

    def _populate_accounts(self):
        self.account_combo.clear()
        for account in self.model.accounts():
            name = account.name or _("Unnamed account")
            self.account_combo.addItem(name, account.id)

    def _select_initial_account(self):
        if self.account_combo.count() == 0:
            self.account_row.setEnabled(False)
            for row in self.dependent_rows:
                row.setEnabled(False)
            self.enabled_row.setEnabled(False)
            return

        current_account_id = self._current_account_id()
        index = self.account_combo.findData(current_account_id)
        self.account_combo.setCurrentIndex(index if index >= 0 else 0)
        self._select_account(self.account_combo.currentData())

    def _load_settings(self):
        self.enabled_row.checkbox.setChecked(self.model.enabled)
        self.name_row.line_edit.setText(self.model.attendant_name)
        self.text_messages_row.checkbox.setChecked(
            self.model.sign_text_messages
        )
        self.media_captions_row.checkbox.setChecked(
            self.model.sign_media_captions
        )
        self.empty_media_row.checkbox.setChecked(
            self.model.sign_empty_media
        )

    def _connect_signals(self):
        self.account_combo.currentIndexChanged.connect(
            self._on_account_changed
        )
        self.enabled_row.checkbox.toggled.connect(self._set_enabled)
        self.name_row.line_edit.editingFinished.connect(self._set_name)
        self.text_messages_row.checkbox.toggled.connect(
            self._set_sign_text_messages
        )
        self.media_captions_row.checkbox.toggled.connect(
            self._set_sign_media_captions
        )
        self.empty_media_row.checkbox.toggled.connect(
            self._set_sign_empty_media
        )

    def _sync_enabled_state(self):
        enabled = self.enabled_row.checkbox.isChecked()
        self.name_row.setEnabled(enabled)
        self.text_messages_row.setEnabled(enabled)
        self.media_captions_row.setEnabled(enabled)
        self.empty_media_row.setEnabled(
            enabled and self.media_captions_row.checkbox.isChecked()
        )

    def _select_account(self, account_id):
        if account_id is None:
            return
        self._loading_account = True
        try:
            self.model.select_account(account_id)
            self._load_settings()
            self._sync_enabled_state()
        finally:
            self._loading_account = False

    def _on_account_changed(self, _index):
        if self._loading_account:
            return
        self._save_name_if_changed(apply=True)
        self._select_account(self.account_combo.currentData())

    def _set_enabled(self, enabled: bool):
        if self._loading_account:
            return
        self.model.enabled = enabled
        self._sync_enabled_state()
        self._apply_to_selected_page()

    def _set_name(self):
        if self._loading_account:
            return
        self._save_name_if_changed(apply=True)

    def _save_name_if_changed(self, *, apply: bool):
        if self.model.account_id is None:
            return
        previous = self.model.attendant_name
        self.model.attendant_name = self.name_row.line_edit.text()
        normalized = self.model.attendant_name
        if self.name_row.line_edit.text() != normalized:
            self.name_row.line_edit.setText(normalized)
        if apply and previous != normalized:
            self._apply_to_selected_page()

    def _set_sign_text_messages(self, enabled: bool):
        if self._loading_account:
            return
        self.model.sign_text_messages = enabled
        self._apply_to_selected_page()

    def _set_sign_media_captions(self, enabled: bool):
        if self._loading_account:
            return
        self.model.sign_media_captions = enabled
        self._sync_enabled_state()
        self._apply_to_selected_page()

    def _set_sign_empty_media(self, enabled: bool):
        if self._loading_account:
            return
        self.model.sign_empty_media = enabled
        self._apply_to_selected_page()

    @staticmethod
    def _current_account_id():
        app = QApplication.instance()
        get_window = getattr(app, "getWindow", None)
        if not callable(get_window):
            return None
        browser = getattr(get_window(), "browser", None)
        current_webview = getattr(browser, "current_webview", None)
        if not callable(current_webview):
            return None
        webview = current_webview()
        user = getattr(webview, "user", None)
        return getattr(user, "id", None)

    def _apply_to_selected_page(self):
        app = QApplication.instance()
        get_window = getattr(app, "getWindow", None)
        if not callable(get_window):
            return
        window = get_window()
        browser = getattr(window, "browser", None)
        apply_settings = getattr(
            browser,
            "apply_attendant_signature_settings_for_user_id",
            None,
        )
        if callable(apply_settings):
            apply_settings(self.model.account_id)
