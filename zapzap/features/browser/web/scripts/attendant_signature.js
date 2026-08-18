(() => {
    const RUNTIME_NAME = "__zapzapAttendantSignature";
    const CONTEXT = Object.freeze({
        NORMAL_COMPOSER: "NORMAL_COMPOSER",
        EDIT_MESSAGE: "EDIT_MESSAGE",
        MEDIA_CAPTION: "MEDIA_CAPTION",
        UNKNOWN: "UNKNOWN",
    });
    const LEXICAL_EDITABLE_SELECTOR =
        '[contenteditable="true"][data-lexical-editor="true"]';
    const NORMAL_COMPOSER_SELECTOR =
        '[data-testid="conversation-compose-box-input"]' +
        LEXICAL_EDITABLE_SELECTOR;

    try {
        window[RUNTIME_NAME]?.destroy?.();
    } catch (_error) {
        // A stale runtime must not prevent the replacement from loading.
    }

    let config = Object.freeze({
        enabled: false,
        attendantName: "",
        signTextMessages: true,
        signMediaCaptions: true,
        signEmptyMedia: false,
        debug: false,
    });
    let isInserting = false;
    let listenersInstalled = false;
    let missingInsertionCommandLogged = false;
    const loggedContexts = new WeakMap();

    function debugLog(message, details) {
        if (config.debug) {
            console.debug(`[ZapZap Signature] ${message}`, details || "");
        }
    }

    function normalizeText(text) {
        return String(text || "")
            .replace(/\u200B/g, "")
            .replace(/\u00A0/g, " ")
            .replace(/\r\n?/g, "\n");
    }

    function isEmpty(element) {
        return normalizeText(element?.innerText).trim() === "";
    }

    function hasSignature(text) {
        if (!config.attendantName) {
            return false;
        }
        const normalized = normalizeText(text).trimStart();
        return (
            normalized === config.attendantName ||
            normalized.startsWith(`${config.attendantName}\n`)
        );
    }

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

    function semanticValue(element) {
        return [
            element.getAttribute("data-testid") || "",
            element.getAttribute("aria-label") || "",
            element.getAttribute("role") || "",
        ]
            .join(" ")
            .toLowerCase();
    }

    function semanticAncestry(element) {
        const values = [];
        let current = element;
        let depth = 0;
        while (
            current instanceof Element &&
            current !== document.body &&
            depth < 12
        ) {
            values.push(semanticValue(current));
            current = current.parentElement;
            depth += 1;
        }
        return values.join(" ");
    }

    function getEditorContext(element) {
        if (!(element instanceof Element) || !getLexicalEditor(element)) {
            return CONTEXT.UNKNOWN;
        }
        if (element.matches(NORMAL_COMPOSER_SELECTOR)) {
            return CONTEXT.NORMAL_COMPOSER;
        }

        const semantics = semanticAncestry(element);
        if (
            /(?:media[-_ ]?caption|caption[-_ ]?input|\bcaption\b|\blegenda\b)/i.test(
                semantics
            )
        ) {
            return CONTEXT.MEDIA_CAPTION;
        }
        if (
            /(?:edit[-_ ]?message|message[-_ ]?edit|editar[^ ]* mensagem|editar mensagem)/i.test(
                semantics
            )
        ) {
            return CONTEXT.EDIT_MESSAGE;
        }

        const dialog = element.closest('[role="dialog"]');
        if (dialog) {
            const mediaMarker = dialog.querySelector(
                '[data-testid*="caption" i], [data-testid*="media" i], ' +
                    '[aria-label*="caption" i], [aria-label*="legenda" i]'
            );
            return mediaMarker
                ? CONTEXT.MEDIA_CAPTION
                : CONTEXT.EDIT_MESSAGE;
        }
        return CONTEXT.UNKNOWN;
    }

    function logDetectedContext(context, element, editor) {
        if (
            !config.debug ||
            context === CONTEXT.UNKNOWN ||
            loggedContexts.get(element) === context
        ) {
            return;
        }
        loggedContexts.set(element, context);
        debugLog(`context=${context}`, {
            element,
            editor,
            testId: element.getAttribute("data-testid"),
            ariaLabel: element.getAttribute("aria-label"),
        });
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

    function insertSignature(editor, element, withLineBreak = true) {
        if (
            isInserting ||
            !config.enabled ||
            !config.attendantName ||
            !editor ||
            !element ||
            hasSignature(element.innerText) ||
            !isEmpty(element)
        ) {
            return false;
        }

        const insertText = findCommand(
            editor,
            "CONTROLLED_TEXT_INSERTION_COMMAND"
        );
        const insertLineBreak = findCommand(
            editor,
            "INSERT_LINE_BREAK_COMMAND"
        );
        const insertParagraph = findCommand(editor, "INSERT_PARAGRAPH_COMMAND");
        if (!insertText) {
            if (!missingInsertionCommandLogged) {
                console.error(
                    "[ZapZap Signature] CONTROLLED_TEXT_INSERTION_COMMAND not found"
                );
                missingInsertionCommandLogged = true;
            }
            return false;
        }

        isInserting = true;
        try {
            element.focus();
            editor.dispatchCommand(insertText, config.attendantName);
            if (withLineBreak) {
                if (insertLineBreak) {
                    editor.dispatchCommand(insertLineBreak, false);
                } else if (insertParagraph) {
                    editor.dispatchCommand(insertParagraph, undefined);
                } else {
                    editor.dispatchCommand(insertText, "\n");
                }
            }
            return true;
        } catch (error) {
            console.error("[ZapZap Signature] insertion failed", error);
            return false;
        } finally {
            isInserting = false;
        }
    }

    function handleNormalComposer(editor, element) {
        return config.signTextMessages
            ? insertSignature(editor, element)
            : false;
    }

    function handleEditMessage(_editor, element) {
        // Editing must never move focus or dispatch to the composer behind
        // the edit dialog. Existing signatures are intentionally untouched.
        return hasSignature(element.innerText);
    }

    function handleMediaCaption(editor, element, emptyCaptionSubmission) {
        if (!config.signMediaCaptions) {
            return false;
        }
        if (emptyCaptionSubmission) {
            return config.signEmptyMedia
                ? insertSignature(editor, element, false)
                : false;
        }
        return insertSignature(editor, element);
    }

    function handleTextInsertionEvent(event) {
        if (!config.enabled || isInserting || event.isComposing) {
            return;
        }
        const element = getOriginatingEditorElement(event.target);
        if (!element) {
            return;
        }
        const editor = getLexicalEditor(element);
        const context = getEditorContext(element);
        logDetectedContext(context, element, editor);
        if (context === CONTEXT.NORMAL_COMPOSER) {
            handleNormalComposer(editor, element);
        } else if (context === CONTEXT.EDIT_MESSAGE) {
            handleEditMessage(editor, element);
        } else if (context === CONTEXT.MEDIA_CAPTION) {
            handleMediaCaption(editor, element, false);
        }
    }

    function onKeyDown(event) {
        if (
            isInserting ||
            event.isComposing ||
            event.ctrlKey ||
            event.altKey ||
            event.metaKey
        ) {
            return;
        }
        if (event.key && event.key.length === 1) {
            handleTextInsertionEvent(event);
            return;
        }
        if (
            event.key === "Enter" &&
            !event.shiftKey &&
            config.signMediaCaptions &&
            config.signEmptyMedia
        ) {
            const element = getOriginatingEditorElement(event.target);
            if (!element || !isEmpty(element)) {
                return;
            }
            const editor = getLexicalEditor(element);
            const context = getEditorContext(element);
            logDetectedContext(context, element, editor);
            if (context === CONTEXT.MEDIA_CAPTION) {
                handleMediaCaption(editor, element, true);
            }
        }
    }

    function onBeforeInput(event) {
        if (isInserting) {
            return;
        }
        const inputType = event.inputType || "";
        if (
            inputType.startsWith("insert") &&
            inputType !== "insertParagraph" &&
            inputType !== "insertLineBreak"
        ) {
            handleTextInsertionEvent(event);
        }
    }

    function onPaste(event) {
        if (!isInserting) {
            handleTextInsertionEvent(event);
        }
    }

    function onPointerDown(event) {
        if (
            !config.enabled ||
            !config.signMediaCaptions ||
            !config.signEmptyMedia ||
            isInserting ||
            !(event.target instanceof Element)
        ) {
            return;
        }
        const control =
            event.target.closest('button, [role="button"]') ||
            event.target.closest("[data-testid]");
        if (
            !control ||
            !/(?:^|[-_ ])send(?:$|[-_ ])|\benviar\b/i.test(
                semanticValue(control)
            )
        ) {
            return;
        }

        // Empty-caption submission originates in the send control. The only
        // allowed lookup is inside that same dialog, never in document.
        const dialog = control.closest('[role="dialog"]');
        if (!dialog) {
            return;
        }
        const candidates = [
            ...dialog.querySelectorAll(LEXICAL_EDITABLE_SELECTOR),
        ].filter(
            (element) =>
                getEditorContext(element) === CONTEXT.MEDIA_CAPTION
        );
        if (candidates.length !== 1 || !isEmpty(candidates[0])) {
            return;
        }
        const element = candidates[0];
        const editor = getLexicalEditor(element);
        logDetectedContext(CONTEXT.MEDIA_CAPTION, element, editor);
        handleMediaCaption(editor, element, true);
    }

    function installListeners() {
        if (listenersInstalled) {
            return;
        }
        document.addEventListener("keydown", onKeyDown, true);
        document.addEventListener("beforeinput", onBeforeInput, true);
        document.addEventListener("paste", onPaste, true);
        document.addEventListener("pointerdown", onPointerDown, true);
        listenersInstalled = true;
    }

    function removeListeners() {
        if (!listenersInstalled) {
            return;
        }
        document.removeEventListener("keydown", onKeyDown, true);
        document.removeEventListener("beforeinput", onBeforeInput, true);
        document.removeEventListener("paste", onPaste, true);
        document.removeEventListener("pointerdown", onPointerDown, true);
        listenersInstalled = false;
    }

    function configure(nextConfig) {
        const attendantName = String(nextConfig?.attendantName || "").trim();
        config = Object.freeze({
            enabled: Boolean(nextConfig?.enabled) && Boolean(attendantName),
            attendantName,
            signTextMessages: nextConfig?.signTextMessages !== false,
            signMediaCaptions: nextConfig?.signMediaCaptions !== false,
            signEmptyMedia: Boolean(nextConfig?.signEmptyMedia),
            debug: Boolean(nextConfig?.debug),
        });
        if (config.enabled) {
            installListeners();
            debugLog("initialized", {
                signTextMessages: config.signTextMessages,
                signMediaCaptions: config.signMediaCaptions,
                signEmptyMedia: config.signEmptyMedia,
            });
        } else {
            removeListeners();
        }
    }

    window[RUNTIME_NAME] = {
        configure,
        destroy() {
            removeListeners();
            delete window[RUNTIME_NAME];
        },
    };
})();
