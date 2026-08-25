"""Build JavaScript payloads for the quick-messages runtime."""

from __future__ import annotations

from functools import lru_cache
from gettext import gettext as _
import json
from pathlib import Path

from zapzap.core.config.settings.quick_messages import QuickMessagesSettings


RUNTIME_NAME = "__zapzapQuickMessages"
SCRIPT_PATH = Path(__file__).with_name("scripts") / "quick_messages.js"


@lru_cache(maxsize=1)
def load_quick_messages_source() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def build_configuration_script(
    account_id: str | int,
    settings: QuickMessagesSettings | None = None,
) -> str:
    domain = settings or QuickMessagesSettings()
    config = domain.runtime_config(account_id)
    config["labels"] = {
        "button": _("Quick messages"),
        "title": _("Quick messages"),
        "search": _("Search messages…"),
        "empty": _("No quick messages configured."),
        "hint": _("Add messages in Settings > Quick messages."),
    }
    payload = json.dumps(config, ensure_ascii=True, separators=(",", ":"))
    return f"window.{RUNTIME_NAME}?.configure({payload});"


def build_initialization_script(
    account_id: str | int,
    settings: QuickMessagesSettings | None = None,
) -> str:
    return "\n".join(
        (
            load_quick_messages_source(),
            build_configuration_script(account_id, settings),
        )
    )
