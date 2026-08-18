"""Persistent preferences for application updates."""

from zapzap.core.config.settings.base import BaseSettings


class UpdateSettings(BaseSettings):
    """Semantic access to the opt-in automatic updater."""

    _AUTOMATIC = ("updates/automatic", False)

    @property
    def automatic(self) -> bool:
        return self._get_bool(self._AUTOMATIC)

    @automatic.setter
    def automatic(self, value: bool) -> None:
        self._set_bool(self._AUTOMATIC, value)
