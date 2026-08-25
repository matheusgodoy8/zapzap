"""Persistent quick-message templates shared by ZapZap accounts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from zapzap.core.config.settings.base import BaseSettings


QUICK_MESSAGES_SETTING = ("quick_messages/items", "[]")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _account_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        account_id = str(value).strip()
        if account_id and account_id not in result:
            result.append(account_id)
    return result


def normalize_quick_message(value: Any) -> dict[str, Any] | None:
    """Return one safe template or ``None`` for unusable persisted data."""
    if not isinstance(value, dict):
        return None
    title = str(value.get("title", "")).strip()
    content = str(value.get("content", "")).replace("\r\n", "\n").replace(
        "\r", "\n"
    )
    if not title or not content.strip():
        return None
    created_at = str(value.get("createdAt", "")).strip() or _now()
    updated_at = str(value.get("updatedAt", "")).strip() or created_at
    try:
        order = int(value.get("order", 0))
    except (TypeError, ValueError, OverflowError):
        order = 0
    return {
        "id": str(value.get("id", "")).strip() or uuid4().hex,
        "title": title,
        "content": content,
        "active": bool(value.get("active", True)),
        # An empty list deliberately means every account.
        "accounts": _account_ids(value.get("accounts", [])),
        "createdAt": created_at,
        "updatedAt": updated_at,
        "order": max(0, order),
    }


class QuickMessagesSettings(BaseSettings):
    """CRUD and account filtering for locally persisted quick messages."""

    @property
    def messages(self) -> list[dict[str, Any]]:
        raw = self._get(QUICK_MESSAGES_SETTING)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                return []
        if not isinstance(raw, list):
            return []
        return [
            normalized
            for item in raw
            if (normalized := normalize_quick_message(item)) is not None
        ]

    def _save(self, messages: list[dict[str, Any]]) -> None:
        self._set(
            QUICK_MESSAGES_SETTING,
            json.dumps(messages, ensure_ascii=False, separators=(",", ":")),
        )

    def create(
        self,
        *,
        title: str,
        content: str,
        active: bool = True,
        accounts: list[str | int] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        existing = self.messages
        message = normalize_quick_message(
            {
                "id": uuid4().hex,
                "title": title,
                "content": content,
                "active": active,
                "accounts": list(accounts or []),
                "createdAt": now,
                "updatedAt": now,
                "order": len(existing),
            }
        )
        if message is None:
            raise ValueError("title and content must not be empty")
        existing.append(message)
        self._save(existing)
        return deepcopy(message)

    def update(self, message_id: str, **changes: Any) -> dict[str, Any]:
        messages = self.messages
        for index, current in enumerate(messages):
            if current["id"] != str(message_id):
                continue
            candidate = {
                **current,
                **changes,
                "id": current["id"],
                "updatedAt": _now(),
            }
            normalized = normalize_quick_message(candidate)
            if normalized is None:
                raise ValueError("title and content must not be empty")
            messages[index] = normalized
            self._save(messages)
            return deepcopy(normalized)
        raise KeyError(message_id)

    def delete(self, message_id: str) -> bool:
        messages = self.messages
        remaining = [item for item in messages if item["id"] != str(message_id)]
        if len(remaining) == len(messages):
            return False
        self._save(remaining)
        return True

    def for_account(
        self,
        account_id: str | int,
        *,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        account_key = str(account_id)
        return [
            deepcopy(item)
            for item in self.messages
            if (not active_only or item["active"])
            and (not item["accounts"] or account_key in item["accounts"])
        ]

    def runtime_config(self, account_id: str | int) -> dict[str, Any]:
        """Return only fields required by the untrusted web-page runtime."""
        return {
            "messages": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "content": item["content"],
                }
                for item in self.for_account(account_id)
            ]
        }
