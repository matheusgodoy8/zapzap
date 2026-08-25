"""Regression tests for persistent account-scoped quick messages."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QSettings

from qt_test_case import QtTestCase
from zapzap.core.config.settings.quick_messages import (
    QUICK_MESSAGES_SETTING,
    QuickMessagesSettings,
)
from zapzap.core.config.settings_manager import SettingsManager
from zapzap.features.browser.web.quick_messages import (
    build_configuration_script,
    build_initialization_script,
    load_quick_messages_source,
)
from zapzap.features.browser.web.page_controller import PageController
from zapzap.features.browser.shell.browser_controller import BrowserController
from zapzap.features.settings.pages.quick_messages.controller import (
    QuickMessagesSettingsController,
)
from zapzap.features.settings.pages.quick_messages.view import (
    QuickMessageEditorDialog,
)


class QuickMessagesDomainTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        previous = SettingsManager._settings
        SettingsManager._settings = QSettings(
            str(Path(self.temp_dir.name) / "settings.ini"),
            QSettings.Format.IniFormat,
        )
        self.addCleanup(setattr, SettingsManager, "_settings", previous)
        self.settings = QuickMessagesSettings()

    def test_missing_and_corrupt_settings_are_an_empty_list(self):
        self.assertEqual(self.settings.messages, [])
        SettingsManager.set(QUICK_MESSAGES_SETTING[0], "not json")
        self.assertEqual(self.settings.messages, [])
        SettingsManager.set(QUICK_MESSAGES_SETTING[0], json.dumps({"items": []}))
        self.assertEqual(self.settings.messages, [])

    def test_crud_preserves_multiline_content_and_metadata(self):
        created = self.settings.create(
            title="Orçamento",
            content="Olá!\n\nProduto:\nValor:",
            accounts=["storage-whats"],
        )
        self.assertTrue(created["id"])
        self.assertEqual(created["content"], "Olá!\n\nProduto:\nValor:")
        self.assertTrue(created["active"])
        self.assertEqual(created["accounts"], ["storage-whats"])
        self.assertEqual(created["createdAt"], created["updatedAt"])
        self.assertEqual(created["order"], 0)

        updated = self.settings.update(
            created["id"], title="Novo orçamento", active=False
        )
        self.assertEqual(updated["title"], "Novo orçamento")
        self.assertFalse(updated["active"])
        self.assertEqual(updated["createdAt"], created["createdAt"])
        self.assertTrue(self.settings.delete(created["id"]))
        self.assertFalse(self.settings.delete(created["id"]))
        self.assertEqual(self.settings.messages, [])

    def test_account_filter_uses_stable_ids_and_empty_scope_means_all(self):
        shared = self.settings.create(title="Geral", content="Para todos")
        account_a = self.settings.create(
            title="Plantão", content="Somente A", accounts=["account-a"]
        )
        self.settings.create(
            title="Inativa", content="Oculta", active=False, accounts=["account-a"]
        )

        self.assertEqual(
            [item["id"] for item in self.settings.for_account("account-a")],
            [shared["id"], account_a["id"]],
        )
        self.assertEqual(
            [item["id"] for item in self.settings.for_account("account-b")],
            [shared["id"]],
        )

    def test_runtime_payload_excludes_inactive_and_other_accounts(self):
        self.settings.create(title='Diga "oi"', content="Olá\nMundo")
        self.settings.create(
            title="Outra", content="Não aparece", accounts=["account-b"]
        )
        script = build_configuration_script("account-a", self.settings)
        self.assertIn('Diga \\"oi\\"', script)
        self.assertIn("Ol\\u00e1\\nMundo", script)
        self.assertNotIn("Não aparece", script)


class QuickMessagesRuntimeTest(unittest.TestCase):
    def test_initialization_contains_runtime_and_safe_configuration(self):
        settings = Mock()
        settings.runtime_config.return_value = {
            "messages": [{"id": "1", "title": "Quote", "content": "Hello"}]
        }
        script = build_initialization_script("account-a", settings)
        self.assertIn("__zapzapQuickMessages", script)
        self.assertIn('"title":"Quote"', script)
        settings.runtime_config.assert_called_once_with("account-a")

    def test_runtime_is_idempotent_and_uses_lexical_controlled_insertion(self):
        source = load_quick_messages_source()
        self.assertIn('data-zapzap-quick-messages', source)
        self.assertIn("CONTROLLED_TEXT_INSERTION_COMMAND", source)
        self.assertIn("MutationObserver", source)
        self.assertIn('document.querySelector("#app")', source)
        self.assertIn("prepareComposer", source)
        self.assertIn("composerRowPlacement", source)
        self.assertIn("buttonPlacementIsValid", source)
        self.assertIn("parent.contains(composerElement)", source)
        self.assertIn(
            "placement.container.insertBefore(button, placement.after.nextSibling)",
            source,
        )
        self.assertIn(":scope > [${BUTTON_ATTRIBUTE}]", source)
        self.assertNotIn("anchor.parentElement.insertBefore", source)
        self.assertNotIn("setInterval", source)
        self.assertNotIn("execCommand", source)

    def test_runtime_has_valid_javascript_syntax(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is unavailable")
        result = subprocess.run(
            [
                node,
                "--check",
                str(
                    Path(__file__).resolve().parents[1]
                    / "zapzap/features/browser/web/scripts/quick_messages.js"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_page_controller_runs_account_runtime_directly(self):
        page = SimpleNamespace(user_id="account-a", runJavaScript=Mock())
        with patch(
            "zapzap.features.browser.web.page_controller."
            "build_quick_messages_initialization_script",
            return_value="quick-runtime",
        ) as build_script:
            PageController.initialize_quick_messages(page)
        build_script.assert_called_once_with("account-a")
        page.runJavaScript.assert_called_once_with("quick-runtime")

    def test_browser_refreshes_every_active_account(self):
        first = SimpleNamespace(page=Mock())
        second = SimpleNamespace(page=Mock())
        browser = SimpleNamespace(_active_runtimes=lambda: [first, second])
        BrowserController.apply_quick_messages_settings_all_pages(browser)
        first.page.apply_quick_messages_settings.assert_called_once_with()
        second.page.apply_quick_messages_settings.assert_called_once_with()


class QuickMessagesUiTest(QtTestCase):
    ACCOUNTS = (
        SimpleNamespace(id="account-a", name="Plantão"),
        SimpleNamespace(id="account-b", name="Comercial"),
    )

    def test_editor_preserves_multiline_content_and_account_scope(self):
        dialog = QuickMessageEditorDialog(
            self.ACCOUNTS,
            message={
                "title": "Documentos",
                "content": "Olá\n\nDocumento:\nData:",
                "active": False,
                "accounts": ["account-a"],
            },
        )
        values = dialog.values()
        self.assertEqual(values["content"], "Olá\n\nDocumento:\nData:")
        self.assertEqual(values["accounts"], ["account-a"])
        self.assertFalse(values["active"])
        self.assertTrue(dialog.account_checks["account-a"].isEnabled())
        dialog.close()

    def test_controller_searches_title_and_content_and_exposes_accessibility(self):
        messages = [
            {
                "id": "one",
                "title": "Orçamento",
                "content": "Produto e valor",
                "active": True,
                "accounts": [],
                "createdAt": "now",
                "updatedAt": "now",
                "order": 0,
            },
            {
                "id": "two",
                "title": "Confirmação",
                "content": "Pedido pronto",
                "active": True,
                "accounts": ["account-b"],
                "createdAt": "now",
                "updatedAt": "now",
                "order": 1,
            },
        ]
        fake_model = Mock()
        fake_model.accounts.return_value = list(self.ACCOUNTS)
        fake_model.messages.return_value = messages
        with patch(
            "zapzap.features.settings.pages.quick_messages.controller."
            "QuickMessagesSettingsModel",
            return_value=fake_model,
        ):
            page = QuickMessagesSettingsController()
        self.assertEqual(page.cards_layout.count(), 2)
        page.search_edit.setText("valor")
        self.assertEqual(page.cards_layout.count(), 1)
        self.assertEqual(page.add_button.accessibleName(), "Add quick message")
        page.close()


if __name__ == "__main__":
    unittest.main()
