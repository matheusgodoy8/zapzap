"""Regression tests for local automatic Portuguese accent correction."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from zapzap.core.config.settings.accent_autocorrect import (
    AccentAutocorrectSettings,
)
from zapzap.core.config.settings_manager import SettingsManager
from zapzap.features.browser.shell.browser_controller import BrowserController
from zapzap.features.browser.web.accent_autocorrect import (
    DEFAULT_CORRECTIONS,
    build_configuration_script,
    build_initialization_script,
    load_accent_autocorrect_source,
)
from zapzap.features.browser.web.page_controller import PageController


class AccentAutocorrectSettingsTests(unittest.TestCase):

    def test_global_setting_is_enabled_by_default_and_uses_stable_key(self):
        settings = AccentAutocorrectSettings()

        with patch.object(
            SettingsManager,
            "get",
            side_effect=lambda _key, default: default,
        ) as read:
            self.assertTrue(settings.enabled)

        read.assert_called_once_with("system/accentAutocorrect", True)
        with patch.object(SettingsManager, "set") as save:
            settings.enabled = False
        save.assert_called_once_with("system/accentAutocorrect", False)

    def test_map_is_conservative_and_keeps_ambiguous_words_out(self):
        self.assertEqual(len(DEFAULT_CORRECTIONS), 20)
        self.assertEqual(DEFAULT_CORRECTIONS["voce"], "você")
        self.assertEqual(DEFAULT_CORRECTIONS["informacoes"], "informações")
        for ambiguous in ("esta", "pelo", "para", "por", "ate", "numero"):
            self.assertNotIn(ambiguous, DEFAULT_CORRECTIONS)

    def test_configuration_is_json_serialized(self):
        settings = Mock(enabled=False)
        script = build_configuration_script(settings)
        payload = script.removeprefix(
            "window.__zapzapAccentAutocorrect?.configure("
        ).removesuffix(");")

        config = json.loads(payload)
        self.assertFalse(config["enabled"])
        self.assertEqual(config["corrections"], DEFAULT_CORRECTIONS)


class AccentAutocorrectRuntimeTests(unittest.TestCase):
    HARNESS = r"""
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");

global.Node = { TEXT_NODE: 3 };
class FakeText {
    constructor(data, parent) {
        this.nodeType = Node.TEXT_NODE;
        this.data = data;
        this.parentElement = parent;
        this.parentNode = parent;
        this.lastChild = null;
        this.nodeName = "#text";
    }
}

class FakeElement {
    constructor(parent = null) {
        this.parentElement = parent;
        this.childNodes = [];
        this.nodeName = "DIV";
        if (parent) parent.childNodes.push(this);
    }
    matches(selector) {
        if (selector.includes(":focus")) return document.activeElement === this;
        return selector.includes("contenteditable") || selector === "[contenteditable=\"true\"]";
    }
    closest(selector) {
        let current = this;
        while (current) {
            if (current.matches(selector)) return current;
            current = current.parentElement;
        }
        return null;
    }
    contains(node) {
        return node === this || node?.parentElement === this;
    }
    focus() { document.activeElement = this; }
}

class FakeRange {
    setStart(node, offset) { this.startContainer = node; this.startOffset = offset; }
    setEnd(node, offset) { this.endContainer = node; this.endOffset = offset; }
    cloneRange() {
        const copy = new FakeRange();
        copy.setStart(this.startContainer, this.startOffset);
        copy.setEnd(this.endContainer, this.endOffset);
        return copy;
    }
}

class FakeSelection {
    constructor() { this.range = null; }
    get rangeCount() { return this.range ? 1 : 0; }
    get isCollapsed() {
        return this.range && this.range.startContainer === this.range.endContainer &&
            this.range.startOffset === this.range.endOffset;
    }
    get anchorNode() { return this.range?.endContainer || null; }
    get anchorOffset() { return this.range?.endOffset || 0; }
    getRangeAt() { return this.range; }
    removeAllRanges() { this.range = null; }
    addRange(range) { this.range = range; }
}

const selection = new FakeSelection();
global.Element = FakeElement;
global.HTMLElement = FakeElement;
global.document = {
    body: new FakeElement(),
    activeElement: null,
    listeners: new Map(),
    addEventListener(type, callback) { this.listeners.set(type, callback); },
    removeEventListener(type, callback) {
        if (this.listeners.get(type) === callback) this.listeners.delete(type);
    },
    createRange() { return new FakeRange(); },
    dispatch(type, event) { this.listeners.get(type)?.(event); },
};
global.window = { getSelection: () => selection };

eval(source);

const INSERT = { type: "CONTROLLED_TEXT_INSERTION_COMMAND" };
function editorWithText(value, caretOffset = value.length) {
    const element = new FakeElement(document.body);
    const text = new FakeText(value, element);
    element.childNodes.push(text);
    function internalRange(anchorOffset, focusOffset) {
        return {
            anchor: { key: "text", offset: anchorOffset },
            focus: { key: "text", offset: focusOffset },
            applyDOMRange(range) {
                this.anchor.offset = range.startOffset;
                this.focus.offset = range.endOffset;
            },
        };
    }
    let internalSelection = internalRange(caretOffset, caretOffset);
    element.__lexicalEditor = {
        _commands: new Map([[INSERT, []]]),
        _pendingEditorState: null,
        history: [],
        update(callback) {
            this._pendingEditorState = { _selection: internalSelection };
            callback();
            this._pendingEditorState = null;
        },
        dispatchCommand(command, replacement) {
            if (command !== INSERT) return false;
            const range = {
                startOffset: Math.min(
                    internalSelection.anchor.offset,
                    internalSelection.focus.offset
                ),
                endOffset: Math.max(
                    internalSelection.anchor.offset,
                    internalSelection.focus.offset
                ),
            };
            this.history.push(text.data);
            text.data = text.data.slice(0, range.startOffset) + replacement +
                text.data.slice(range.endOffset);
            const caret = new FakeRange();
            const offset = range.startOffset + replacement.length;
            caret.setStart(text, offset);
            caret.setEnd(text, offset);
            selection.removeAllRanges();
            selection.addRange(caret);
            internalSelection = internalRange(offset, offset);
            return true;
        },
        undo() {
            text.data = this.history.pop();
            const caret = new FakeRange();
            caret.setStart(text, text.data.length);
            caret.setEnd(text, text.data.length);
            selection.removeAllRanges();
            selection.addRange(caret);
        },
    };
    element.focus();
    const caret = new FakeRange();
    caret.setStart(text, caretOffset);
    caret.setEnd(text, caretOffset);
    selection.removeAllRanges();
    selection.addRange(caret);
    return { element, text };
}
function configure(enabled = true) {
    window.__zapzapAccentAutocorrect.configure({
        enabled,
        corrections: {
            voce: "você", voces: "vocês", nao: "não", tambem: "também",
            codigo: "código",
            informacoes: "informações",
        },
    });
}
function delimit(editor, key = " ") {
    document.dispatch("keydown", {
        target: editor.element, key, isComposing: false,
        ctrlKey: false, altKey: false, metaKey: false,
    });
}
function insertOriginalDelimiter(editor, key) {
    const offset = selection.anchorOffset;
    editor.text.data = editor.text.data.slice(0, offset) + key +
        editor.text.data.slice(offset);
    const caret = new FakeRange();
    caret.setStart(editor.text, offset + key.length);
    caret.setEnd(editor.text, offset + key.length);
    selection.removeAllRanges();
    selection.addRange(caret);
}
function assertEqual(actual, expected, label) {
    if (actual !== expected) throw new Error(`${label}: ${actual} !== ${expected}`);
}

configure();
const completedSpace = editorWithText("voce");
delimit(completedSpace);
insertOriginalDelimiter(completedSpace, " ");
assertEqual(completedSpace.text.data, "você ", "original space preserved");
assertEqual(selection.anchorOffset, 5, "cursor after original space");

for (const [sourceText, expected, key] of [
    ["voce", "você", " "],
    ["Voce", "Você", "."],
    ["VOCE", "VOCÊ", "Enter"],
    ["nao", "não", "?"],
    ["tambem", "também", ";"],
    ["codigo", "código", " "],
    ["informacoes", "informações", ","],
]) {
    const editor = editorWithText(sourceText);
    delimit(editor, key);
    assertEqual(editor.text.data, expected, `case ${sourceText}`);
    assertEqual(selection.anchorOffset, expected.length, `cursor ${sourceText}`);
}

const middle = editorWithText("voce depois", 4);
delimit(middle);
assertEqual(middle.text.data, "você depois", "middle of message");
assertEqual(selection.anchorOffset, 4, "middle cursor");

const richPrefix = editorWithText("😀 *Matheus:*\n\nBom dia, voce");
delimit(richPrefix);
assertEqual(
    richPrefix.text.data,
    "😀 *Matheus:*\n\nBom dia, você",
    "emoji markdown and signature prefix"
);

const undoable = editorWithText("voce");
delimit(undoable);
undoable.element.__lexicalEditor.undo();
assertEqual(undoable.text.data, "voce", "Lexical undo history");

for (const ignored of [
    "https://site.test/voce", "nome@voce", "pasta/voce", "voce_1",
    "VoCe", "você", "esta", "CODIGO-VOCE", "constructor",
]) {
    const editor = editorWithText(ignored);
    delimit(editor);
    assertEqual(editor.text.data, ignored, `ignored ${ignored}`);
}

const unsynchronized = editorWithText("voce");
unsynchronized.element.__lexicalEditor.update = undefined;
delimit(unsynchronized);
assertEqual(
    unsynchronized.text.data,
    "voce",
    "failed selection synchronization must not append replacement"
);

const disabled = editorWithText("voce");
configure(false);
delimit(disabled);
assertEqual(disabled.text.data, "voce", "disabled");

console.log("accent autocorrect JavaScript scenarios: OK");
"""

    def test_runtime_syntax_and_behavior_with_node(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            harness_path = Path(temp_dir) / "accent_autocorrect_test.js"
            harness_path.write_text(textwrap.dedent(self.HARNESS), encoding="utf-8")
            result = subprocess.run(
                [
                    node,
                    str(harness_path),
                    str(
                        Path(__file__).resolve().parents[1]
                        / "zapzap/features/browser/web/scripts/accent_autocorrect.js"
                    ),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("scenarios: OK", result.stdout)

    def test_runtime_uses_no_content_rewrite_or_background_observer(self):
        source = load_accent_autocorrect_source()

        self.assertIn("CONTROLLED_TEXT_INSERTION_COMMAND", source)
        self.assertIn("selection.applyDOMRange(wordRange)", source)
        self.assertIn("{discrete: true}", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("textContent", source)
        self.assertNotIn("execCommand", source)
        self.assertNotIn("MutationObserver", source)
        self.assertNotIn("setInterval", source)


class AccentAutocorrectIntegrationTests(unittest.TestCase):

    def test_initialization_contains_runtime_and_configuration(self):
        settings = Mock(enabled=True)
        script = build_initialization_script(settings)

        self.assertIn("CONTROLLED_TEXT_INSERTION_COMMAND", script)
        self.assertIn('"voce":"voc\\u00ea"', script)
        self.assertIn("__zapzapAccentAutocorrect?.configure", script)

    def test_page_controller_runs_and_reconfigures_runtime_directly(self):
        page = SimpleNamespace(runJavaScript=Mock())
        with (
            patch(
                "zapzap.features.browser.web.page_controller."
                "build_accent_autocorrect_initialization_script",
                return_value="accent-runtime",
            ),
            patch(
                "zapzap.features.browser.web.page_controller."
                "build_accent_autocorrect_configuration_script",
                return_value="accent-config",
            ),
        ):
            PageController.initialize_accent_autocorrect(page)
            PageController.apply_accent_autocorrect_settings(page)

        self.assertEqual(
            page.runJavaScript.call_args_list,
            [unittest.mock.call("accent-runtime"), unittest.mock.call("accent-config")],
        )

    def test_browser_refreshes_every_active_account(self):
        first = SimpleNamespace(page=Mock())
        second = SimpleNamespace(page=Mock())
        browser = SimpleNamespace(_active_runtimes=lambda: [first, second])

        BrowserController.apply_accent_autocorrect_settings_all_pages(browser)

        first.page.apply_accent_autocorrect_settings.assert_called_once_with()
        second.page.apply_accent_autocorrect_settings.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
