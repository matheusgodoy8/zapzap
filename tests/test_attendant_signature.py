"""Regression tests for native attendant identification."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from qt_test_case import QtTestCase
from zapzap.core.config.settings.attendant_signature import (
    AttendantSignatureSettings,
)
from zapzap.core.config.settings_manager import SettingsManager
from zapzap.features.browser.web.attendant_signature import (
    build_configuration_script,
    build_initialization_script,
    load_attendant_signature_source,
)
from zapzap.features.browser.web.page_controller import PageController
from zapzap.features.browser.shell.browser_controller import BrowserController
from zapzap.features.settings.pages.attendant_signature.controller import (
    AttendantSignatureSettingsController,
)


class AttendantSignatureSettingsTests(unittest.TestCase):

    @staticmethod
    def _key(account_id, field):
        return f"attendant_signature/accounts/{account_id}/{field}"

    def test_defaults_are_safe_and_local_feature_is_disabled(self):
        settings = AttendantSignatureSettings("account-a")

        with patch.object(
            SettingsManager,
            "get",
            side_effect=lambda _key, default: default,
        ):
            self.assertEqual(
                settings.runtime_config(),
                {
                    "enabled": False,
                    "attendantName": "",
                    "signTextMessages": True,
                    "signMediaCaptions": True,
                    "signEmptyMedia": False,
                    "debug": False,
                },
            )

    def test_unscoped_legacy_values_do_not_leak_into_an_account(self):
        settings = AttendantSignatureSettings("personal-account")
        values = {
            "attendant_signature/enabled": True,
            "attendant_signature/name": "Plantão Alfa",
        }

        with patch.object(
            SettingsManager,
            "get",
            side_effect=lambda key, default: values.get(key, default),
        ):
            self.assertFalse(settings.enabled)
            self.assertEqual(settings.attendant_name, "")

    def test_empty_name_disables_runtime_even_when_switch_is_enabled(self):
        settings = AttendantSignatureSettings("account-a")
        values = {
            self._key("account-a", "enabled"): True,
            self._key("account-a", "name"): "   ",
        }

        with patch.object(
            SettingsManager,
            "get",
            side_effect=lambda key, default: values.get(key, default),
        ):
            self.assertFalse(settings.runtime_config()["enabled"])

    def test_properties_use_the_documented_qsettings_keys(self):
        settings = AttendantSignatureSettings("storage-whats")

        with patch.object(SettingsManager, "set") as save:
            settings.enabled = True
            settings.attendant_name = "  Matheus Godoy  "
            settings.sign_text_messages = False
            settings.sign_media_captions = False
            settings.sign_empty_media = True

        self.assertEqual(
            save.call_args_list,
            [
                unittest.mock.call(
                    "attendant_signature/accounts/storage-whats/enabled",
                    True,
                ),
                unittest.mock.call(
                    "attendant_signature/accounts/storage-whats/name",
                    "Matheus Godoy",
                ),
                unittest.mock.call(
                    "attendant_signature/accounts/storage-whats/"
                    "sign_text_messages",
                    False,
                ),
                unittest.mock.call(
                    "attendant_signature/accounts/storage-whats/"
                    "sign_media_captions",
                    False,
                ),
                unittest.mock.call(
                    "attendant_signature/accounts/storage-whats/"
                    "sign_empty_media",
                    True,
                ),
            ],
        )

    def test_accounts_have_isolated_values_and_defaults(self):
        values = {}

        def get(key, default):
            return values.get(key, default)

        def set_value(key, value):
            values[key] = value

        account_a = AttendantSignatureSettings("account-a")
        account_b = AttendantSignatureSettings("account-b")
        with (
            patch.object(SettingsManager, "get", side_effect=get),
            patch.object(SettingsManager, "set", side_effect=set_value),
        ):
            account_a.enabled = True
            account_a.attendant_name = "Matheus Godoy - NTI"
            account_b.attendant_name = "Bruno M."

            self.assertTrue(account_a.enabled)
            self.assertEqual(
                account_a.attendant_name,
                "Matheus Godoy - NTI",
            )
            self.assertFalse(account_b.enabled)
            self.assertEqual(account_b.attendant_name, "Bruno M.")
            self.assertTrue(account_b.sign_text_messages)
            self.assertTrue(account_b.sign_media_captions)
            self.assertFalse(account_b.sign_empty_media)

    def test_configuration_uses_json_for_special_names(self):
        for name in ("João D'Ávila", 'José "Junior"', "André Gonçalves"):
            with self.subTest(name=name):
                config = {
                    "enabled": True,
                    "attendantName": name,
                    "signTextMessages": True,
                    "signMediaCaptions": True,
                    "signEmptyMedia": False,
                    "debug": False,
                }
                settings = Mock()
                settings.runtime_config.return_value = config

                script = build_configuration_script("account-a", settings)
                payload = script.removeprefix(
                    "window.__zapzapAttendantSignature?.configure("
                ).removesuffix(");")

                self.assertEqual(json.loads(payload), config)


class FakeAttendantSignatureModel:

    def __init__(self):
        self._accounts = (
            SimpleNamespace(id="account-a", name="Plantão Alfa"),
            SimpleNamespace(id="account-b", name="Matheus Pessoal"),
        )
        self._states = {
            "account-a": {
                "enabled": True,
                "attendant_name": "Matheus Godoy - NTI",
                "sign_text_messages": True,
                "sign_media_captions": True,
                "sign_empty_media": False,
            },
            "account-b": {
                "enabled": False,
                "attendant_name": "",
                "sign_text_messages": True,
                "sign_media_captions": True,
                "sign_empty_media": False,
            },
        }
        self.account_id = None

    def accounts(self):
        return self._accounts

    def select_account(self, account_id):
        self.account_id = account_id

    def _get(self, field):
        return self._states[self.account_id][field]

    def _set(self, field, value):
        self._states[self.account_id][field] = value

    @property
    def enabled(self):
        return self._get("enabled")

    @enabled.setter
    def enabled(self, value):
        self._set("enabled", value)

    @property
    def attendant_name(self):
        return self._get("attendant_name")

    @attendant_name.setter
    def attendant_name(self, value):
        self._set("attendant_name", value.strip())

    @property
    def sign_text_messages(self):
        return self._get("sign_text_messages")

    @sign_text_messages.setter
    def sign_text_messages(self, value):
        self._set("sign_text_messages", value)

    @property
    def sign_media_captions(self):
        return self._get("sign_media_captions")

    @sign_media_captions.setter
    def sign_media_captions(self, value):
        self._set("sign_media_captions", value)

    @property
    def sign_empty_media(self):
        return self._get("sign_empty_media")

    @sign_empty_media.setter
    def sign_empty_media(self, value):
        self._set("sign_empty_media", value)


class AttendantSignatureSettingsUiTests(QtTestCase):

    def _controller(self):
        model = FakeAttendantSignatureModel()
        browser = SimpleNamespace(
            current_webview=lambda: SimpleNamespace(
                user=SimpleNamespace(id="account-a")
            ),
            apply_attendant_signature_settings_for_user_id=Mock(),
        )
        previous_get_window = getattr(self.app, "getWindow", None)
        self.app.getWindow = Mock(
            return_value=SimpleNamespace(browser=browser)
        )
        if previous_get_window is None:
            self.addCleanup(delattr, self.app, "getWindow")
        else:
            self.addCleanup(
                setattr,
                self.app,
                "getWindow",
                previous_get_window,
            )
        with patch(
            "zapzap.features.settings.pages.attendant_signature.controller."
            "AttendantSignatureSettingsModel",
            return_value=model,
        ):
            page = AttendantSignatureSettingsController()
        self.addCleanup(page.deleteLater)
        return page, model, browser

    def test_page_uses_shared_rows_and_accessible_controls(self):
        page, _model, _browser = self._controller()

        self.assertEqual(page.title_label.text(), "Attendant identification")
        self.assertEqual(
            page.description_label.text(),
            "Automatically adds the attendant's name to messages sent from "
            "this account on this computer.",
        )
        self.assertEqual(page.account_row.title_label.text(), "Account")
        self.assertEqual(page.account_combo.count(), 2)
        self.assertEqual(page.account_combo.currentData(), "account-a")
        for row in (
            page.enabled_row,
            page.text_messages_row,
            page.media_captions_row,
            page.empty_media_row,
        ):
            self.assertEqual(
                row.checkbox.accessibleName(),
                row.title_label.text(),
            )
            self.assertTrue(row.checkbox.accessibleDescription())
        self.assertEqual(
            page.name_row.line_edit.accessibleName(),
            "Attendant name",
        )

    def test_controls_persist_and_apply_without_reload(self):
        page, model, browser = self._controller()

        page.text_messages_row.checkbox.setChecked(False)
        page.media_captions_row.checkbox.setChecked(False)
        page.enabled_row.checkbox.setChecked(False)

        self.assertFalse(model.sign_text_messages)
        self.assertFalse(model.sign_media_captions)
        self.assertFalse(model.enabled)
        self.assertFalse(page.name_row.isEnabled())
        self.assertEqual(
            browser.apply_attendant_signature_settings_for_user_id.call_args_list,
            [
                unittest.mock.call("account-a"),
                unittest.mock.call("account-a"),
                unittest.mock.call("account-a"),
            ],
        )

    def test_name_is_trimmed_and_applied_on_editing_finished(self):
        page, model, browser = self._controller()
        page.name_row.line_edit.setText("  João D'Ávila  ")

        page.name_row.line_edit.editingFinished.emit()

        self.assertEqual(model.attendant_name, "João D'Ávila")
        self.assertEqual(page.name_row.line_edit.text(), "João D'Ávila")
        browser.apply_attendant_signature_settings_for_user_id.assert_called_once_with(
            "account-a"
        )

    def test_empty_media_depends_on_media_caption_switch(self):
        page, _model, _browser = self._controller()

        page.media_captions_row.checkbox.setChecked(False)
        self.assertFalse(page.empty_media_row.isEnabled())

        page.media_captions_row.checkbox.setChecked(True)
        self.assertTrue(page.empty_media_row.isEnabled())

    def test_account_selector_loads_each_accounts_values(self):
        page, model, _browser = self._controller()

        self.assertEqual(page.name_row.line_edit.text(), "Matheus Godoy - NTI")
        self.assertTrue(page.enabled_row.checkbox.isChecked())

        page.account_combo.setCurrentIndex(1)

        self.assertEqual(model.account_id, "account-b")
        self.assertEqual(page.name_row.line_edit.text(), "")
        self.assertFalse(page.enabled_row.checkbox.isChecked())
        self.assertTrue(page.text_messages_row.checkbox.isChecked())

    def test_saving_account_a_does_not_modify_account_b(self):
        page, model, browser = self._controller()
        original_b = dict(model._states["account-b"])
        page.name_row.line_edit.setText("João D'Ávila")

        page.name_row.line_edit.editingFinished.emit()

        self.assertEqual(
            model._states["account-a"]["attendant_name"],
            "João D'Ávila",
        )
        self.assertEqual(model._states["account-b"], original_b)
        browser.apply_attendant_signature_settings_for_user_id.assert_called_once_with(
            "account-a"
        )


class AttendantSignatureJavaScriptTests(unittest.TestCase):

    HARNESS = r"""
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");

class FakeElement {
    constructor(attributes = {}, parentElement = null) {
        this.attributes = attributes;
        this.parentElement = parentElement;
        this.children = [];
        this.innerText = "";
        this.__lexicalEditor = null;
        if (parentElement) parentElement.children.push(this);
    }
    getAttribute(name) { return this.attributes[name] || null; }
    matches(selector) {
        if (selector === '[contenteditable="true"]') {
            return this.attributes.contenteditable === "true";
        }
        if (selector.includes('data-lexical-editor="true"')) {
            const lexical = this.attributes.contenteditable === "true" &&
                this.attributes["data-lexical-editor"] === "true";
            const normalRequired = selector.includes(
                "conversation-compose-box-input"
            );
            return lexical && (!normalRequired ||
                this.attributes["data-testid"] ===
                    "conversation-compose-box-input");
        }
        if (selector === '[role="dialog"]') {
            return this.attributes.role === "dialog";
        }
        if (selector.includes("button") || selector.includes('[role="button"]')) {
            return this.attributes.tag === "button" ||
                this.attributes.role === "button" ||
                Boolean(this.attributes["data-testid"]);
        }
        return false;
    }
    closest(selector) {
        let current = this;
        while (current) {
            if (current.matches(selector)) return current;
            current = current.parentElement;
        }
        return null;
    }
    descendants() {
        return this.children.flatMap((child) => [child, ...child.descendants()]);
    }
    querySelector(selector) {
        return this.descendants().find((element) => {
            const semantic = [
                element.getAttribute("data-testid") || "",
                element.getAttribute("aria-label") || "",
            ].join(" ").toLowerCase();
            return selector.includes("caption") &&
                (semantic.includes("caption") || semantic.includes("media") ||
                 semantic.includes("legenda"));
        }) || null;
    }
    querySelectorAll(selector) {
        return this.descendants().filter((element) => element.matches(selector));
    }
    focus() {}
}

class FakeDocument {
    constructor() {
        this.body = new FakeElement();
        this.listeners = new Map();
    }
    addEventListener(type, callback) { this.listeners.set(type, callback); }
    removeEventListener(type, callback) {
        if (this.listeners.get(type) === callback) this.listeners.delete(type);
    }
    dispatch(type, event) { this.listeners.get(type)?.(event); }
}

global.Element = FakeElement;
global.HTMLElement = FakeElement;
global.document = new FakeDocument();
global.window = {};
eval(source);

const INSERT = { type: "CONTROLLED_TEXT_INSERTION_COMMAND" };
const BREAK = { type: "INSERT_LINE_BREAK_COMMAND" };

function editorElement(testId, parent = document.body) {
    const element = new FakeElement({
        "data-testid": testId,
        contenteditable: "true",
        "data-lexical-editor": "true",
    }, parent);
    const editor = {
        _commands: new Map([[INSERT, []], [BREAK, []]]),
        calls: [],
        dispatchCommand(command, payload) {
            this.calls.push([command.type, payload]);
            if (command === INSERT) element.innerText += payload;
            if (command === BREAK) element.innerText += "\n";
        },
    };
    element.__lexicalEditor = editor;
    return { element, editor };
}

function configure(overrides = {}) {
    window.__zapzapAttendantSignature.configure({
        enabled: true,
        attendantName: "Matheus Godoy",
        signTextMessages: true,
        signMediaCaptions: true,
        signEmptyMedia: false,
        debug: false,
        ...overrides,
    });
}
function typeIn(element) {
    document.dispatch("keydown", {
        target: element, key: "B", isComposing: false,
        ctrlKey: false, altKey: false, metaKey: false, shiftKey: false,
    });
}
function assert(condition, label) {
    if (!condition) throw new Error(label);
}

const disabled = editorElement("conversation-compose-box-input");
configure({ enabled: false });
typeIn(disabled.element);
assert(disabled.element.innerText === "", "disabled configuration signed");

const emptyName = editorElement("conversation-compose-box-input");
configure({ attendantName: "" });
typeIn(emptyName.element);
assert(emptyName.element.innerText === "", "empty name signed");

const normal = editorElement("conversation-compose-box-input");
configure();
typeIn(normal.element);
assert(normal.element.innerText === "Matheus Godoy\n", "normal composer");
normal.element.innerText = "Matheus Godoy\nBom dia";
typeIn(normal.element);
assert(normal.element.innerText === "Matheus Godoy\nBom dia", "duplicate signature");

const mainBehindEdit = editorElement("conversation-compose-box-input");
const dialog = new FakeElement({ role: "dialog" }, document.body);
const edit = editorElement("edit-message-input", dialog);
edit.element.innerText = "Matheus Godoy\nBom dia";
typeIn(edit.element);
assert(edit.element.innerText === "Matheus Godoy\nBom dia", "edit duplicated");
assert(mainBehindEdit.element.innerText === "", "edit filled main composer");

const mediaDialog = new FakeElement({ role: "dialog" }, document.body);
const media = editorElement("media-caption-input", mediaDialog);
typeIn(media.element);
assert(media.element.innerText === "Matheus Godoy\n", "media caption");
assert(mainBehindEdit.element.innerText === "", "media filled main composer");

const emptyMediaDialog = new FakeElement({ role: "dialog" }, document.body);
const emptyMedia = editorElement("media-caption-input", emptyMediaDialog);
const send = new FakeElement(
    { tag: "button", "data-testid": "send" }, emptyMediaDialog
);
configure({ signEmptyMedia: false });
document.dispatch("pointerdown", { target: send });
assert(emptyMedia.element.innerText === "", "false created empty caption");

configure({ signEmptyMedia: true });
document.dispatch("pointerdown", { target: send });
assert(emptyMedia.element.innerText === "Matheus Godoy", "true empty caption");

for (const name of ["João D'Ávila", 'José "Junior"', "André Gonçalves"]) {
    const special = editorElement("conversation-compose-box-input");
    configure({ attendantName: name });
    typeIn(special.element);
    assert(special.element.innerText === `${name}\n`, `special name: ${name}`);
}

console.log("attendant signature JavaScript scenarios: OK");
"""

    def test_runtime_syntax_and_behavior_with_node(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            harness_path = Path(temp_dir) / "attendant_signature_test.js"
            harness_path.write_text(
                textwrap.dedent(self.HARNESS),
                encoding="utf-8",
            )
            result = subprocess.run(
                [node, str(harness_path), str(
                    Path(__file__).resolve().parents[1]
                    / "zapzap/features/browser/web/scripts/attendant_signature.js"
                )],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertIn("scenarios: OK", result.stdout)

    def test_runtime_has_no_global_composer_fallback(self):
        source = load_attendant_signature_source()

        self.assertNotIn("document.activeElement", source)
        self.assertNotIn("document.querySelector", source)
        self.assertIn("getOriginatingEditorElement(event.target)", source)
        self.assertIn("CONTROLLED_TEXT_INSERTION_COMMAND", source)


class AttendantSignatureIntegrationTests(unittest.TestCase):

    def test_initialization_contains_packaged_runtime_and_json_config(self):
        settings = Mock()
        settings.runtime_config.return_value = {
            "enabled": True,
            "attendantName": 'José "Junior"',
            "signTextMessages": True,
            "signMediaCaptions": True,
            "signEmptyMedia": False,
            "debug": False,
        }

        script = build_initialization_script("account-a", settings)

        self.assertIn("CONTROLLED_TEXT_INSERTION_COMMAND", script)
        self.assertIn('Jos\\u00e9 \\"Junior\\"', script)
        self.assertIn("__zapzapAttendantSignature?.configure", script)

    def test_page_controller_runs_runtime_directly(self):
        page = SimpleNamespace(
            user_id="account-a",
            runJavaScript=Mock(),
        )

        with patch(
            "zapzap.features.browser.web.page_controller."
            "build_initialization_script",
            return_value="native-runtime",
        ) as build_script:
            PageController.initialize_attendant_signature(page)

        build_script.assert_called_once_with("account-a", debug=False)
        page.runJavaScript.assert_called_once_with("native-runtime")

    def test_browser_updates_only_the_requested_webview(self):
        first = Mock()
        second = Mock()
        pages = {"account-a": first, "account-b": second}
        browser = SimpleNamespace(
            webview_for_user_id=lambda user_id: pages.get(user_id),
        )

        BrowserController.apply_attendant_signature_settings_for_user_id(
            browser,
            "account-a",
        )

        first.apply_attendant_signature_settings.assert_called_once_with()
        second.apply_attendant_signature_settings.assert_not_called()

    def test_two_page_controllers_build_isolated_payloads_on_reload(self):
        values = {
            "attendant_signature/accounts/account-a/enabled": True,
            "attendant_signature/accounts/account-a/name": "Plantão Alfa",
            "attendant_signature/accounts/account-b/enabled": False,
            "attendant_signature/accounts/account-b/name": "",
        }
        pages = (
            SimpleNamespace(user_id="account-a", runJavaScript=Mock()),
            SimpleNamespace(user_id="account-b", runJavaScript=Mock()),
        )

        with patch.object(
            SettingsManager,
            "get",
            side_effect=lambda key, default: values.get(key, default),
        ):
            for page in pages:
                PageController.initialize_attendant_signature(page)

        account_a_script = pages[0].runJavaScript.call_args.args[0]
        account_b_script = pages[1].runJavaScript.call_args.args[0]
        self.assertIn('"attendantName":"Plant\\u00e3o Alfa"', account_a_script)
        self.assertIn('"enabled":true', account_a_script)
        self.assertIn('"attendantName":""', account_b_script)
        self.assertIn('"enabled":false', account_b_script)
        self.assertNotIn("Plant\\u00e3o Alfa", account_b_script)


if __name__ == "__main__":
    unittest.main()
