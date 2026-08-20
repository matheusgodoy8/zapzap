from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, call, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from zapzap.features.tray.sys_tray_manager import SysTrayManager


class LinuxLauncherBadgeTest(unittest.TestCase):
    def test_unread_total_updates_and_clears_linux_launcher_badge(self):
        manager = object.__new__(SysTrayManager)
        manager._bound_window = Mock()
        app = Mock(spec=["setBadgeNumber", "setWindowIcon"])
        icon = object()

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager.IS_LINUX",
                True,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager.QApplication.instance",
                return_value=app,
            ),
            patch.object(
                manager,
                "_send_plasma_launcher_badge",
            ) as send_plasma_badge,
            patch(
                "zapzap.features.tray.sys_tray_manager."
                "TrayIcon.getTaskbarIcon",
                return_value=icon,
            ),
        ):
            manager._set_linux_launcher_badge(7)
            manager._set_linux_launcher_badge(0)

        self.assertEqual(
            app.setBadgeNumber.call_args_list,
            [call(7), call(0)],
        )
        self.assertEqual(
            send_plasma_badge.call_args_list,
            [call(7), call(0)],
        )
        self.assertEqual(
            app.setWindowIcon.call_args_list,
            [call(icon), call(icon)],
        )
        self.assertEqual(
            manager._bound_window.setWindowIcon.call_args_list,
            [call(icon), call(icon)],
        )

    def test_invalid_unread_total_clears_linux_launcher_badge(self):
        manager = object.__new__(SysTrayManager)
        app = Mock(spec=["setBadgeNumber", "setWindowIcon"])

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager.IS_LINUX",
                True,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager.QApplication.instance",
                return_value=app,
            ),
            patch.object(manager, "_send_plasma_launcher_badge"),
            patch(
                "zapzap.features.tray.sys_tray_manager."
                "TrayIcon.getTaskbarIcon",
            ),
        ):
            manager._set_linux_launcher_badge("invalid")

        app.setBadgeNumber.assert_called_once_with(0)

    def test_linux_without_qt_badge_api_uses_plasma_signal(self):
        manager = object.__new__(SysTrayManager)
        app = Mock(spec=["setWindowIcon"])

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager.IS_LINUX",
                True,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager.QApplication.instance",
                return_value=app,
            ),
            patch.object(
                manager,
                "_send_plasma_launcher_badge",
            ) as send_plasma_badge,
            patch(
                "zapzap.features.tray.sys_tray_manager."
                "TrayIcon.getTaskbarIcon",
                return_value=object(),
            ),
        ):
            manager._set_linux_launcher_badge(7)

        send_plasma_badge.assert_called_once_with(7)

    def test_plasma_signal_uses_installed_desktop_file_identity(self):
        manager = object.__new__(SysTrayManager)
        message = Mock()
        session_bus = Mock()

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager."
                "QDBusMessage.createSignal",
                return_value=message,
            ) as create_signal,
            patch(
                "zapzap.features.tray.sys_tray_manager."
                "QDBusConnection.sessionBus",
                return_value=session_bus,
            ),
        ):
            manager._send_plasma_launcher_badge(8)

        create_signal.assert_called_once_with(
            "/com/rtosta/zapzap/LauncherEntry",
            "com.canonical.Unity.LauncherEntry",
            "Update",
        )
        message.setArguments.assert_called_once_with([
            "application://com.rtosta.zapzap.desktop",
            {"count": 8, "count-visible": True},
        ])
        session_bus.send.assert_called_once_with(message)

    def test_plasma_signal_hides_zero_badge(self):
        manager = object.__new__(SysTrayManager)
        message = Mock()

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager."
                "QDBusMessage.createSignal",
                return_value=message,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager."
                "QDBusConnection.sessionBus",
            ),
        ):
            manager._send_plasma_launcher_badge(0)

        message.setArguments.assert_called_once_with([
            "application://com.rtosta.zapzap.desktop",
            {"count": 0, "count-visible": False},
        ])

    def test_non_linux_platform_does_not_request_application_badge(self):
        manager = object.__new__(SysTrayManager)

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager.IS_LINUX",
                False,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager.QApplication.instance",
            ) as application_instance,
        ):
            manager._set_linux_launcher_badge(7)

        application_instance.assert_not_called()


if __name__ == "__main__":
    unittest.main()
