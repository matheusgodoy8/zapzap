from __future__ import annotations

from typing import TYPE_CHECKING

from pathlib import Path
from gettext import gettext as _
import logging

from PyQt6.QtWebEngineCore import QWebEngineNotification

from zapzap.core.config.settings_manager import SettingsManager
from zapzap.features.notifications.portal_notification_backend import (
    PortalNotificationBackend
)
from zapzap.features.notifications.freedesktop_notification_backend import (
    FreedesktopNotificationBackend
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from zapzap.features.browser.web.web_view import WebView


def is_flatpak() -> bool:
    return Path("/.flatpak-info").exists()


def account_label(page: WebView) -> str:
    """Return the user-facing account name used to identify notifications."""
    name = getattr(getattr(page, "user", None), "name", "")
    if isinstance(name, str) and name.strip():
        return name.strip()

    page_index = getattr(page, "page_index", None)
    if page_index is not None:
        return _("Account {}").format(page_index)
    return _("Account")


def notification_title(page: WebView, contact_name: str = "") -> str:
    """Combine the stable account label with the optional sender name."""
    account = account_label(page)
    contact = contact_name.strip() if isinstance(contact_name, str) else ""
    if contact and contact != account:
        return f"{account} · {contact}"
    return account


class NotificationService:
    """
    Fachada única para notificações.

    Decide o backend (Portal / Freedesktop / None)
    e delega completamente a ele.
    """

    _backend = None

    def __init__(self):
        if NotificationService._backend is None:
            NotificationService._backend = self._select_backend()

        self.backend = NotificationService._backend

    # ------------------------------------------------------------------
    # Backend selection
    # ------------------------------------------------------------------
    def _select_backend(self):
        from zapzap.core.platform import IS_WINDOWS, IS_MAC
        if IS_WINDOWS:
            from zapzap.features.notifications.windows_notification_backend import (
                WindowsNotificationBackend,
            )
            return WindowsNotificationBackend()

        if IS_MAC:
            from zapzap.features.notifications.macos_notification_backend import (
                MacosNotificationBackend,
            )
            return MacosNotificationBackend()

        if is_flatpak():
            return PortalNotificationBackend()

        backend = FreedesktopNotificationBackend()
        return backend if backend.available() else None

    @classmethod
    def shutdown(cls):
        """Withdraw active notifications before the application exits."""
        backend = cls._backend
        if backend is None:
            return

        close_all = getattr(backend, "close_all", None)
        if close_all is not None:
            close_all()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def notify(
        self,
        page: WebView,
        notification: QWebEngineNotification
    ):
        # =================================================
        # 1. Regras globais (app / usuário)
        # =================================================
        if not SettingsManager.get("notification/app", True):
            return

        if not SettingsManager.get(
            f"{page.user.id}/notification", True
        ):
            return

        if not self.backend:
            return

        # =================================================
        # 2. Conteúdo (decisão global)
        # =================================================
        contact_name = (
            notification.title()
            if SettingsManager.get("notification/show_name", True)
            else ""
        )
        title = notification_title(page, contact_name)

        message = (
            notification.message()
            if SettingsManager.get("notification/show_msg", True)
            else _("New message...")
        )

        # =================================================
        # 3. Delegação total ao backend
        # =================================================
        try:
            self.backend.notify(
                page=page,
                notification=notification,
                title=title,
                message=message,
            )
        except Exception:
            # Notification failures must never crash the app.
            logger.warning(
                "Notification backend failed; dropping notification",
                exc_info=True,
            )
