"""Build JavaScript payloads for local automatic accent correction."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from zapzap.core.config.settings.accent_autocorrect import (
    AccentAutocorrectSettings,
)


RUNTIME_NAME = "__zapzapAccentAutocorrect"
SCRIPT_PATH = Path(__file__).with_name("scripts") / "accent_autocorrect.js"

# Only unambiguous, frequently typed Portuguese forms belong here. In
# particular, keep valid unaccented words such as "esta", "pelo", "para" and
# "por" out of this map. The data is separate from the runtime so custom maps
# can be layered on later without changing its editor integration.
DEFAULT_CORRECTIONS = {
    "apos": "após",
    "atencao": "atenção",
    "codigo": "código",
    "codigos": "códigos",
    "confirmacao": "confirmação",
    "confirmacoes": "confirmações",
    "documentacao": "documentação",
    "documentacoes": "documentações",
    "informacao": "informação",
    "informacoes": "informações",
    "ja": "já",
    "nao": "não",
    "numeros": "números",
    "situacao": "situação",
    "situacoes": "situações",
    "solicitacao": "solicitação",
    "solicitacoes": "solicitações",
    "tambem": "também",
    "voce": "você",
    "voces": "vocês",
}


@lru_cache(maxsize=1)
def load_accent_autocorrect_source() -> str:
    """Load the packaged runtime once per process."""
    return SCRIPT_PATH.read_text(encoding="utf-8")


def build_configuration_script(
    settings: AccentAutocorrectSettings | None = None,
) -> str:
    """Serialize the global preference and conservative built-in map."""
    domain = settings or AccentAutocorrectSettings()
    payload = json.dumps(
        {
            "enabled": domain.enabled,
            "corrections": DEFAULT_CORRECTIONS,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"window.{RUNTIME_NAME}?.configure({payload});"


def build_initialization_script(
    settings: AccentAutocorrectSettings | None = None,
) -> str:
    """Install the runtime and immediately apply its local configuration."""
    return "\n".join(
        (
            load_accent_autocorrect_source(),
            build_configuration_script(settings),
        )
    )
