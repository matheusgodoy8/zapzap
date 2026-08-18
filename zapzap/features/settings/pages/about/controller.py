"""Controller for the About settings page."""

from gettext import gettext as _

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication

from zapzap.features.alerts.alert_manager import AlertManager
from zapzap.core.config.settings.updates import UpdateSettings
from zapzap.core.update_checker import ApplicationUpdater, UpdatePolicy
from zapzap.features.settings.pages.about.model import AboutSettingsModel
from zapzap.features.settings.pages.about.view import AboutSettingsView


class AboutSettingsController(AboutSettingsView):
    """Coordinates About metadata, links, dialogs, and clipboard actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = AboutSettingsModel()
        self._copy_feedback_timer = QTimer(self)
        self._copy_feedback_timer.setSingleShot(True)
        self._copy_feedback_timer.timeout.connect(
            self._restore_copy_button_text
        )
        self._load_metadata()
        self._configure_signals()
        self._update_state = None
        self._update_checker = None
        self._application_updater = None
        self._update_settings = UpdateSettings()
        self.automatic_updates.setChecked(self._update_settings.automatic)
        self.set_update_capabilities(
            UpdatePolicy.should_check_current_environment(),
            ApplicationUpdater.supported(),
        )

    def _load_metadata(self):
        self.set_identity(self.model.app_name, self.model.version_text)
        self.set_technical_details(self.model.technical_details)

    def _configure_signals(self):
        links = self.model.project_links
        self.homepage_row.clicked.connect(
            lambda: self._open_project_link(links["website"])
        )
        self.update_row.clicked.connect(self._install_or_download_update)
        self.issue_row.clicked.connect(
            lambda: self._open_project_link(links["bug_report"])
        )
        self.donate_row.clicked.connect(
            self._open_donations
        )
        self.license_row.clicked.connect(self._show_license)
        self.credits_row.clicked.connect(self._show_credits)
        self.copy_system_info_button.clicked.connect(self._copy_system_information)
        self.automatic_updates.toggled.connect(self._set_automatic_updates)
        self.check_updates_button.clicked.connect(self._check_for_updates)

    def _copy_system_information(self):
        QApplication.clipboard().setText(self.model.system_information)
        self.show_copy_feedback()
        self._copy_feedback_timer.start(2000)

    def _restore_copy_button_text(self):
        self.copy_system_info_button.setText(_("Copy system information"))

    def _show_license(self):
        AlertManager.information(
            self,
            _("License"),
            _(
                "ZapZap is free software licensed under {license_id} "
                "(GPL-3.0-or-later)."
            ).format(license_id=self.model.license_name),
        )

    def _show_credits(self):
        AlertManager.information(
            self,
            _("Credits and contributors"),
            _(
                "Created and maintained by {author}. Thanks to everyone who "
                "contributes translations, code, testing, and feedback."
            ).format(author=self.model.author_name),
        )

    @staticmethod
    def _open_project_link(url):
        QDesktopServices.openUrl(QUrl(url))

    @staticmethod
    def _open_donations():
        window = QApplication.instance().getWindow()
        return window.open_donations()

    def bind_update_state(
        self, update_state, update_checker=None, application_updater=None
    ):
        """Consume the same session state as the main-window indicator."""
        if self._update_state is not None:
            try:
                self._update_state.changed.disconnect(self._on_update_info_changed)
            except (TypeError, RuntimeError):
                pass
        self._update_state = update_state
        self._update_checker = update_checker
        self._application_updater = application_updater
        if application_updater is not None:
            application_updater.changed.connect(self._on_updater_changed)
            self._on_updater_changed(application_updater.status)
        if update_state is None:
            self.set_update_available(None)
            return
        update_state.changed.connect(self._on_update_info_changed)
        self._on_update_info_changed(update_state.info)

    def _on_update_info_changed(self, info):
        latest = info.latest_version if info is not None and info.available else None
        self.set_update_available(
            latest,
            installable=bool(info is not None and info.asset is not None),
        )
        if info is not None and not info.available:
            self.set_update_status(_("ZapZap is up to date."))
        elif info is not None and info.available and info.asset is None:
            self.set_update_status(
                _("An update is available from the official download page.")
            )

    def _set_automatic_updates(self, enabled):
        self._update_settings.automatic = enabled
        info = self._update_state.info if self._update_state is not None else None
        if (
            enabled
            and info is not None
            and info.available
            and info.asset is not None
            and self._application_updater is not None
        ):
            self._application_updater.download(info)

    def _check_for_updates(self):
        if self._update_checker is None or not self._update_checker.check_now():
            self.set_update_status(_("Update checking is unavailable for this build."))
            return
        self.check_updates_button.setEnabled(False)
        self.set_update_status(_("Checking for updates…"))
        self._update_checker.completed.connect(self._on_manual_check_completed)

    def _on_manual_check_completed(self, info):
        self.check_updates_button.setEnabled(True)
        try:
            self._update_checker.completed.disconnect(
                self._on_manual_check_completed
            )
        except (TypeError, RuntimeError):
            pass
        if info is None:
            self.set_update_status(_("Could not check for updates."))
        elif not info.available:
            self.set_update_status(_("ZapZap is up to date."))

    def _on_updater_changed(self, status):
        messages = {
            ApplicationUpdater.DOWNLOADING: _("Downloading update…"),
            ApplicationUpdater.READY: _("Update downloaded and ready to install."),
            ApplicationUpdater.FAILED: _("The update could not be prepared."),
        }
        if status in messages:
            self.set_update_status(messages[status])

    def _install_or_download_update(self):
        updater = self._application_updater
        info = self._update_state.info if self._update_state is not None else None
        if updater is None or info is None or info.asset is None:
            self._open_project_link(self.model.project_links["download"])
            return
        if updater.status == ApplicationUpdater.READY:
            if AlertManager.question(
                self,
                _("Install update"),
                _("ZapZap will close, install the verified update, and restart. Continue?"),
            ):
                updater.install_and_restart()
            return
        updater.download(info)
