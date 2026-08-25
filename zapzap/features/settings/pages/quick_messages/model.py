"""Model for persistent quick messages."""

from __future__ import annotations

from zapzap.core.config.settings.quick_messages import QuickMessagesSettings
from zapzap.features.accounts.domain.user import User


class QuickMessagesSettingsModel:
    def __init__(self, account_provider=None, settings=None) -> None:
        self._account_provider = account_provider or User.select
        self.settings = settings or QuickMessagesSettings()

    def accounts(self):
        return list(self._account_provider())

    def messages(self):
        return self.settings.messages

    def create(self, **values):
        return self.settings.create(**values)

    def update(self, message_id, **values):
        return self.settings.update(message_id, **values)

    def delete(self, message_id):
        return self.settings.delete(message_id)
