"""Regression tests for native Windows notification routing."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from qt_test_case import QtTestCase

from zapzap.assets.icons.tray_icon import TrayIcon
from zapzap.features.notifications import windows_notification_backend as module
from zapzap.features.notifications.windows_notification_backend import (
    WindowsNotificationBackend,
)


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self):
        for callback in tuple(self.callbacks):
            callback()


class _Notification:
    def __init__(self):
        self.closed = _Signal()
        self.show = MagicMock()
        self.click = MagicMock()
        self.close = MagicMock()


class _Toast:
    sequence = 0

    def __init__(self):
        type(self).sequence += 1
        self.tag = f"toast-{type(self).sequence}"
        self.text_fields = []
        self.audio = None
        self.images = []
        self.on_activated = None
        self.on_dismissed = None
        self.on_failed = None

    def AddImage(self, image):
        self.images.append(image)


class _Audio:
    def __init__(self, source=None, silent=False):
        self.source = source
        self.silent = silent


class _Toaster:
    def __init__(self):
        self.shown = []
        self.removed = []

    def show_toast(self, toast):
        self.shown.append(toast)

    def remove_toast(self, toast):
        self.removed.append(toast)


class WindowsNotificationBackendTests(QtTestCase):
    def setUp(self):
        _Toast.sequence = 0
        self.toaster = _Toaster()
        self.patches = (
            patch.object(module, "Toast", _Toast),
            patch.object(module, "ToastAudio", _Audio),
            patch.object(module, "ToastDisplayImage", MagicMock()),
        )
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.backend = WindowsNotificationBackend(toaster=self.toaster)

    @staticmethod
    def _page(account_id, icon="account-icon"):
        return SimpleNamespace(
            user=SimpleNamespace(id=account_id, icon=icon),
        )

    def _notify(self, page, notification, sound=True):
        with (
            patch.object(self.backend, "_add_icon"),
            patch.object(
                module.SettingsManager,
                "get",
                side_effect=lambda key, default=None: (
                    sound if key == "notification/sound" else default
                ),
            ),
        ):
            self.backend.notify(page, notification, "Title", "Body")
        return self.toaster.shown[-1]

    def test_two_toasts_keep_independent_account_and_web_context(self):
        first_page = self._page("personal")
        second_page = self._page("business")
        first_notification = _Notification()
        second_notification = _Notification()
        first_toast = self._notify(first_page, first_notification)
        second_toast = self._notify(second_page, second_notification)

        main = MagicMock()
        main.browser.activate_account.return_value = True
        app = MagicMock()
        app.getWindow.return_value = main

        with (
            patch.object(module.QApplication, "instance", return_value=app),
            patch.object(module, "activate_window") as activate_window,
        ):
            first_toast.on_activated(None)

        main.restore_window.assert_called_once_with()
        activate_window.assert_called_once_with(main)
        main.browser.activate_account.assert_called_once_with("personal")
        first_notification.click.assert_called_once_with()
        first_notification.close.assert_called_once_with()
        second_notification.click.assert_not_called()
        self.assertNotIn(first_toast.tag, self.backend._contexts)
        self.assertIn(second_toast.tag, self.backend._contexts)

    def test_account_must_activate_before_web_notification_click(self):
        events = []
        page = self._page("disabled")
        notification = _Notification()
        notification.click.side_effect = lambda: events.append("click")
        toast = self._notify(page, notification)
        main = MagicMock()
        main.browser.activate_account.side_effect = (
            lambda account_id: events.append(("account", account_id)) or False
        )
        app = MagicMock()
        app.getWindow.return_value = main

        with (
            patch.object(module.QApplication, "instance", return_value=app),
            patch.object(module, "activate_window"),
        ):
            toast.on_activated(None)

        self.assertEqual(events, [("account", "disabled")])
        notification.click.assert_not_called()

    def test_native_toast_is_silent_to_avoid_whatsapp_sound_duplication(self):
        first = self._notify(self._page("one"), _Notification(), sound=True)
        second = self._notify(self._page("two"), _Notification(), sound=False)

        self.assertTrue(first.audio.silent)
        self.assertTrue(second.audio.silent)

    def test_account_icon_is_rendered_to_local_png(self):
        page = self._page("personal", icon="persisted-photo")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(module.IconRenderer, "temp_dir", return_value=directory),
            patch.object(module.SettingsManager, "get", return_value=True),
            patch.object(
                module.UserIcon,
                "get_icon",
                return_value=TrayIcon.getIcon(),
            ) as get_icon,
        ):
            path = self.backend._account_icon_path(page)

            self.assertTrue(Path(path).is_file())
            get_icon.assert_called_once_with("persisted-photo")

    def test_disabled_photo_setting_uses_zapzap_logo(self):
        with (
            patch.object(module.SettingsManager, "get", return_value=False),
            patch.object(
                module.IconRenderer,
                "default_icon",
                return_value="zapzap.png",
            ) as default_icon,
        ):
            path = self.backend._account_icon_path(self._page("personal"))

        self.assertEqual(path, "zapzap.png")
        default_icon.assert_called_once_with()

    def test_close_all_withdraws_every_native_toast(self):
        first = self._notify(self._page("one"), _Notification())
        second = self._notify(self._page("two"), _Notification())

        self.backend.close_all()

        self.assertEqual(self.backend._contexts, {})
        self.assertEqual(self.toaster.removed, [first, second])


if __name__ == "__main__":
    unittest.main(verbosity=2)
