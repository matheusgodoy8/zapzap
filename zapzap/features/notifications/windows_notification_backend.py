"""Windows notifications with per-message activation context."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QSize, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtWebEngineCore import QWebEngineNotification

from zapzap import __appname__
from zapzap.assets.icons.tray_icon import TrayIcon
from zapzap.assets.icons.user_icon import UserIcon
from zapzap.core.config.settings_manager import SettingsManager
from zapzap.features.notifications.freedesktop_notification_backend import (
    IconRenderer,
)
from zapzap.features.notifications.window_activation import activate_window

try:
    from windows_toasts import (
        Toast,
        ToastAudio,
        ToastDisplayImage,
        WindowsToaster,
    )
except ImportError:  # Optional on non-Windows/source installations.
    Toast = None
    ToastAudio = None
    ToastDisplayImage = None
    WindowsToaster = None

if TYPE_CHECKING:
    from zapzap.features.browser.web.web_view import WebView


@dataclass
class _NotificationContext:
    page: WebView
    notification: QWebEngineNotification
    toast: object


class _ToastEvents(QObject):
    """Marshal WinRT callbacks back onto Qt's GUI thread."""

    activated = pyqtSignal(str)
    finished = pyqtSignal(str)


class WindowsNotificationBackend(QObject):
    """Deliver individual Windows toasts and restore their exact web context."""

    def __init__(self, toaster=None):
        super().__init__()
        self._toaster = toaster
        if self._toaster is None and WindowsToaster is not None:
            try:
                self._toaster = WindowsToaster(__appname__)
            except Exception as error:
                print("[Windows] Native toast initialization failed:", error)

        self._contexts: dict[str, _NotificationContext] = {}
        self._events = _ToastEvents()
        self._events.activated.connect(self._activate)
        self._events.finished.connect(self._finish)
        self._fallback_callback = None

    def available(self) -> bool:
        return True

    def notify(
        self,
        page: WebView,
        notification: QWebEngineNotification,
        title: str,
        message: str,
    ):
        if self._toaster is None or Toast is None:
            self._notify_with_qt(page, notification, title, message)
            return

        try:
            toast = Toast()
            toast.text_fields = [title, message]
            # WhatsApp Web already plays its own incoming-message sound.
            # Keep the Windows toast silent to avoid a second system alert.
            toast.audio = ToastAudio(silent=True)
            self._add_icon(toast, page)

            token = toast.tag
            toast.on_activated = (
                lambda _args, token=token:
                    self._events.activated.emit(token)
            )
            toast.on_dismissed = (
                lambda _args, token=token:
                    self._events.finished.emit(token)
            )
            toast.on_failed = (
                lambda _args, token=token:
                    self._events.finished.emit(token)
            )

            self._contexts[token] = _NotificationContext(
                page=page,
                notification=notification,
                toast=toast,
            )
            notification.closed.connect(
                lambda token=token: self._remove(token, withdraw=True)
            )
            self._toaster.show_toast(toast)
            notification.show()
        except Exception as error:
            if "token" in locals():
                self._contexts.pop(token, None)
            print("[Windows] Native toast failed, using Qt fallback:", error)
            self._notify_with_qt(page, notification, title, message)

    @staticmethod
    def _account_icon_path(page: WebView) -> str:
        """Render the persisted account image to a stable local PNG."""
        if not SettingsManager.get("notification/show_photo", True):
            return IconRenderer.default_icon()

        try:
            icon_data = getattr(page.user, "icon", "")
            digest = sha256(
                f"{page.user.id}\0{icon_data}".encode("utf-8")
            ).hexdigest()[:20]
            path = Path(IconRenderer.temp_dir()) / (
                f"windows-account-{digest}.png"
            )
            if path.is_file() and path.stat().st_size:
                return str(path)

            icon = UserIcon.get_icon(icon_data)
            pixmap = icon.pixmap(QSize(128, 128))
            if not pixmap.isNull() and pixmap.save(str(path), "PNG"):
                return str(path)
        except Exception as error:
            print("[Windows] Failed to render account icon:", error)

        return IconRenderer.default_icon()

    def _add_icon(self, toast, page: WebView):
        if ToastDisplayImage is None:
            return
        icon_path = self._account_icon_path(page)
        if icon_path:
            toast.AddImage(ToastDisplayImage.fromPath(icon_path))

    @pyqtSlot(str)
    def _activate(self, token: str):
        context = self._contexts.get(token)
        if context is None:
            return

        try:
            app = QApplication.instance()
            main = app.getWindow() if app is not None else None
            if main is None:
                return

            restore = getattr(main, "restore_window", None)
            if restore is not None:
                restore()
            activate_window(main)

            if main.browser.activate_account(context.page.user.id):
                context.notification.click()
        except Exception as error:
            print("[Windows] Notification activation failed:", error)
        finally:
            try:
                context.notification.close()
            except Exception:
                pass
            self._remove(token, withdraw=True)

    @pyqtSlot(str)
    def _finish(self, token: str):
        context = self._contexts.get(token)
        if context is None:
            return
        try:
            context.notification.close()
        except Exception:
            pass
        self._remove(token)

    def _remove(self, token: str, withdraw: bool = False):
        context = self._contexts.pop(token, None)
        if context is None or not withdraw or self._toaster is None:
            return
        try:
            self._toaster.remove_toast(context.toast)
        except Exception:
            pass

    def close_all(self):
        for token in tuple(self._contexts):
            context = self._contexts.get(token)
            if context is not None:
                try:
                    context.notification.close()
                except Exception:
                    pass
            self._remove(token, withdraw=True)

    def _notify_with_qt(
        self,
        page: WebView,
        notification: QWebEngineNotification,
        title: str,
        message: str,
    ):
        """Compatibility fallback for environments without the WinRT package."""
        from zapzap.features.tray.sys_tray_manager import SysTrayManager

        tray: QSystemTrayIcon = SysTrayManager.instance()._tray
        if self._fallback_callback is not None:
            try:
                tray.messageClicked.disconnect(self._fallback_callback)
            except TypeError:
                pass

        def on_message_clicked():
            app = QApplication.instance()
            main = app.getWindow() if app is not None else None
            if main is None:
                return
            restore = getattr(main, "restore_window", None)
            if restore is not None:
                restore()
            activate_window(main)
            if main.browser.activate_account(page.user.id):
                notification.click()

        self._fallback_callback = on_message_clicked
        tray.messageClicked.connect(on_message_clicked)

        icon = TrayIcon.getIcon()
        if SettingsManager.get("notification/show_photo", True):
            try:
                icon = UserIcon.get_icon(getattr(page.user, "icon", ""))
            except Exception:
                pass
        tray.showMessage(title, message, icon, 4000)
        notification.show()
