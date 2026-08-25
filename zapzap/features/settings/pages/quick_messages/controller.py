"""Controller for quick-message CRUD and live WebView updates."""

from __future__ import annotations

from gettext import gettext as _

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from zapzap.features.alerts.alert_manager import AlertManager
from zapzap.features.settings.pages.quick_messages.model import (
    QuickMessagesSettingsModel,
)
from zapzap.features.settings.pages.quick_messages.view import (
    QuickMessageCard,
    QuickMessageEditorDialog,
    QuickMessagesSettingsView,
)
from zapzap.ui.primitives import Button


class QuickMessagesSettingsController(QuickMessagesSettingsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = QuickMessagesSettingsModel()
        self._accounts = self.model.accounts()
        self.add_button.clicked.connect(self._add_message)
        self.search_edit.textChanged.connect(self._render_messages)
        self._render_messages()

    def _render_messages(self):
        query = self.search_edit.text().strip().casefold()
        messages = self.model.messages()
        if query:
            messages = [
                item
                for item in messages
                if query in f"{item['title']}\n{item['content']}".casefold()
            ]
        self.clear_cards()
        account_names = {
            str(account.id): account.name or _("Unnamed account")
            for account in self._accounts
        }
        for message in messages:
            card = QuickMessageCard(message, account_names, self.cards_widget)
            card.edit_requested.connect(self._edit_message)
            card.remove_requested.connect(self._remove_message)
            card.active_changed.connect(self._set_active)
            self.add_card(card)
        self.set_empty_state(not messages, bool(query))

    def _add_message(self):
        dialog = QuickMessageEditorDialog(self._accounts, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.model.create(**dialog.values())
        self.search_edit.clear()
        self._render_messages()
        self._apply_to_pages()

    def _message(self, message_id):
        return next(
            (item for item in self.model.messages() if item["id"] == message_id),
            None,
        )

    def _edit_message(self, message_id):
        message = self._message(message_id)
        if message is None:
            return
        dialog = QuickMessageEditorDialog(
            self._accounts, message=message, parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.model.update(message_id, **dialog.values())
        self._render_messages()
        self._apply_to_pages()

    def _remove_message(self, message_id):
        message = self._message(message_id)
        if message is None:
            return
        action = AlertManager.action_dialog(
            self,
            _("Remove quick message?"),
            _("The message “{}” will be deleted.").format(message["title"]),
            _("This action cannot be undone."),
            AlertManager.warning_icon,
            (
                ("cancel", _("Cancel"), QMessageBox.ButtonRole.RejectRole),
                (
                    "remove",
                    _("Remove"),
                    QMessageBox.ButtonRole.DestructiveRole,
                    Button.DANGER,
                ),
            ),
            default_action="cancel",
        )
        if action != "remove":
            return
        self.model.delete(message_id)
        self._render_messages()
        self._apply_to_pages()

    def _set_active(self, message_id, active):
        if self._message(message_id) is None:
            return
        self.model.update(message_id, active=active)
        self._apply_to_pages()

    @staticmethod
    def _apply_to_pages():
        app = QApplication.instance()
        get_window = getattr(app, "getWindow", None)
        if not callable(get_window):
            return
        browser = getattr(get_window(), "browser", None)
        apply_settings = getattr(
            browser,
            "apply_quick_messages_settings_all_pages",
            None,
        )
        if callable(apply_settings):
            apply_settings()
