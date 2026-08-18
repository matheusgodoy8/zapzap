"""View for local attendant identification."""

from gettext import gettext as _

from zapzap.ui.components import (
    SettingsCard,
    SettingsPage,
    SettingsSection,
    SettingsSelectRow,
    SettingsSwitchRow,
    SettingsTextRow,
)


class AttendantSignatureSettingsView(SettingsPage):
    """Native settings view composed from shared ZapZap components."""

    def __init__(self, parent=None):
        super().__init__(
            _("Attendant identification"),
            _(
                "Automatically adds the attendant's name to messages sent "
                "from this account on this computer."
            ),
            parent,
        )
        self.setObjectName("AttendantSignatureSettingsView")
        self._setup_ui()
        self.add_stretch()

    def _setup_ui(self):
        account_card = SettingsCard(self)
        self.account_row = SettingsSelectRow(
            _("Account"),
            _("Choose which ZapZap account to configure."),
            [""],
        )
        self.account_combo = self.account_row.combo
        self.account_combo.setAccessibleName(self.account_row.title_label.text())
        self.account_combo.setAccessibleDescription(
            self.account_row.description_label.text()
        )
        account_card.add_row(self.account_row)
        self.add_section(account_card)

        section = SettingsSection(
            _("Attendant identification"),
            _(
                "These preferences are stored only for the local operating "
                "system user."
            ),
            self,
        )
        card = SettingsCard(section)

        self.enabled_row = SettingsSwitchRow(
            _("Identify attendant"),
            _("Turn attendant identification on or off."),
        )
        self.name_row = SettingsTextRow(
            _("Attendant name"),
            _("Name added on the first line of signed messages."),
        )
        self.name_row.line_edit.setMaxLength(120)
        self.name_row.line_edit.setPlaceholderText("Matheus Godoy")
        self.text_messages_row = SettingsSwitchRow(
            _("Identify text messages"),
            _("Add the attendant name to new text messages."),
        )
        self.media_captions_row = SettingsSwitchRow(
            _("Identify media captions"),
            _("Add the attendant name before captions for images and media."),
        )
        self.empty_media_row = SettingsSwitchRow(
            _("Identify media without a caption"),
            _("Use only the attendant name as the media caption."),
        )
        self.dependent_rows = (
            self.name_row,
            self.text_messages_row,
            self.media_captions_row,
            self.empty_media_row,
        )

        for row in (
            self.enabled_row,
            self.text_messages_row,
            self.media_captions_row,
            self.empty_media_row,
        ):
            row.checkbox.setAccessibleName(row.title_label.text())
            row.checkbox.setAccessibleDescription(
                row.description_label.text()
            )
        self.name_row.line_edit.setAccessibleName(
            self.name_row.title_label.text()
        )
        self.name_row.line_edit.setAccessibleDescription(
            self.name_row.description_label.text()
        )

        card.add_group(
            self.enabled_row,
            self.dependent_rows,
            child_dividers=True,
        )
        section.add_card(card)
        self.add_section(section)
