"""Tests for the passive stable-release notification."""

import json
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from datetime import date
from unittest.mock import Mock, patch

from PyQt6.QtCore import QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtTest import QTest

from qt_test_case import QtTestCase
from tools.memory.stub_webview import StubWebView
from zapzap.app.main_window_controller import MainWindowController
from zapzap.core import update_checker as update_module
from zapzap.core.config.settings.updates import UpdateSettings
from zapzap.core.config.settings_manager import SettingsManager
from zapzap.core.update_checker import (
    ApplicationUpdater,
    MANUAL_UPDATE_PACKAGING,
    ReleaseAsset,
    StableRelease,
    UpdateChecker,
    UpdateInfo,
    UpdatePolicy,
    UpdateState,
    current_installed_version,
    current_update_asset,
    is_newer_version,
    parse_release_feed,
    parse_stable_release,
)
from zapzap.features.settings.pages.about.controller import (
    AboutSettingsController,
)


class VersionComparisonTests(unittest.TestCase):
    def test_structured_version_comparison(self):
        cases = (
            ("7.4", "7.4", False),
            ("7.4", "7.4.1", True),
            ("7.4.9", "7.4.10", True),
            ("7.9", "7.10", True),
            ("8.0", "7.10", False),
            ("7.4", "7.4.0", False),
            ("invalid", "7.5", False),
            ("7.4", "7.5-rc1", False),
            ("7.4", "7.5-rc.1", True),
            ("7.5-rc.1", "7.5-rc.2", True),
            ("7.5-rc.2", "7.5-rc.1", False),
            ("7.5-rc.2", "7.5", True),
            ("7.5", "7.5-rc.3", False),
        )
        for current, latest, expected in cases:
            with self.subTest(current=current, latest=latest):
                self.assertEqual(is_newer_version(current, latest), expected)


class UpdatePolicyTests(unittest.TestCase):
    def test_only_real_official_manual_packages_are_checked(self):
        expected = {
            "DEB",
            "AppImage",
            "macOS",
            "Windows x86_64 (exe)",
            "Windows arm64 (exe)",
        }
        self.assertEqual(MANUAL_UPDATE_PACKAGING, expected)

        for packaging in expected:
            with self.subTest(packaging=packaging):
                self.assertTrue(
                    UpdatePolicy.should_check(
                        "Official",
                        "GitHub Actions",
                        "matheusgodoy8/zapzap",
                        packaging,
                    )
                )

    def test_managed_or_untrusted_builds_are_skipped(self):
        managed = (
            "Flatpak",
            "Snap",
            "RPM",
            "Copr",
            "Python Package (whl)",
        )
        for packaging in managed:
            with self.subTest(packaging=packaging):
                self.assertFalse(
                    UpdatePolicy.should_check(
                        "Official",
                        "GitHub Actions",
                        "matheusgodoy8/zapzap",
                        packaging,
                    )
                )

        for channel in ("Community", "Unknown", "Custom"):
            with self.subTest(channel=channel):
                self.assertFalse(
                    UpdatePolicy.should_check(
                        channel,
                        "GitHub Actions",
                        "matheusgodoy8/zapzap",
                        "DEB",
                    )
                )
        self.assertFalse(
            UpdatePolicy.should_check(
                "Official", "Other", "matheusgodoy8/zapzap", "DEB"
            )
        )
        self.assertFalse(
            UpdatePolicy.should_check(
                "Official", "GitHub Actions", "fork/zapzap", "DEB"
            )
        )


class ReleaseResponseTests(unittest.TestCase):
    @staticmethod
    def _payload(**overrides):
        release = {
            "tag_name": "v7.5",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-08-07T12:30:00Z",
            "html_url": "https://github.com/matheusgodoy8/zapzap/releases/tag/v7.5",
        }
        release.update(overrides)
        return json.dumps(release).encode()

    def test_valid_stable_release_is_extracted(self):
        self.assertEqual(
            parse_stable_release(self._payload()),
            StableRelease(
                "7.5",
                date(2026, 8, 7),
                "https://github.com/matheusgodoy8/zapzap/releases/tag/v7.5",
            ),
        )

    def test_optional_metadata_is_ignored_when_invalid_or_untrusted(self):
        release = parse_stable_release(
            self._payload(
                published_at="not-a-date",
                html_url="https://example.com/matheusgodoy8/zapzap/releases/tag/v7.5",
            )
        )

        self.assertEqual(release, StableRelease("7.5"))

    def test_drafts_prereleases_and_invalid_responses_are_ignored(self):
        values = (
            self._payload(draft=True),
            self._payload(prerelease=True),
            self._payload(tag_name="7.5-rc1"),
            self._payload(tag_name=None),
            b"not-json",
            b"[]",
        )
        for payload in values:
            with self.subTest(payload=payload):
                self.assertIsNone(parse_stable_release(payload))

    def test_opted_in_feed_selects_newest_rc_and_rejects_continuous(self):
        releases = [
            {
                "tag_name": "continuous",
                "draft": False,
                "prerelease": True,
            },
            {
                "tag_name": "7.5-rc.2",
                "draft": False,
                "prerelease": True,
            },
            {
                "tag_name": "7.5-rc.1",
                "draft": False,
                "prerelease": True,
            },
            {
                "tag_name": "7.4.4",
                "draft": False,
                "prerelease": False,
            },
        ]

        release = parse_release_feed(
            json.dumps(releases).encode(), include_prereleases=True
        )

        self.assertEqual(release, StableRelease("7.5-rc.2", prerelease=True))
        self.assertIsNone(
            parse_release_feed(
                json.dumps(releases[:3]).encode(),
                include_prereleases=False,
            )
        )

    def test_rc_uses_numeric_base_version_in_artifact_name(self):
        asset = ReleaseAsset(
            "ZapZap-7.5-windows-x86_64.exe",
            "https://github.com/matheusgodoy8/zapzap/releases/download/"
            "7.5-rc.1/ZapZap-7.5-windows-x86_64.exe",
            10,
            "a" * 64,
        )
        release = StableRelease("7.5-rc.1", assets=(asset,), prerelease=True)

        self.assertEqual(
            current_update_asset(release, "Windows x86_64 (exe)", "AMD64"),
            asset,
        )

    def test_packaged_rc_tag_identifies_the_installed_candidate(self):
        with (
            patch.object(update_module, "__version__", "7.5"),
            patch.object(
                update_module.EnvironmentDetector,
                "RELEASE_TAG",
                "v7.5-rc.2",
            ),
        ):
            self.assertEqual(current_installed_version(), "7.5-rc.2")

    def test_only_official_assets_with_github_digest_are_accepted(self):
        digest = "a" * 64
        release = parse_stable_release(
            self._payload(
                assets=[
                    {
                        "name": "ZapZap-7.5-windows-x86_64.exe",
                        "browser_download_url": (
                            "https://github.com/matheusgodoy8/zapzap/releases/"
                            "download/v7.5/ZapZap-7.5-windows-x86_64.exe"
                        ),
                        "size": 123,
                        "digest": f"sha256:{digest}",
                    },
                    {
                        "name": "evil.exe",
                        "browser_download_url": "https://example.com/evil.exe",
                        "size": 1,
                        "digest": f"sha256:{digest}",
                    },
                ]
            )
        )

        self.assertEqual(
            release.assets,
            (
                ReleaseAsset(
                    "ZapZap-7.5-windows-x86_64.exe",
                    "https://github.com/matheusgodoy8/zapzap/releases/"
                    "download/v7.5/ZapZap-7.5-windows-x86_64.exe",
                    123,
                    digest,
                ),
            ),
        )

    def test_artifact_selection_matches_packaging_version_and_architecture(self):
        windows = ReleaseAsset(
            "ZapZap-7.5-windows-arm64.exe",
            "https://github.com/matheusgodoy8/zapzap/releases/download/v7.5/a.exe",
            10,
            "a" * 64,
        )
        appimage = ReleaseAsset(
            "ZapZap-7.5-linux-aarch64.AppImage",
            "https://github.com/matheusgodoy8/zapzap/releases/download/v7.5/a.AppImage",
            10,
            "b" * 64,
        )
        release = StableRelease("7.5", assets=(windows, appimage))

        self.assertEqual(
            current_update_asset(release, "Windows arm64 (exe)", "ARM64"),
            windows,
        )
        self.assertEqual(
            current_update_asset(release, "AppImage", "aarch64"),
            appimage,
        )
        self.assertIsNone(current_update_asset(release, "DEB", "x86_64"))


class FakeReply(QObject):
    finished = pyqtSignal()
    readyRead = pyqtSignal()
    downloadProgress = pyqtSignal(int, int)

    def __init__(self, payload=b"", error=QNetworkReply.NetworkError.NoError):
        super().__init__()
        self.payload = payload
        self.network_error = error
        self.deleted = False

    def error(self):
        return self.network_error

    def errorString(self):
        return "timeout"

    def attribute(self, attribute):
        if attribute == QNetworkRequest.Attribute.HttpStatusCodeAttribute:
            return 200
        return None

    def readAll(self):
        payload = self.payload
        self.payload = b""
        return payload

    def abort(self):
        pass

    def deleteLater(self):
        self.deleted = True


class FakeNetworkManager:
    def __init__(self, reply):
        self.reply = reply
        self.requests = []

    def get(self, request):
        self.requests.append(request)
        return self.reply


class UpdateCheckerTests(QtTestCase):
    @staticmethod
    def _payload(version):
        return json.dumps(
            {"tag_name": version, "draft": False, "prerelease": False}
        ).encode()

    def _checker(self, reply):
        state = UpdateState()
        manager = FakeNetworkManager(reply)
        settings = SimpleNamespace(prereleases=False)
        checker = UpdateChecker(
            state, network_manager=manager, settings=settings
        )
        self.addCleanup(checker.deleteLater)
        self.addCleanup(state.deleteLater)
        return checker, state, manager

    def test_prerelease_opt_in_uses_feed_and_accepts_release_candidates(self):
        reply = FakeReply(
            json.dumps(
                [
                    {
                        "tag_name": "7.5-rc.2",
                        "draft": False,
                        "prerelease": True,
                    },
                    {
                        "tag_name": "7.4.4",
                        "draft": False,
                        "prerelease": False,
                    },
                ]
            ).encode()
        )
        checker, state, manager = self._checker(reply)
        checker._settings.prereleases = True
        with (
            patch.object(
                UpdatePolicy, "should_check_current_environment", return_value=True
            ),
            patch.object(update_module, "__version__", "7.4.4"),
        ):
            self.assertTrue(checker.start_once())
            reply.finished.emit()

        self.assertEqual(
            state.info,
            UpdateInfo("7.4.4", "7.5-rc.2", True),
        )
        self.assertEqual(
            manager.requests[0].url().toString(),
            update_module.RELEASES_URL,
        )

    def test_valid_higher_release_updates_state_asynchronously(self):
        reply = FakeReply(self._payload("7.5"))
        checker, state, manager = self._checker(reply)
        with (
            patch.object(
                UpdatePolicy, "should_check_current_environment", return_value=True
            ),
            patch.object(update_module, "__version__", "7.4"),
        ):
            self.assertTrue(checker.start_once())
            self.assertIsNone(state.info)
            reply.finished.emit()

        self.assertEqual(state.info, UpdateInfo("7.4", "7.5", True))
        self.assertEqual(len(manager.requests), 1)
        self.assertEqual(
            manager.requests[0].url().toString(),
            update_module.LATEST_STABLE_RELEASE_URL,
        )
        self.assertTrue(reply.deleted)
        self.assertFalse(checker.start_once())

    def test_same_release_records_no_available_update(self):
        reply = FakeReply(self._payload("7.4"))
        checker, state, _manager = self._checker(reply)
        with (
            patch.object(
                UpdatePolicy, "should_check_current_environment", return_value=True
            ),
            patch.object(update_module, "__version__", "7.4"),
        ):
            checker.start_once()
            reply.finished.emit()
        self.assertEqual(state.info, UpdateInfo("7.4", "7.4", False))

    def test_development_version_does_not_offer_the_last_stable_release(self):
        reply = FakeReply(self._payload("7.4.2"))
        checker, state, _manager = self._checker(reply)
        with (
            patch.object(
                UpdatePolicy, "should_check_current_environment", return_value=True
            ),
            patch.object(update_module, "__version__", "7.4.3"),
        ):
            checker.start_once()
            reply.finished.emit()

        self.assertEqual(state.info, UpdateInfo("7.4.3", "7.4.2", False))

    def test_timeout_and_invalid_response_are_silent(self):
        replies = (
            FakeReply(error=QNetworkReply.NetworkError.TimeoutError),
            FakeReply(b"invalid"),
        )
        for reply in replies:
            with self.subTest(error=reply.network_error):
                checker, state, _manager = self._checker(reply)
                completed = Mock()
                checker.completed.connect(completed)
                with patch.object(
                    UpdatePolicy,
                    "should_check_current_environment",
                    return_value=True,
                ):
                    checker.start_once()
                    reply.finished.emit()
                self.assertIsNone(state.info)
                completed.assert_called_once_with(None)
                self.assertTrue(reply.deleted)

    def test_ineligible_environment_never_creates_a_request(self):
        checker, state, manager = self._checker(FakeReply())
        with patch.object(
            UpdatePolicy, "should_check_current_environment", return_value=False
        ):
            self.assertFalse(checker.start_once())
        self.assertEqual(manager.requests, [])
        self.assertIsNone(state.info)


class ApplicationUpdaterTests(QtTestCase):
    def _updater(self, payload, digest=None, size=None):
        reply = FakeReply(payload)
        manager = FakeNetworkManager(reply)
        updater = ApplicationUpdater(network_manager=manager)
        asset = ReleaseAsset(
            "ZapZap-7.5-windows-x86_64.exe",
            "https://github.com/matheusgodoy8/zapzap/releases/download/7.5/"
            "ZapZap-7.5-windows-x86_64.exe",
            len(payload) if size is None else size,
            digest or hashlib.sha256(payload).hexdigest(),
        )
        info = UpdateInfo("7.4", "7.5", True, asset=asset)
        self.addCleanup(updater.deleteLater)
        return updater, reply, info

    def test_verified_portable_executable_becomes_ready(self):
        updater, reply, info = self._updater(b"MZverified executable")

        self.assertTrue(updater.download(info))
        reply.readyRead.emit()
        reply.finished.emit()

        self.assertEqual(updater.status, ApplicationUpdater.READY)
        self.assertTrue(updater._download_path.exists())
        self.addCleanup(updater._download_path.unlink, missing_ok=True)

    def test_size_digest_and_executable_format_are_fail_closed(self):
        cases = (
            {"size": 1},
            {"size": 999},
            {"digest": "0" * 64},
            {},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                payload = b"not an executable"
                updater, reply, info = self._updater(payload, **overrides)
                updater.download(info)
                reply.finished.emit()
                self.assertEqual(updater.status, ApplicationUpdater.FAILED)


class UpdateUiTests(QtTestCase):
    def test_about_page_persists_opt_in_automatic_updates(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        previous_settings = SettingsManager._settings
        SettingsManager._settings = QSettings(
            str(Path(temporary.name) / "settings.ini"),
            QSettings.Format.IniFormat,
        )
        self.addCleanup(setattr, SettingsManager, "_settings", previous_settings)
        settings = UpdateSettings()
        settings.automatic = False
        settings.prereleases = False
        self.addCleanup(setattr, settings, "automatic", False)
        self.addCleanup(setattr, settings, "prereleases", False)
        with patch.object(
            update_module.ApplicationUpdater, "supported", return_value=True
        ), patch.object(
            update_module.UpdatePolicy,
            "should_check_current_environment",
            return_value=True,
        ):
            page = AboutSettingsController()
        self.addCleanup(page.deleteLater)

        self.assertFalse(page.updates_section.isHidden())
        self.assertFalse(page.automatic_updates.isChecked())
        self.assertFalse(page.prerelease_updates.isChecked())
        page.automatic_updates.setChecked(True)
        page.prerelease_updates.setChecked(True)

        self.assertTrue(UpdateSettings().automatic)
        self.assertTrue(UpdateSettings().prereleases)

    def test_rebuilt_window_restores_existing_session_state(self):
        state = UpdateState()
        checker = Mock()
        state.set_info(UpdateInfo("7.4", "7.5", True))
        window = MainWindowController(
            webview_factory=StubWebView,
            user_provider=lambda: [],
            update_state=state,
            update_checker=checker,
        )
        self.addCleanup(window.deleteLater)
        self.addCleanup(state.deleteLater)

        self.assertFalse(window.browser.btn_update_available.isHidden())
        self.assertEqual(window.browser.btn_update_available.toolTip(), "")

    def test_sidebar_icon_opens_details_and_download_action(self):
        opener = Mock(return_value=True)
        with patch(
            "zapzap.app.main_window_controller.open_external_url", opener
        ):
            window = MainWindowController(
                webview_factory=StubWebView,
                user_provider=lambda: [],
            )
            self.addCleanup(window.deleteLater)
            self.assertFalse(window.browser.btn_update_available.isVisible())

            window.update_state.set_info(
                UpdateInfo(
                    "7.4",
                    "7.5",
                    True,
                    date(2026, 8, 7),
                    "https://github.com/matheusgodoy8/zapzap/releases/tag/v7.5",
                )
            )
            button = window.browser.btn_update_available
            self.assertFalse(button.isHidden())
            self.assertEqual(button.text(), "")
            self.assertFalse(button.icon().isNull())
            self.assertEqual(button.maximumWidth(), 40)
            self.assertEqual(button.toolTip(), "")
            self.assertIn("7.5", button.accessibleName())

            button.click()
            popover = window.browser._update_popover
            self.assertFalse(popover.isHidden())
            self.assertIn("7.4", popover.current_version_label.text())
            self.assertIn("7.5", popover.latest_version_label.text())
            self.assertTrue(popover.release_date_label.text())
            self.assertTrue(popover.release_notes_button.isVisible())
            popover.download_button.click()

        opener.assert_called_once()
        self.assertEqual(
            opener.call_args.args[0],
            "https://rtosta.com/zapzap/#download",
        )

    def test_release_notes_action_opens_only_the_validated_release_url(self):
        release_url = "https://github.com/matheusgodoy8/zapzap/releases/tag/v7.5"
        opener = Mock(return_value=True)
        with patch(
            "zapzap.app.main_window_controller.open_external_url", opener
        ):
            window = MainWindowController(
                webview_factory=StubWebView,
                user_provider=lambda: [],
            )
            self.addCleanup(window.deleteLater)
            window.update_state.set_info(
                UpdateInfo("7.4", "7.5", True, date(2026, 8, 7), release_url)
            )
            window.browser.show_update_popover(focus_actions=True)
            window.browser._update_popover.release_notes_button.click()

        opener.assert_called_once()
        self.assertEqual(opener.call_args.args[0], release_url)

    def test_hover_transition_delay_and_escape_keep_popover_usable(self):
        window = MainWindowController(
            webview_factory=StubWebView,
            user_provider=lambda: [],
        )
        self.addCleanup(window.deleteLater)
        window.update_state.set_info(UpdateInfo("7.4", "7.5", True))
        button = window.browser.btn_update_available
        popover = window.browser._update_popover

        window_type = popover.windowFlags() & Qt.WindowType.WindowType_Mask
        self.assertEqual(window_type, Qt.WindowType.Tool)
        self.assertTrue(
            popover.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        )

        button.pointer_entered.emit()
        self.assertFalse(popover.isHidden())
        button.pointer_exited.emit()
        popover.pointer_entered.emit()
        QTest.qWait(300)
        self.assertFalse(popover.isHidden())

        QTest.keyClick(popover.download_button, Qt.Key.Key_Escape)
        self.assertTrue(popover.isHidden())

        button.pointer_entered.emit()
        self.assertFalse(popover.isHidden())
        QTest.mouseClick(window.browser.pages, Qt.MouseButton.LeftButton)
        self.assertTrue(popover.isHidden())

    def test_about_page_consumes_the_same_state(self):
        state = UpdateState()
        page = AboutSettingsController()
        self.addCleanup(state.deleteLater)
        self.addCleanup(page.deleteLater)
        page.bind_update_state(state)
        self.assertTrue(page.update_row.isHidden())

        state.set_info(UpdateInfo("7.4", "7.5", True))

        self.assertFalse(page.update_row.isHidden())
        self.assertIn("7.5", page.update_row.title_label.text())
        self.assertIn("7.5", page.update_row.accessibleName())

        with patch(
            "zapzap.features.settings.pages.about.controller.QDesktopServices.openUrl",
            return_value=True,
        ) as opener:
            page.update_row.click()

        self.assertEqual(
            opener.call_args.args[0].toString(),
            "https://rtosta.com/zapzap/#download",
        )


if __name__ == "__main__":
    unittest.main()
