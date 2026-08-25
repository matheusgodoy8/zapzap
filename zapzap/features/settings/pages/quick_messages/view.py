"""Views for managing quick messages."""

from __future__ import annotations

from gettext import gettext as _

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from zapzap.features.alerts.alert_manager import AlertManager
from zapzap.ui.components import SettingsPage
from zapzap.ui.primitives import (
    Button,
    CheckBox,
    Label,
    LineEdit,
    TextEdit,
    ToggleSwitch,
)


class QuickMessageEditorDialog(QDialog):
    """Transactional editor for one message template."""

    def __init__(self, accounts, message=None, parent=None):
        super().__init__(parent)
        self._accounts = list(accounts)
        self._message = message or {}
        self.setWindowTitle(
            _("Edit quick message") if message else _("Add quick message")
        )
        self.setModal(True)
        self.setMinimumWidth(520)
        self._setup_ui()
        self._load_message()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(9)

        layout.addWidget(Label(_("Message name"), "row_title", self))
        self.title_edit = LineEdit(parent=self)
        self.title_edit.setPlaceholderText(_("Example: Quote"))
        self.title_edit.setMaxLength(120)
        self.title_edit.setAccessibleName(_("Message name"))
        layout.addWidget(self.title_edit)

        layout.addWidget(Label(_("Message"), "row_title", self))
        self.content_edit = TextEdit(parent=self)
        self.content_edit.setPlaceholderText(_("Enter the content…"))
        self.content_edit.setMinimumHeight(170)
        self.content_edit.setAccessibleName(_("Message"))
        layout.addWidget(self.content_edit)

        layout.addWidget(Label(_("Available for"), "row_title", self))
        self.all_accounts = CheckBox(_("All accounts"), self)
        self.all_accounts.setAccessibleDescription(
            _("Make this message available in every account.")
        )
        layout.addWidget(self.all_accounts)

        self.account_checks = {}
        self.account_box = QWidget(self)
        account_layout = QVBoxLayout(self.account_box)
        account_layout.setContentsMargins(20, 0, 0, 0)
        account_layout.setSpacing(2)
        for account in self._accounts:
            check = CheckBox(account.name or _("Unnamed account"), self.account_box)
            check.setProperty("accountId", str(account.id))
            self.account_checks[str(account.id)] = check
            account_layout.addWidget(check)
        layout.addWidget(self.account_box)

        status_row = QWidget(self)
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 5, 0, 0)
        self.active_label = Label(_("Activated"), "row_title", status_row)
        self.active_switch = ToggleSwitch(parent=status_row)
        self.active_switch.setAccessibleName(_("Status"))
        status_layout.addWidget(self.active_label, 1)
        status_layout.addWidget(self.active_switch)
        layout.addWidget(status_row)

        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 10, 0, 0)
        actions_layout.addStretch(1)
        self.cancel_button = Button(_("Cancel"), parent=actions)
        self.save_button = Button(_("Save"), Button.PRIMARY, actions)
        actions_layout.addWidget(self.cancel_button)
        actions_layout.addWidget(self.save_button)
        layout.addWidget(actions)

        self.all_accounts.toggled.connect(self._sync_account_state)
        self.active_switch.toggled.connect(
            lambda active: self.active_label.setText(
                _("Activated") if active else _("Deactivated")
            )
        )
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def _load_message(self):
        self.title_edit.setText(self._message.get("title", ""))
        self.content_edit.setPlainText(self._message.get("content", ""))
        selected = {str(value) for value in self._message.get("accounts", [])}
        self.all_accounts.setChecked(not selected)
        for account_id, check in self.account_checks.items():
            check.setChecked(account_id in selected)
        self.active_switch.setChecked(self._message.get("active", True))
        self._sync_account_state()

    def _sync_account_state(self):
        self.account_box.setEnabled(not self.all_accounts.isChecked())

    def accept(self):
        if (
            not self.title_edit.text().strip()
            or not self.content_edit.toPlainText().strip()
        ):
            AlertManager.warning(
                self,
                _("Quick messages"),
                _("Enter a name and message content before saving."),
            )
            return
        if (
            not self.all_accounts.isChecked()
            and not any(check.isChecked() for check in self.account_checks.values())
        ):
            AlertManager.warning(
                self,
                _("Quick messages"),
                _("Select at least one account or choose All accounts."),
            )
            return
        super().accept()

    def values(self):
        accounts = (
            []
            if self.all_accounts.isChecked()
            else [
                account_id
                for account_id, check in self.account_checks.items()
                if check.isChecked()
            ]
        )
        return {
            "title": self.title_edit.text().strip(),
            "content": self.content_edit.toPlainText().replace("\r\n", "\n"),
            "active": self.active_switch.isChecked(),
            "accounts": accounts,
        }


class QuickMessageCard(QFrame):
    edit_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)
    active_changed = pyqtSignal(str, bool)

    def __init__(self, message, account_names, parent=None):
        super().__init__(parent)
        self.message_id = message["id"]
        self.setObjectName("QuickMessageCard")
        self.setStyleSheet(
            "QFrame#QuickMessageCard { background: palette(base); border: 1px solid palette(mid); border-radius: 14px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(7)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        title = Label(message["title"], "row_title", header)
        title.setObjectName("QuickMessageTitle")
        self.active_switch = ToggleSwitch(parent=header)
        self.active_switch.setChecked(message["active"])
        self.active_switch.setAccessibleName(
            _("Activate {}").format(message["title"])
        )
        header_layout.addWidget(title, 1)
        header_layout.addWidget(self.active_switch)
        layout.addWidget(header)

        preview_text = message["content"].strip()
        self.preview = Label(preview_text, "row_description", self)
        self.preview.setObjectName("QuickMessagePreview")
        self.preview.setWordWrap(True)
        self.preview.setMaximumHeight(76)
        layout.addWidget(self.preview)

        scope = (
            _("All accounts")
            if not message["accounts"]
            else _("Accounts: {}").format(
                ", ".join(
                    account_names.get(value, value)
                    for value in message["accounts"]
                )
            )
        )
        scope_label = Label(scope, "row_description", self)
        scope_label.setObjectName("QuickMessageScope")
        layout.addWidget(scope_label)

        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 2, 0, 0)
        actions_layout.addStretch(1)
        edit_button = Button(_("Edit"), parent=actions)
        remove_button = Button(_("Remove"), Button.DANGER, actions)
        edit_button.setAccessibleName(_("Edit {}").format(message["title"]))
        remove_button.setAccessibleName(_("Remove {}").format(message["title"]))
        actions_layout.addWidget(edit_button)
        actions_layout.addWidget(remove_button)
        layout.addWidget(actions)

        edit_button.clicked.connect(
            lambda: self.edit_requested.emit(self.message_id)
        )
        remove_button.clicked.connect(
            lambda: self.remove_requested.emit(self.message_id)
        )
        self.active_switch.toggled.connect(
            lambda active: self.active_changed.emit(self.message_id, active)
        )


class QuickMessagesSettingsView(SettingsPage):
    def __init__(self, parent=None):
        super().__init__(
            _("Quick messages"),
            _("Create reusable messages and choose which accounts can use them."),
            parent,
        )
        self._setup_ui()
        self.add_stretch()

    def _setup_ui(self):
        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        self.search_edit = LineEdit(parent=header)
        self.search_edit.setPlaceholderText(_("Search messages…"))
        self.search_edit.setAccessibleName(_("Search quick messages"))
        self.add_button = Button("+ " + _("Add message"), Button.PRIMARY, header)
        self.add_button.setAccessibleName(_("Add quick message"))
        header_layout.addWidget(self.search_edit, 1)
        header_layout.addWidget(self.add_button)
        self.add_section(header)

        self.empty_label = Label(
            _("No quick messages configured."), "description", self
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.add_section(self.empty_label)

        self.cards_widget = QWidget(self)
        self.cards_layout = QVBoxLayout(self.cards_widget)
        self.cards_layout.setContentsMargins(0, 3, 0, 0)
        self.cards_layout.setSpacing(10)
        self.add_section(self.cards_widget)

    def clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_empty_state(self, visible, search_active=False):
        self.empty_label.setText(
            _("No messages match your search.")
            if search_active
            else _("No quick messages configured.")
        )
        self.empty_label.setVisible(visible)

    def add_card(self, card):
        self.cards_layout.addWidget(card)
