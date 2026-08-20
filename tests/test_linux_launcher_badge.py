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
        app = Mock(spec=["setBadgeNumber"])

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager.IS_LINUX",
                True,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager.QApplication.instance",
                return_value=app,
            ),
        ):
            manager._set_linux_launcher_badge(7)
            manager._set_linux_launcher_badge(0)

        self.assertEqual(
            app.setBadgeNumber.call_args_list,
            [call(7), call(0)],
        )

    def test_invalid_unread_total_clears_linux_launcher_badge(self):
        manager = object.__new__(SysTrayManager)
        app = Mock(spec=["setBadgeNumber"])

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager.IS_LINUX",
                True,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager.QApplication.instance",
                return_value=app,
            ),
        ):
            manager._set_linux_launcher_badge("invalid")

        app.setBadgeNumber.assert_called_once_with(0)

    def test_linux_without_qt_badge_api_remains_compatible(self):
        manager = object.__new__(SysTrayManager)

        with (
            patch(
                "zapzap.features.tray.sys_tray_manager.IS_LINUX",
                True,
            ),
            patch(
                "zapzap.features.tray.sys_tray_manager.QApplication.instance",
                return_value=object(),
            ),
        ):
            manager._set_linux_launcher_badge(7)

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
