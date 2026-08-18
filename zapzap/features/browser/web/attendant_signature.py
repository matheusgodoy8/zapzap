"""Build JavaScript payloads for the native attendant signature."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from zapzap.core.config.settings.attendant_signature import (
    AttendantSignatureSettings,
)


RUNTIME_NAME = "__zapzapAttendantSignature"
SCRIPT_PATH = Path(__file__).with_name("scripts") / "attendant_signature.js"


@lru_cache(maxsize=1)
def load_attendant_signature_source() -> str:
    """Load the packaged runtime once per process."""
    return SCRIPT_PATH.read_text(encoding="utf-8")


def build_configuration_script(
    account_id: str | int,
    settings: AttendantSignatureSettings | None = None,
    *,
    debug: bool = False,
) -> str:
    """Serialize local settings without interpolating raw user text."""
    domain = settings or AttendantSignatureSettings(account_id)
    payload = json.dumps(
        domain.runtime_config(debug=debug),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"window.{RUNTIME_NAME}?.configure({payload});"


def build_initialization_script(
    account_id: str | int,
    settings: AttendantSignatureSettings | None = None,
    *,
    debug: bool = False,
) -> str:
    """Install the runtime and immediately apply its local configuration."""
    return "\n".join(
        (
            load_attendant_signature_source(),
            build_configuration_script(
                account_id,
                settings,
                debug=debug,
            ),
        )
    )
