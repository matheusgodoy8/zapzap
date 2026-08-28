"""Tests for muting the desktop alert sound for new messages."""

import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QMetaType, QVariant

import qt_test_case  # noqa: F401  puts the repository root on sys.path
from zapzap.features.notifications.freedesktop_notification_backend import (
    DBusNotification,
)
from zapzap.features.notifications.portal_notification_backend import (
    PortalNotificationBackend,
)
from zapzap.features.browser.web.web_view import WebView
from zapzap.features.accounts.card_user_controller import CardUserController


def _with_sound(enabled, module):
    """Patch SettingsManager.get so notification/sound reads as `enabled`."""
    return patch(
        f"zapzap.features.notifications.{module}.SettingsManager.get",
        side_effect=lambda key, default=None: (
            enabled if key == "notification/sound" else default
        ),
    )


class SuppressSoundHintTests(unittest.TestCase):
    """The freedesktop backend carries the preference as a hint."""

    @staticmethod
    def _notification():
        return DBusNotification("Title", "Body", "", 3000)

    def test_muting_sets_the_suppress_sound_hint(self):
        notification = self._notification()

        notification.set_suppress_sound(True)

        self.assertIs(notification.hints["suppress-sound"], True)

    def test_allowing_sound_leaves_the_hint_false(self):
        notification = self._notification()

        notification.set_suppress_sound(False)

        self.assertIs(notification.hints["suppress-sound"], False)

    def test_hint_is_absent_until_it_is_set(self):
        self.assertNotIn("suppress-sound", self._notification().hints)

    def test_urgency_keeps_the_freedesktop_byte_type(self):
        notification = self._notification()

        notification.set_urgency(1)

        urgency = notification.hints["urgency"]
        self.assertIsInstance(urgency, QVariant)
        self.assertEqual(urgency.typeId(), QMetaType.Type.UChar.value)

    def test_urgency_rejects_values_outside_the_dbus_byte_range(self):
        notification = self._notification()

        for urgency in (-1, 256):
            with self.subTest(urgency=urgency):
                with self.assertRaises(ValueError):
                    notification.set_urgency(urgency)


class PortalSoundFieldTests(unittest.TestCase):
    """The portal backend carries the preference as a payload field."""

    def test_muting_marks_the_notification_silent(self):
        with _with_sound(False, "portal_notification_backend"):
            fields = PortalNotificationBackend._extra_fields()

        self.assertEqual(fields["sound"], "silent")

    def test_allowing_sound_omits_the_field(self):
        with _with_sound(True, "portal_notification_backend"):
            fields = PortalNotificationBackend._extra_fields()

        self.assertNotIn("sound", fields)

    def test_the_other_extra_fields_are_kept_when_muting(self):
        with _with_sound(False, "portal_notification_backend"):
            fields = PortalNotificationBackend._extra_fields()

        self.assertEqual(fields["category"], "im.received")
        self.assertEqual(fields["display-hint"], ["show-as-new"])


class AccountDoNotDisturbAudioTests(unittest.TestCase):
    @staticmethod
    def _webview():
        return type("FakeWebView", (), {
            "user": type("FakeUser", (), {"id": "account-2"})(),
            "whatsapp_page": MagicMock(),
        })()

    def test_do_not_disturb_mutes_whatsapp_page_audio(self):
        webview = self._webview()
        with patch(
            "zapzap.features.browser.web.web_view.SettingsManager.get",
            return_value=False,
        ):
            WebView.apply_notification_audio_state(webview)

        webview.whatsapp_page.setAudioMuted.assert_called_once_with(True)

    def test_reenabling_notifications_restores_whatsapp_page_audio(self):
        webview = self._webview()
        with patch(
            "zapzap.features.browser.web.web_view.SettingsManager.get",
            return_value=True,
        ):
            WebView.apply_notification_audio_state(webview)

        webview.whatsapp_page.setAudioMuted.assert_called_once_with(False)

    def test_new_web_page_applies_persisted_audio_state_before_loading(self):
        webview = type("FakeWebView", (), {
            "profile": object(),
            "user": type("FakeUser", (), {"id": "account-2"})(),
            "whatsapp_page": None,
            "_on_render_crash": MagicMock(),
            "load_page": MagicMock(),
            "_inject_web_theme_controller": MagicMock(),
            "apply_notification_audio_state": MagicMock(),
        })()
        page = MagicMock()

        with patch(
            "zapzap.features.browser.web.web_view.PageController",
            return_value=page,
        ):
            WebView._setup_page(webview)

        webview.apply_notification_audio_state.assert_called_once_with()
        webview.load_page.assert_called_once_with()

    def test_account_toggle_applies_audio_state_immediately(self):
        user = type("FakeUser", (), {"id": "account-2"})()
        model = MagicMock()
        browser = MagicMock()

        with (
            patch(
                "zapzap.features.accounts.card_user_controller.CardUserModel",
                return_value=model,
            ),
            patch.object(
                CardUserController,
                "_get_browser",
                return_value=browser,
            ),
        ):
            CardUserController.set_user_notifications(user, False)

        self.assertFalse(model.notifications_enabled)
        browser.update_icons_page_button.assert_called_once_with(user)
        browser.apply_notification_audio_state.assert_called_once_with(
            "account-2"
        )


if __name__ == "__main__":
    unittest.main()
