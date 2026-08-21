"""Regression tests for the native Windows taskbar unread badge."""

from pathlib import Path
import ctypes
from ctypes import wintypes
import sys
import unittest
from unittest.mock import Mock, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from qt_test_case import QtTestCase
from zapzap.assets.icons.tray_icon import TrayIcon
from zapzap.features.tray.windows_taskbar_badge import (
    _create_hicon,
    publish_windows_taskbar_badge,
)


class _Window:
    def __init__(self, handle=123):
        self._handle = handle

    def winId(self):
        return self._handle


class WindowsTaskbarBadgeTest(QtTestCase):
    def test_positive_count_publishes_owned_numeric_overlay(self):
        user32 = Mock()
        user32.DestroyIcon = Mock()

        with (
            patch(
                "zapzap.features.tray.windows_taskbar_badge.sys.platform",
                "win32",
            ),
            patch(
                "zapzap.features.tray.windows_taskbar_badge._create_hicon",
                return_value=456,
            ),
            patch(
                "zapzap.features.tray.windows_taskbar_badge."
                "_set_overlay_icon",
                return_value=True,
            ) as set_overlay_icon,
            patch(
                "zapzap.features.tray.windows_taskbar_badge.ctypes.WinDLL",
                return_value=user32,
            ),
        ):
            published = publish_windows_taskbar_badge(_Window(), 7)

        self.assertTrue(published)
        set_overlay_icon.assert_called_once_with(
            123,
            456,
            "Unread messages: 7",
        )
        user32.DestroyIcon.assert_called_once_with(456)

    def test_zero_count_clears_overlay_without_allocating_an_icon(self):
        with (
            patch(
                "zapzap.features.tray.windows_taskbar_badge.sys.platform",
                "win32",
            ),
            patch(
                "zapzap.features.tray.windows_taskbar_badge._create_hicon",
            ) as create_hicon,
            patch(
                "zapzap.features.tray.windows_taskbar_badge."
                "_set_overlay_icon",
                return_value=True,
            ) as set_overlay_icon,
        ):
            published = publish_windows_taskbar_badge(_Window(), 0)

        self.assertTrue(published)
        create_hicon.assert_not_called()
        set_overlay_icon.assert_called_once_with(123, 0, "")

    def test_invalid_window_or_count_fails_closed(self):
        with (
            patch(
                "zapzap.features.tray.windows_taskbar_badge.sys.platform",
                "win32",
            ),
            patch(
                "zapzap.features.tray.windows_taskbar_badge."
                "_set_overlay_icon",
            ) as set_overlay_icon,
        ):
            self.assertFalse(
                publish_windows_taskbar_badge(_Window(handle=0), 3)
            )
            self.assertFalse(
                publish_windows_taskbar_badge(_Window(), "invalid")
            )

        set_overlay_icon.assert_not_called()

    def test_native_failure_does_not_escape_into_the_application(self):
        with (
            patch(
                "zapzap.features.tray.windows_taskbar_badge.sys.platform",
                "win32",
            ),
            patch(
                "zapzap.features.tray.windows_taskbar_badge."
                "_set_overlay_icon",
                side_effect=OSError("simulated shell failure"),
            ),
        ):
            with self.assertLogs(
                "zapzap.features.tray.windows_taskbar_badge",
                level="WARNING",
            ):
                self.assertFalse(
                    publish_windows_taskbar_badge(_Window(), 0)
                )

    def test_overlay_asset_is_transparent_and_numeric(self):
        overlay = TrayIcon.getTaskbarOverlayIcon(12)
        image = overlay.pixmap(32, 32).toImage()

        self.assertFalse(overlay.isNull())
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertGreater(image.pixelColor(16, 16).alpha(), 0)

    @unittest.skipUnless(sys.platform == "win32", "requires native Windows")
    def test_qt_overlay_converts_to_an_owned_native_icon(self):
        image = TrayIcon.getTaskbarOverlayIcon(7).pixmap(16, 16).toImage()
        hicon = _create_hicon(image)

        self.assertTrue(hicon)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        self.assertTrue(user32.DestroyIcon(hicon))


if __name__ == "__main__":
    unittest.main()
