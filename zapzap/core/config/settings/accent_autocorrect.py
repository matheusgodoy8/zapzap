"""Settings for the local automatic accent correction runtime."""

from __future__ import annotations

from zapzap.core.config.settings.base import BaseSettings


class AccentAutocorrectSettings(BaseSettings):
    """Semantic access to the global automatic accent correction setting."""

    _ENABLED = ("system/accentAutocorrect", True)

    @property
    def enabled(self) -> bool:
        return self._get_bool(self._ENABLED)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._set_bool(self._ENABLED, value)
