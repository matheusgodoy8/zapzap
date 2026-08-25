from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from PyQt6.QtCore import QDir, QStandardPaths, QTemporaryDir, QUrl
from PyQt6.QtGui import QDesktopServices
from zapzap.core.config.settings_manager import SettingsManager
from zapzap.features.downloads.download_naming_service import DownloadNamingService
from PyQt6.QtWidgets import QFileDialog

from gettext import gettext as _


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest


class DownloadManager:
    SYSTEM_PLAYER_FILE_PATTERN = re.compile(
        r"^zapzap-open-video-(\d{8}-\d{6})\.(mp4|m4v|mov|ogv|webm)$",
        re.IGNORECASE,
    )
    WHATSAPP_BLOB_PREFIX = "blob:https://web.whatsapp.com/"
    DOWNLOAD_PATH = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DownloadLocation
    )

    _floating_cards = []
    _active_downloads = []
    _system_player_downloads = {}
    _opened_video_temp_dirs = []

    @staticmethod
    def set_path(new_path):
        path = (
            new_path
            if isinstance(new_path, str) and new_path.strip()
            else DownloadManager.DOWNLOAD_PATH
        )
        SettingsManager.set("system/download_path", path)

    @staticmethod
    def get_path():
        path = SettingsManager.get(
            "system/download_path",
            DownloadManager.DOWNLOAD_PATH
        )
        if not isinstance(path, str) or not path.strip():
            logger.warning(
                "Invalid stored download directory; replacing it with the default"
            )
            path = DownloadManager.DOWNLOAD_PATH
            DownloadManager.set_path(path)
        return path

    @staticmethod
    def restore_path():
        SettingsManager.set(
            "system/download_path",
            DownloadManager.DOWNLOAD_PATH
        )

    @staticmethod
    def on_downloadRequested(
        download: QWebEngineDownloadRequest,
        parent=None
    ):
        from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest
        from zapzap.features.downloads.ui.download_dialog import DownloadDialog

        if download.state() != QWebEngineDownloadRequest.DownloadState.DownloadRequested:
            return

        if DownloadManager._is_system_player_video_download(download):
            DownloadManager._download_for_system_player(download, parent)
            return

        if not DownloadManager._set_initial_download_parameters(download):
            return

        DownloadManager._active_downloads.append(download)

        dialog = DownloadDialog(download, parent)
        DownloadManager._floating_cards.append(dialog)

        try:
            dialog.exec()
        finally:
            DownloadManager._release_download(download, dialog)

    @staticmethod
    def _is_system_player_video_download(download) -> bool:
        file_name = download.downloadFileName() or download.suggestedFileName()
        mime_type = (download.mimeType() or "").split(";", 1)[0].lower()
        source_url = download.url().toString()
        return bool(
            DownloadManager.SYSTEM_PLAYER_FILE_PATTERN.fullmatch(file_name)
            and mime_type.startswith("video/")
            and source_url.startswith(DownloadManager.WHATSAPP_BLOB_PREFIX)
        )

    @staticmethod
    def _download_for_system_player(download, parent=None) -> None:
        match = DownloadManager.SYSTEM_PLAYER_FILE_PATTERN.fullmatch(
            download.downloadFileName() or download.suggestedFileName()
        )
        if match is None:
            download.cancel()
            return

        template = os.path.join(QDir.tempPath(), "zapzap-video-XXXXXX")
        temporary_directory = QTemporaryDir(template)
        if not temporary_directory.isValid():
            download.cancel()
            DownloadManager._show_system_player_error(parent)
            return

        file_name = f"WhatsApp-video-{match.group(1)}.{match.group(2).lower()}"
        target_path = os.path.join(temporary_directory.path(), file_name)

        def on_state_changed(state, requested_download=download):
            DownloadManager._finish_system_player_download(
                requested_download,
                state,
                parent,
            )

        try:
            download.setDownloadDirectory(temporary_directory.path())
            download.setDownloadFileName(file_name)
            download.stateChanged.connect(on_state_changed)
            DownloadManager._active_downloads.append(download)
            DownloadManager._system_player_downloads[download] = {
                "directory": temporary_directory,
                "path": target_path,
                "handler": on_state_changed,
            }
            download.accept()
        except Exception:
            logger.exception("Failed to prepare a video for the system player")
            DownloadManager._system_player_downloads.pop(download, None)
            if download in DownloadManager._active_downloads:
                DownloadManager._active_downloads.remove(download)
            try:
                download.cancel()
            except Exception:
                logger.exception("Failed to cancel the temporary video download")
            DownloadManager._show_system_player_error(parent)

    @staticmethod
    def _finish_system_player_download(download, state, parent=None) -> None:
        from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest

        terminal_states = {
            QWebEngineDownloadRequest.DownloadState.DownloadCompleted,
            QWebEngineDownloadRequest.DownloadState.DownloadCancelled,
            QWebEngineDownloadRequest.DownloadState.DownloadInterrupted,
        }
        if state not in terminal_states:
            return

        record = DownloadManager._system_player_downloads.pop(download, None)
        if record is None:
            return
        if download in DownloadManager._active_downloads:
            DownloadManager._active_downloads.remove(download)
        try:
            download.stateChanged.disconnect(record["handler"])
        except (RuntimeError, TypeError):
            pass

        if state != QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            return

        try:
            opened = QDesktopServices.openUrl(
                QUrl.fromLocalFile(record["path"])
            )
        except Exception:
            logger.exception("Failed to hand the video to the system player")
            opened = False
        if opened:
            DownloadManager._opened_video_temp_dirs.append(record["directory"])
        else:
            DownloadManager._show_system_player_error(parent)

    @staticmethod
    def _show_system_player_error(parent=None) -> None:
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.warning(
            parent,
            _("Unable to open video"),
            _(
                "ZapZap could not open this video in the system player. "
                "Use the WhatsApp download button and open the downloaded "
                "file manually."
            ),
        )

    @staticmethod
    def _release_download(download: QWebEngineDownloadRequest, dialog):
        if download in DownloadManager._active_downloads:
            DownloadManager._active_downloads.remove(download)

        if dialog in DownloadManager._floating_cards:
            DownloadManager._floating_cards.remove(dialog)

    @staticmethod
    def _normalize_download_file_name(download: QWebEngineDownloadRequest):
        file_name = DownloadNamingService.normalized_file_name(
            download.downloadFileName() or download.suggestedFileName(),
            download.mimeType(),
            download.url().toString()
        )

        if file_name != download.downloadFileName():
            download.setDownloadFileName(file_name)

    @staticmethod
    def _set_initial_download_parameters(download) -> bool:
        """Set the target safely, retrying with the default before cancelling."""
        configured_path = DownloadManager.get_path()
        try:
            download.setDownloadDirectory(configured_path)
            DownloadManager._normalize_download_file_name(download)
            return True
        except Exception:
            logger.exception(
                "Failed to apply the configured download target; retrying "
                "with the default directory"
            )

        try:
            download.setDownloadDirectory(DownloadManager.DOWNLOAD_PATH)
            DownloadManager._normalize_download_file_name(download)
            DownloadManager.restore_path()
            return True
        except Exception:
            logger.exception(
                "Failed to apply the default download target; cancelling "
                "the download"
            )

        try:
            download.cancel()
        except Exception:
            logger.exception("Failed to cancel a download with no valid target")
        return False

    @staticmethod
    def open_folder_dialog(parent):
        directory = DownloadManager.get_path()

        options = (
            QFileDialog.Option.DontUseNativeDialog
            if SettingsManager.get("system/DontUseNativeDialog", False)
            else QFileDialog.Option(0)
        )

        folder_path = QFileDialog.getExistingDirectory(
            parent=parent,
            caption=_("Select folder"),
            directory=directory,
            options=options
        )

        return folder_path or None
