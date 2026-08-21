"""Native Windows taskbar overlay integration."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from gettext import gettext as _
import logging
import sys
from uuid import UUID

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage

from zapzap.assets.icons.tray_icon import TrayIcon


logger = logging.getLogger(__name__)

_CLSID_TASKBAR_LIST = "56fdf344-fd6d-11d0-958a-006097c9a090"
_IID_ITASKBAR_LIST3 = "ea1afb91-9e28-4b86-90e9-9e9f8a5eefaf"
_CLSCTX_INPROC_SERVER = 0x1
_COINIT_APARTMENTTHREADED = 0x2
_RPC_E_CHANGED_MODE = -2147417850
_SET_OVERLAY_ICON_INDEX = 18


class _Guid(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]

    @classmethod
    def from_string(cls, value):
        return cls.from_buffer_copy(UUID(value).bytes_le)


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _RgbQuad(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", ctypes.c_ubyte),
        ("rgbGreen", ctypes.c_ubyte),
        ("rgbRed", ctypes.c_ubyte),
        ("rgbReserved", ctypes.c_ubyte),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BitmapInfoHeader),
        ("bmiColors", _RgbQuad * 1),
    ]


class _IconInfo(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HANDLE),
        ("hbmColor", wintypes.HANDLE),
    ]


def _signed_hresult(value):
    return ctypes.c_int32(value).value


def _succeeded(value):
    return _signed_hresult(value) >= 0


def _create_hicon(image: QImage):
    """Convert a Qt ARGB image to an owned native HICON."""
    if sys.platform != "win32" or image.isNull():
        return 0

    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    width = image.width()
    height = image.height()
    bitmap_info = _BitmapInfo()
    bitmap_info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
    bitmap_info.bmiHeader.biWidth = width
    bitmap_info.bmiHeader.biHeight = -height
    bitmap_info.bmiHeader.biPlanes = 1
    bitmap_info.bmiHeader.biBitCount = 32
    bitmap_info.bmiHeader.biCompression = 0

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    bits = ctypes.c_void_p()

    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(_BitmapInfo),
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    gdi32.CreateDIBSection.restype = wintypes.HANDLE
    gdi32.CreateBitmap.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    user32.CreateIconIndirect.argtypes = [ctypes.POINTER(_IconInfo)]
    user32.CreateIconIndirect.restype = wintypes.HICON

    color_bitmap = gdi32.CreateDIBSection(
        None,
        ctypes.byref(bitmap_info),
        0,
        ctypes.byref(bits),
        None,
        0,
    )
    if not color_bitmap or not bits.value:
        return 0

    mask_bitmap = 0
    try:
        source = image.constBits().asstring(image.sizeInBytes())
        ctypes.memmove(bits, source, len(source))
        mask_bitmap = gdi32.CreateBitmap(width, height, 1, 1, None)
        if not mask_bitmap:
            return 0

        icon_info = _IconInfo(
            True,
            0,
            0,
            mask_bitmap,
            color_bitmap,
        )
        return user32.CreateIconIndirect(ctypes.byref(icon_info)) or 0
    finally:
        if mask_bitmap:
            gdi32.DeleteObject(mask_bitmap)
        gdi32.DeleteObject(color_bitmap)


def _set_overlay_icon(hwnd, hicon, description):
    """Call ITaskbarList3.SetOverlayIcon for one taskbar button."""
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_Guid),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_Guid),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long

    initialize_result = _signed_hresult(
        ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    )
    should_uninitialize = _succeeded(initialize_result)
    if not should_uninitialize and initialize_result != _RPC_E_CHANGED_MODE:
        return False

    interface = ctypes.c_void_p()
    clsid = _Guid.from_string(_CLSID_TASKBAR_LIST)
    interface_id = _Guid.from_string(_IID_ITASKBAR_LIST3)
    try:
        create_result = ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            _CLSCTX_INPROC_SERVER,
            ctypes.byref(interface_id),
            ctypes.byref(interface),
        )
        if not _succeeded(create_result) or not interface.value:
            return False

        call_type = ctypes.WINFUNCTYPE
        vtable = ctypes.cast(
            interface,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
        ).contents
        release = call_type(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
        initialize = call_type(ctypes.c_long, ctypes.c_void_p)(vtable[3])
        set_overlay = call_type(
            ctypes.c_long,
            ctypes.c_void_p,
            wintypes.HWND,
            wintypes.HICON,
            wintypes.LPCWSTR,
        )(vtable[_SET_OVERLAY_ICON_INDEX])

        try:
            taskbar_initialize_result = initialize(interface)
            if not _succeeded(taskbar_initialize_result):
                return False
            overlay_result = set_overlay(
                interface,
                hwnd,
                hicon,
                description,
            )
            return _succeeded(overlay_result)
        finally:
            release(interface)
    finally:
        if should_uninitialize:
            ole32.CoUninitialize()


def publish_windows_taskbar_badge(window, number_notifications):
    """Publish or clear the unread count on the native taskbar button."""
    if sys.platform != "win32" or window is None:
        return False

    try:
        count = max(0, min(int(number_notifications), 999))
        hwnd = int(window.winId())
    except (TypeError, ValueError, AttributeError):
        return False

    hicon = 0
    user32 = None
    try:
        if not hwnd:
            return False
        if count == 0:
            return _set_overlay_icon(hwnd, 0, "")

        overlay = TrayIcon.getTaskbarOverlayIcon(count)
        image = overlay.pixmap(QSize(16, 16)).toImage()
        hicon = _create_hicon(image)
        if not hicon:
            return False

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        description = _("Unread messages: {}").format(count)
        return _set_overlay_icon(hwnd, hicon, description)
    except Exception:
        logger.warning(
            "Could not update the Windows taskbar badge",
            exc_info=True,
        )
        return False
    finally:
        if user32 is not None and hicon:
            user32.DestroyIcon(hicon)
