"""Non-blocking stable-release checks for official manual packages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Optional
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QApplication

from zapzap import __version__
from zapzap.core.environment.environment_detector import EnvironmentDetector


logger = logging.getLogger(__name__)

LATEST_STABLE_RELEASE_URL = (
    "https://api.github.com/repos/matheusgodoy8/zapzap/releases/latest"
)
OFFICIAL_REPOSITORY = "matheusgodoy8/zapzap"
OFFICIAL_PROVIDER = "GitHub Actions"
MANUAL_UPDATE_PACKAGING = frozenset(
    {
        "DEB",
        "macOS",
        "Windows x86_64 (exe)",
        "Windows arm64 (exe)",
        "AppImage",
    }
)
_VERSION_PATTERN = re.compile(r"^[vV]?(\d+(?:\.\d+)*)$")


@dataclass(frozen=True)
class StableRelease:
    version: str
    published_on: Optional[date] = None
    release_notes_url: str = ""
    assets: tuple["ReleaseAsset", ...] = ()


@dataclass(frozen=True)
class ReleaseAsset:
    """A validated downloadable artifact belonging to the official release."""

    name: str
    download_url: str
    size: int
    sha256: str


def parse_version(value: str) -> Optional[tuple[int, ...]]:
    """Parse a stable numeric version, normalizing insignificant zeroes."""

    match = _VERSION_PATTERN.fullmatch(str(value or "").strip())
    if match is None:
        return None
    parts = [int(part) for part in match.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer_version(current: str, latest: str) -> bool:
    """Return whether both versions are valid and ``latest`` is newer."""

    current_parts = parse_version(current)
    latest_parts = parse_version(latest)
    if current_parts is None or latest_parts is None:
        return False
    width = max(len(current_parts), len(latest_parts))
    return current_parts + (0,) * (width - len(current_parts)) < (
        latest_parts + (0,) * (width - len(latest_parts))
    )


def _parse_release_date(value) -> Optional[date]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _official_release_url(value) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value.strip())
    expected_prefix = "/matheusgodoy8/zapzap/releases/"
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname != "github.com"
        or not parsed.path.casefold().startswith(expected_prefix)
        or parsed.username
        or parsed.password
    ):
        return ""
    return value.strip()


def _official_asset_url(value) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value.strip())
    expected_prefix = "/matheusgodoy8/zapzap/releases/download/"
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname != "github.com"
        or not parsed.path.casefold().startswith(expected_prefix)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return value.strip()


def _parse_release_assets(value) -> tuple[ReleaseAsset, ...]:
    if not isinstance(value, list):
        return ()
    assets = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        url = _official_asset_url(item.get("browser_download_url"))
        size = item.get("size")
        digest = item.get("digest")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9._-]+", name)
            or not url
            or not isinstance(size, int)
            or size <= 0
            or size > 1024 * 1024 * 1024
            or not isinstance(digest, str)
            or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)
        ):
            continue
        assets.append(ReleaseAsset(name, url, size, digest[7:].casefold()))
    return tuple(assets)


def parse_stable_release(payload: bytes) -> Optional[StableRelease]:
    """Extract safe stable-release metadata from a GitHub response."""

    try:
        release = json.loads(bytes(payload).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(release, dict):
        return None
    if release.get("draft") is not False or release.get("prerelease") is not False:
        return None
    tag_name = release.get("tag_name")
    if not isinstance(tag_name, str) or parse_version(tag_name) is None:
        return None
    return StableRelease(
        version=tag_name.lstrip("vV"),
        published_on=_parse_release_date(release.get("published_at")),
        release_notes_url=_official_release_url(release.get("html_url")),
        assets=_parse_release_assets(release.get("assets")),
    )


class UpdatePolicy:
    """Conservative policy for official packages requiring manual downloads."""

    @staticmethod
    def should_check(
        channel: str,
        provider: str,
        repository: str,
        packaging: str,
    ) -> bool:
        return (
            channel == "Official"
            and provider == OFFICIAL_PROVIDER
            and str(repository).casefold() == OFFICIAL_REPOSITORY
            and packaging in MANUAL_UPDATE_PACKAGING
        )

    @classmethod
    def should_check_current_environment(cls) -> bool:
        return cls.should_check(
            EnvironmentDetector.CHANNEL,
            EnvironmentDetector.PROVIDER,
            EnvironmentDetector.BUILD_REPOSITORY,
            EnvironmentDetector.PACKAGING,
        )


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    available: bool
    published_on: Optional[date] = None
    release_notes_url: str = ""
    asset: Optional[ReleaseAsset] = None


def current_update_asset(
    release: StableRelease,
    packaging: Optional[str] = None,
    machine: Optional[str] = None,
) -> Optional[ReleaseAsset]:
    """Select only the artifact matching this official binary build."""

    packaging = packaging or EnvironmentDetector.PACKAGING
    machine = (machine or platform.machine()).casefold()
    architecture = "arm64" if machine in {"arm64", "aarch64"} else "x86_64"
    if packaging == "AppImage":
        architecture = "aarch64" if architecture == "arm64" else "x86_64"
        expected = f"ZapZap-{release.version}-linux-{architecture}.AppImage"
    elif packaging in {
        "Windows x86_64 (exe)",
        "Windows arm64 (exe)",
    }:
        expected = f"ZapZap-{release.version}-windows-{architecture}.exe"
    else:
        return None
    return next((asset for asset in release.assets if asset.name == expected), None)


class UpdateState(QObject):
    """Session-only update result shared by independent views."""

    changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info: Optional[UpdateInfo] = None

    @property
    def info(self) -> Optional[UpdateInfo]:
        return self._info

    def set_info(self, info: UpdateInfo) -> None:
        if info == self._info:
            return
        self._info = info
        self.changed.emit(info)


class UpdateChecker(QObject):
    """Perform at most one asynchronous release request for this instance."""

    completed = pyqtSignal(object)
    TIMEOUT_MS = 5000

    def __init__(self, state: UpdateState, parent=None, network_manager=None):
        super().__init__(parent)
        self._state = state
        self._network_manager = network_manager or QNetworkAccessManager(self)
        self._started = False
        self._reply = None

    def start_once(self) -> bool:
        if self._started:
            return False
        self._started = True

        return self._start_request()

    def check_now(self) -> bool:
        """Start an explicit check, including after the startup check."""
        if self._reply is not None:
            return False
        self._started = True
        return self._start_request()

    def _start_request(self) -> bool:

        if not UpdatePolicy.should_check_current_environment():
            logger.debug(
                "update check skipped: channel=%s packaging=%s",
                EnvironmentDetector.CHANNEL,
                EnvironmentDetector.PACKAGING,
            )
            return False

        request = QNetworkRequest(QUrl(LATEST_STABLE_RELEASE_URL))
        request.setTransferTimeout(self.TIMEOUT_MS)
        request.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader,
            f"ZapZap/{__version__}",
        )
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        self._reply = self._network_manager.get(request)
        self._reply.finished.connect(self._handle_reply)
        return True

    def _handle_reply(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return

        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                logger.debug("update check failed: %s", reply.errorString())
                self.completed.emit(None)
                return

            status = reply.attribute(
                QNetworkRequest.Attribute.HttpStatusCodeAttribute
            )
            if status != 200:
                logger.debug("update check failed: HTTP status %s", status)
                self.completed.emit(None)
                return

            release = parse_stable_release(bytes(reply.readAll()))
            if release is None:
                logger.debug("update check failed: invalid stable release response")
                self.completed.emit(None)
                return

            info = UpdateInfo(
                current_version=__version__,
                latest_version=release.version,
                available=is_newer_version(__version__, release.version),
                published_on=release.published_on,
                release_notes_url=release.release_notes_url,
                asset=current_update_asset(release),
            )
            logger.info(
                "update check: current=%s latest=%s available=%s",
                info.current_version,
                info.latest_version,
                info.available,
            )
            self._state.set_info(info)
            self.completed.emit(info)
        finally:
            reply.deleteLater()


class ApplicationUpdater(QObject):
    """Download, verify, and atomically activate an official portable build."""

    IDLE = "idle"
    DOWNLOADING = "downloading"
    READY = "ready"
    FAILED = "failed"

    changed = pyqtSignal(str)
    progress_changed = pyqtSignal(int)

    def __init__(self, parent=None, network_manager=None):
        super().__init__(parent)
        self._network_manager = network_manager or QNetworkAccessManager(self)
        self._reply = None
        self._info = None
        self._download_path = None
        self._download_file = None
        self._download_hash = None
        self._download_size = 0
        self.status = self.IDLE
        self.error = ""

    @staticmethod
    def supported() -> bool:
        return EnvironmentDetector.PACKAGING in {
            "AppImage",
            "Windows x86_64 (exe)",
            "Windows arm64 (exe)",
        }

    def download(self, info: UpdateInfo) -> bool:
        if (
            self.status == self.DOWNLOADING
            or info.asset is None
            or (
                self.status == self.READY
                and self._info == info
                and self._download_path is not None
                and self._download_path.exists()
            )
        ):
            return False
        self._info = info
        self.error = ""
        self.status = self.DOWNLOADING
        self.changed.emit(self.status)
        suffix = ".AppImage" if info.asset.name.endswith(".AppImage") else ".exe"
        try:
            descriptor, raw_path = tempfile.mkstemp(
                prefix="zapzap-update-", suffix=suffix
            )
        except OSError as error:
            self._fail(str(error))
            return False
        self._download_path = Path(raw_path)
        self._download_file = os.fdopen(descriptor, "wb")
        self._download_hash = hashlib.sha256()
        self._download_size = 0
        request = QNetworkRequest(QUrl(info.asset.download_url))
        request.setTransferTimeout(10 * 60 * 1000)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader,
            f"ZapZap/{__version__}",
        )
        self._reply = self._network_manager.get(request)
        self._reply.readyRead.connect(self._read_download_chunk)
        self._reply.downloadProgress.connect(self._on_progress)
        self._reply.finished.connect(self._handle_download)
        return True

    def _on_progress(self, received: int, total: int) -> None:
        if total > 0:
            self.progress_changed.emit(max(0, min(100, received * 100 // total)))

    def _fail(self, message: str) -> None:
        if self._download_file is not None:
            self._download_file.close()
            self._download_file = None
        if self._download_path is not None:
            try:
                self._download_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._download_path = None
        self.error = message
        self.status = self.FAILED
        self.changed.emit(self.status)

    def _read_download_chunk(self, reply=None) -> None:
        reply = reply or self._reply
        if reply is None or self._download_file is None:
            return
        chunk = bytes(reply.readAll())
        if not chunk:
            return
        asset = self._info.asset if self._info is not None else None
        if asset is None or self._download_size + len(chunk) > asset.size:
            self._fail("download exceeds the size in release metadata")
            reply.abort()
            return
        self._download_file.write(chunk)
        self._download_hash.update(chunk)
        self._download_size += len(chunk)

    def _handle_download(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None or self._info is None or self._info.asset is None:
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._fail(reply.errorString())
                return
            self._read_download_chunk(reply)
            if self.status == self.FAILED or self._download_file is None:
                return
            self._download_file.close()
            self._download_file = None
            asset = self._info.asset
            if self._download_size != asset.size:
                self._fail("download size does not match release metadata")
                return
            if self._download_hash.hexdigest() != asset.sha256:
                self._fail("download checksum does not match release metadata")
                return
            with self._download_path.open("rb") as downloaded:
                header = downloaded.read(4)
            if asset.name.endswith(".exe") and not header.startswith(b"MZ"):
                self._fail("download is not a Windows executable")
                return
            if asset.name.endswith(".AppImage") and not header.startswith(b"\x7fELF"):
                self._fail("download is not an AppImage executable")
                return
            if asset.name.endswith(".AppImage"):
                self._download_path.chmod(0o755)
            self.status = self.READY
            self.progress_changed.emit(100)
            self.changed.emit(self.status)
        except OSError as error:
            self._fail(str(error))
        finally:
            reply.deleteLater()

    def install_and_restart(self) -> bool:
        if self.status != self.READY or self._download_path is None:
            return False
        current = self._current_executable()
        if current is None:
            self._fail("current portable executable could not be located")
            return False
        try:
            if os.name == "nt":
                return self._schedule_windows_replacement(current)
            staged = current.with_name(f".{current.name}.update")
            shutil.copy2(self._download_path, staged)
            staged.chmod(0o755)
            os.replace(staged, current)
            try:
                self._download_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._download_path = None
            return bool(QApplication.instance().restartApplication())
        except OSError as error:
            self._fail(str(error))
            return False

    @staticmethod
    def _current_executable() -> Optional[Path]:
        if EnvironmentDetector.PACKAGING == "AppImage":
            value = os.environ.get("APPIMAGE", "")
            return Path(value).resolve() if value else None
        if EnvironmentDetector.PACKAGING.startswith("Windows "):
            return Path(sys.executable).resolve()
        return None

    def _schedule_windows_replacement(self, current: Path) -> bool:
        # PowerShell receives paths as positional arguments, avoiding command
        # interpolation of a user-controlled installation directory.
        descriptor, raw_script = tempfile.mkstemp(
            prefix="zapzap-apply-update-", suffix=".ps1"
        )
        script = Path(raw_script)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(
                "param($PidToWait,$Source,$Target)\n"
                "Wait-Process -Id $PidToWait -ErrorAction SilentlyContinue\n"
                "Move-Item -LiteralPath $Source -Destination $Target -Force\n"
                "Start-Process -FilePath $Target\n"
                "Remove-Item -LiteralPath $PSCommandPath -Force\n"
            )
        try:
            subprocess.Popen(
                [
                    "powershell.exe", "-NoProfile", "-NonInteractive",
                    "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
                    "-File", str(script), str(os.getpid()),
                    str(self._download_path), str(current),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            self._fail(str(error))
            return False
        QApplication.instance().quit()
        return True
