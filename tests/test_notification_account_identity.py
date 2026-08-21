"""Regression tests for account identity in native notifications."""

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from zapzap.features.notifications.notification_service import (
    NotificationService,
    account_label,
)


class NotificationAccountIdentityTests(unittest.TestCase):
    @staticmethod
    def _page(name="Comercial", page_index=2):
        return SimpleNamespace(
            user=SimpleNamespace(id="account-2", name=name),
            page_index=page_index,
        )

    @staticmethod
    def _notification(title="Meu Amor", message="Oi, meu gato"):
        notification = Mock()
        notification.title.return_value = title
        notification.message.return_value = message
        return notification

    @staticmethod
    def _settings(show_name=True, show_message=True):
        values = {
            "notification/app": True,
            "account-2/notification": True,
            "notification/show_name": show_name,
            "notification/show_msg": show_message,
        }
        return lambda key, default=None: values.get(key, default)

    def _service(self):
        service = object.__new__(NotificationService)
        service.backend = Mock()
        return service

    def test_saved_account_name_precedes_contact_name(self):
        service = self._service()
        page = self._page()
        notification = self._notification()

        with patch(
            "zapzap.features.notifications.notification_service."
            "SettingsManager.get",
            side_effect=self._settings(),
        ):
            service.notify(page, notification)

        service.backend.notify.assert_called_once_with(
            page=page,
            notification=notification,
            title="Comercial · Meu Amor",
            message="Oi, meu gato",
        )

    def test_contact_privacy_keeps_only_account_identity(self):
        service = self._service()
        page = self._page(name="Pessoal")
        notification = self._notification()

        with patch(
            "zapzap.features.notifications.notification_service."
            "SettingsManager.get",
            side_effect=self._settings(
                show_name=False,
                show_message=False,
            ),
        ):
            service.notify(page, notification)

        service.backend.notify.assert_called_once_with(
            page=page,
            notification=notification,
            title="Pessoal",
            message="New message...",
        )
        notification.title.assert_not_called()
        notification.message.assert_not_called()

    def test_blank_account_name_uses_visible_account_position(self):
        self.assertEqual(
            account_label(self._page(name="  ", page_index=3)),
            "Account 3",
        )

    def test_repeated_account_and_contact_name_is_not_duplicated(self):
        service = self._service()
        page = self._page(name="Comercial")
        notification = self._notification(title="Comercial")

        with patch(
            "zapzap.features.notifications.notification_service."
            "SettingsManager.get",
            side_effect=self._settings(),
        ):
            service.notify(page, notification)

        self.assertEqual(
            service.backend.notify.call_args.kwargs["title"],
            "Comercial",
        )


if __name__ == "__main__":
    unittest.main()
