(() => {
    const RUNTIME_NAME = "__zapzapAccentAutocorrect";
    const LEXICAL_EDITABLE_SELECTOR =
        '[contenteditable="true"][data-lexical-editor="true"]';
    const DELIMITERS = new Set([
        " ",
        "Spacebar",
        "Enter",
        ".",
        ",",
        "!",
        "?",
        ";",
        ":",
    ]);

    try {
        window[RUNTIME_NAME]?.destroy?.();
    } catch (_error) {
        // A stale runtime must not prevent the replacement from loading.
    }

    let enabled = false;
    let corrections = Object.freeze({});
    let listenerInstalled = false;
    let isReplacing = false;

    function getLexicalEditor(element) {
        let current = element;
        while (current instanceof Element && current !== document.body) {
            if (current.__lexicalEditor) {
                return current.__lexicalEditor;
            }
            current = current.parentElement;
        }
        return null;
    }

    function getOriginatingEditorElement(target) {
        if (!(target instanceof Element)) {
            return null;
        }
        const editable = target.closest('[contenteditable="true"]');
        if (!(editable instanceof HTMLElement)) {
            return null;
        }
        return (
            editable.matches(LEXICAL_EDITABLE_SELECTOR) ||
            getLexicalEditor(editable)
        )
            ? editable
            : null;
    }

    function findCommand(editor, type) {
        try {
            return (
                [...editor._commands.keys()].find(
                    (command) => command?.type === type
                ) || null
            );
        } catch (_error) {
            return null;
        }
    }

    function caretTextPosition(element) {
        const selection = window.getSelection();
        if (
            !selection ||
            selection.rangeCount !== 1 ||
            !selection.isCollapsed ||
            !selection.anchorNode ||
            !element.contains(selection.anchorNode)
        ) {
            return null;
        }

        if (selection.anchorNode.nodeType === Node.TEXT_NODE) {
            return {
                node: selection.anchorNode,
                offset: selection.anchorOffset,
                selection,
            };
        }

        const container = selection.anchorNode;
        const child = container.childNodes[selection.anchorOffset - 1];
        if (!child || child.nodeName === "BR") {
            return null;
        }
        let node = child;
        while (node?.lastChild && node.nodeName !== "BR") {
            node = node.lastChild;
        }
        if (!node || node.nodeType !== Node.TEXT_NODE) {
            return null;
        }
        return {node, offset: node.data.length, selection};
    }

    function previousWord(element) {
        const caret = caretTextPosition(element);
        if (!caret) {
            return null;
        }
        const textBeforeCaret = caret.node.data.slice(0, caret.offset);
        const tokenMatch = textBeforeCaret.match(/(\S+)$/u);
        if (!tokenMatch) {
            return null;
        }
        const text = tokenMatch[1];

        // A complete whitespace-delimited token made exclusively from ASCII
        // letters is deliberate: URLs, e-mails, paths, numbers, identifiers,
        // emoji and already accented words never reach the correction map.
        if (!/^[A-Za-z]+$/.test(text)) {
            return null;
        }
        return {
            ...caret,
            text,
            startOffset: caret.offset - text.length,
        };
    }

    function preserveCase(source, replacement) {
        if (source === source.toLocaleLowerCase("pt-BR")) {
            return replacement;
        }
        if (source === source.toLocaleUpperCase("pt-BR")) {
            return replacement.toLocaleUpperCase("pt-BR");
        }
        const initialUpper =
            source[0] === source[0].toLocaleUpperCase("pt-BR") &&
            source.slice(1) === source.slice(1).toLocaleLowerCase("pt-BR");
        if (!initialUpper) {
            return null;
        }
        return (
            replacement[0].toLocaleUpperCase("pt-BR") + replacement.slice(1)
        );
    }

    function lexicalSelectionMatchesWord(selection, wordLength) {
        return Boolean(
            selection?.anchor &&
                selection?.focus &&
                selection.anchor.key === selection.focus.key &&
                Math.abs(selection.focus.offset - selection.anchor.offset) ===
                    wordLength
        );
    }

    function replaceThroughLexicalUpdate(
        editor,
        insertText,
        wordRange,
        originalRange,
        wordLength,
        replacement
    ) {
        if (typeof editor.update !== "function") {
            return false;
        }
        let handled = false;
        try {
            editor.update(
                () => {
                    // The pending state is the state CONTROLLED_TEXT_INSERTION_COMMAND
                    // reads while this synchronous Lexical update is active.
                    const selection = editor._pendingEditorState?._selection;
                    if (typeof selection?.applyDOMRange !== "function") {
                        return;
                    }
                    selection.applyDOMRange(wordRange);
                    if (!lexicalSelectionMatchesWord(selection, wordLength)) {
                        selection.applyDOMRange(originalRange);
                        return;
                    }
                    handled = Boolean(
                        editor.dispatchCommand(insertText, replacement)
                    );
                    if (!handled) {
                        selection.applyDOMRange(originalRange);
                    }
                },
                {discrete: true}
            );
        } catch (error) {
            console.error(
                "[ZapZap Accent Autocorrect] Lexical update failed",
                error
            );
            return false;
        }
        return handled;
    }

    function replacePreviousWord(element) {
        if (!enabled || isReplacing || !element.matches(":focus, :focus-within")) {
            return false;
        }
        const candidate = previousWord(element);
        if (!candidate) {
            return false;
        }
        const replacement = corrections[
            candidate.text.toLocaleLowerCase("pt-BR")
        ];
        const casedReplacement = replacement
            ? preserveCase(candidate.text, replacement)
            : null;
        if (!casedReplacement || casedReplacement === candidate.text) {
            return false;
        }

        const editor = getLexicalEditor(element);
        const insertText = editor
            ? findCommand(editor, "CONTROLLED_TEXT_INSERTION_COMMAND")
            : null;
        if (!editor || !insertText) {
            return false;
        }

        const originalRange = candidate.selection.getRangeAt(0).cloneRange();
        const wordRange = document.createRange();
        wordRange.setStart(candidate.node, candidate.startOffset);
        wordRange.setEnd(candidate.node, candidate.offset);

        isReplacing = true;
        try {
            return replaceThroughLexicalUpdate(
                editor,
                insertText,
                wordRange,
                originalRange,
                candidate.text.length,
                casedReplacement
            );
        } catch (error) {
            console.error("[ZapZap Accent Autocorrect] replacement failed", error);
            return false;
        } finally {
            isReplacing = false;
        }
    }

    function onKeyDown(event) {
        if (
            !enabled ||
            isReplacing ||
            event.isComposing ||
            event.ctrlKey ||
            event.altKey ||
            event.metaKey ||
            !DELIMITERS.has(event.key)
        ) {
            return;
        }
        const element = getOriginatingEditorElement(event.target);
        if (element) {
            replacePreviousWord(element);
        }
    }

    function installListener() {
        if (!listenerInstalled) {
            document.addEventListener("keydown", onKeyDown, true);
            listenerInstalled = true;
        }
    }

    function removeListener() {
        if (listenerInstalled) {
            document.removeEventListener("keydown", onKeyDown, true);
            listenerInstalled = false;
        }
    }

    function configure(nextConfig) {
        enabled = Boolean(nextConfig?.enabled);
        const safeCorrections = Object.assign(
            Object.create(null),
            nextConfig?.corrections || {}
        );
        corrections = Object.freeze(safeCorrections);
        if (enabled) {
            installListener();
        } else {
            removeListener();
        }
    }

    window[RUNTIME_NAME] = {
        configure,
        correctPreviousWord(element) {
            return replacePreviousWord(element);
        },
        destroy() {
            removeListener();
            delete window[RUNTIME_NAME];
        },
    };
})();
