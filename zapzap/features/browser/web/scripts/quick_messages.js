(() => {
    "use strict";

    const RUNTIME_NAME = "__zapzapQuickMessages";
    const BUTTON_ATTRIBUTE = "data-zapzap-quick-messages";
    const POPUP_ATTRIBUTE = "data-zapzap-quick-messages-popup";
    const COMPOSER_SELECTOR =
        '[data-testid="conversation-compose-box-input"]' +
        '[contenteditable="true"][data-lexical-editor="true"], ' +
        '[contenteditable="true"][data-lexical-editor="true"][data-tab="10"]';
    const LEXICAL_KEY = /^__lexicalEditor/;

    window[RUNTIME_NAME]?.destroy?.();

    let config = Object.freeze({ messages: [], labels: {} });
    let observer = null;
    let button = null;
    let popup = null;
    let observedComposer = null;
    let savedRange = null;
    let reconcileQueued = false;

    function lexicalEditor(element) {
        if (!(element instanceof HTMLElement)) return null;
        try {
            const key = Object.keys(element).find((name) => LEXICAL_KEY.test(name));
            return key ? element[key] : null;
        } catch (_error) {
            return null;
        }
    }

    function command(editor, type) {
        try {
            return [...editor._commands.keys()].find((item) => item?.type === type) || null;
        } catch (_error) {
            return null;
        }
    }

    function composer() {
        return [...document.querySelectorAll(COMPOSER_SELECTOR)].find(
            (element) => Boolean(lexicalEditor(element))
        ) || null;
    }

    function semanticValue(element) {
        return [
            element?.getAttribute?.("data-testid"),
            element?.getAttribute?.("aria-label"),
            element?.getAttribute?.("title"),
        ].filter(Boolean).join(" ");
    }

    function attachmentControl(root) {
        const controls = [...root.querySelectorAll('button, [role="button"]')];
        const semanticControl = controls.find((element) =>
            /(?:attach|attachment|anexar|clip)/i.test(semanticValue(element))
        );
        if (semanticControl) return semanticControl;

        const plusMarker = root.querySelector(
            '[data-testid="plus-rounded"], [data-testid*="attach" i]'
        );
        return plusMarker?.closest('button, [role="button"]') || null;
    }

    function isHorizontalFlex(element) {
        if (!(element instanceof HTMLElement)) return false;
        const style = getComputedStyle(element);
        return (
            (style.display === "flex" || style.display === "inline-flex") &&
            (style.flexDirection === "row" || style.flexDirection === "row-reverse")
        );
    }

    function composerRowPlacement(root, composerElement) {
        const control = attachmentControl(root);
        if (!control) return null;

        let slot = control;
        while (slot.parentElement && slot.parentElement !== root) {
            const parent = slot.parentElement;
            if (
                isHorizontalFlex(parent) &&
                parent.contains(composerElement)
            ) {
                return { container: parent, after: slot };
            }
            slot = parent;
        }
        return null;
    }

    function buttonPlacementIsValid(composerElement) {
        const container = button?.parentElement;
        return Boolean(
            container &&
            isHorizontalFlex(container) &&
            container.contains(composerElement)
        );
    }

    function captureSelection(element) {
        const selection = window.getSelection();
        if (!selection || selection.rangeCount === 0) return;
        const range = selection.getRangeAt(0);
        if (element.contains(range.commonAncestorContainer)) {
            savedRange = range.cloneRange();
        }
    }

    function buttonStyle(element) {
        Object.assign(element.style, {
            appearance: "none",
            background: "transparent",
            border: "0",
            borderRadius: "999px",
            color: "var(--icon, var(--secondary, #667781))",
            cursor: "pointer",
            display: "inline-grid",
            flex: "0 0 auto",
            font: "inherit",
            height: "40px",
            margin: "0 2px",
            placeItems: "center",
            width: "40px",
        });
    }

    function makeButton(element) {
        const next = document.createElement("button");
        next.type = "button";
        next.setAttribute(BUTTON_ATTRIBUTE, "");
        next.setAttribute("aria-label", config.labels.button || "Quick messages");
        next.setAttribute("title", config.labels.button || "Quick messages");
        next.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 8h8M8 12h6"/></svg>';
        buttonStyle(next);
        next.addEventListener("pointerdown", () => captureSelection(element), true);
        next.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            popup ? closePopup() : openPopup(next);
        });
        return next;
    }

    function installButton() {
        const element = composer();
        if (!element) {
            closePopup();
            button?.remove();
            button = null;
            observedComposer = null;
            return;
        }
        if (
            button?.isConnected &&
            observedComposer === element &&
            buttonPlacementIsValid(element)
        ) {
            return;
        }
        button?.remove();
        closePopup();
        const root = element.closest("footer") || element.parentElement?.parentElement;
        if (!root) return;
        const placement = composerRowPlacement(root, element);
        if (!placement) return;

        const existing = placement.container.querySelector(
            `:scope > [${BUTTON_ATTRIBUTE}]`
        );
        if (existing instanceof HTMLButtonElement) {
            button = existing;
            observedComposer = element;
            return;
        }

        button = makeButton(element);
        placement.container.insertBefore(button, placement.after.nextSibling);
        observedComposer = element;
    }

    function queueReconcile() {
        if (reconcileQueued) return;
        reconcileQueued = true;
        window.requestAnimationFrame(() => {
            reconcileQueued = false;
            const currentComposer = composer();
            if (
                !button?.isConnected ||
                currentComposer !== observedComposer ||
                !buttonPlacementIsValid(currentComposer)
            ) {
                installButton();
            }
        });
    }

    function popupStyle(element) {
        Object.assign(element.style, {
            background: "var(--panel-background, #fff)",
            border: "1px solid var(--border-strong, rgba(11, 20, 26, .14))",
            borderRadius: "12px",
            boxShadow: "0 6px 24px rgba(11, 20, 26, .22)",
            color: "var(--primary, #111b21)",
            display: "flex",
            flexDirection: "column",
            fontFamily: "inherit",
            maxHeight: "min(430px, 65vh)",
            overflow: "hidden",
            position: "fixed",
            width: "min(360px, calc(100vw - 24px))",
            zIndex: "2147483646",
        });
    }

    function visibleMessages(query) {
        const term = query.trim().toLocaleLowerCase();
        if (!term) return config.messages;
        return config.messages.filter((message) =>
            `${message.title}\n${message.content}`.toLocaleLowerCase().includes(term)
        );
    }

    function renderItems(container, query = "") {
        container.replaceChildren();
        const matches = visibleMessages(query);
        if (!matches.length) {
            const empty = document.createElement("div");
            empty.style.padding = "20px 16px";
            empty.style.color = "var(--secondary, #667781)";
            empty.style.textAlign = "center";
            empty.textContent = config.labels.empty || "No quick messages configured.";
            container.appendChild(empty);
            if (!config.messages.length) {
                const hint = document.createElement("div");
                hint.style.marginTop = "6px";
                hint.style.fontSize = "12px";
                hint.textContent = config.labels.hint || "Add messages in Settings > Quick messages.";
                empty.appendChild(hint);
            }
            return;
        }
        for (const message of matches) {
            const item = document.createElement("button");
            item.type = "button";
            Object.assign(item.style, {
                background: "transparent", border: "0", color: "inherit", cursor: "pointer",
                display: "block", font: "inherit", padding: "11px 16px", textAlign: "left", width: "100%",
            });
            const title = document.createElement("div");
            title.style.fontWeight = "600";
            title.textContent = message.title;
            const preview = document.createElement("div");
            preview.style.color = "var(--secondary, #667781)";
            preview.style.fontSize = "13px";
            preview.style.marginTop = "3px";
            preview.style.overflow = "hidden";
            preview.style.textOverflow = "ellipsis";
            preview.style.whiteSpace = "nowrap";
            preview.textContent = message.content.replace(/\s+/g, " ").trim();
            item.append(title, preview);
            item.addEventListener("mouseenter", () => item.style.background = "var(--background-default-hover, rgba(11, 20, 26, .06))");
            item.addEventListener("mouseleave", () => item.style.background = "transparent");
            item.addEventListener("click", () => insertMessage(message.content));
            container.appendChild(item);
        }
    }

    function openPopup(anchor) {
        closePopup();
        const panel = document.createElement("section");
        panel.setAttribute(POPUP_ATTRIBUTE, "");
        panel.setAttribute("aria-label", config.labels.title || "Quick messages");
        popupStyle(panel);
        const heading = document.createElement("strong");
        heading.style.padding = "14px 16px 8px";
        heading.textContent = config.labels.title || "Quick messages";
        const search = document.createElement("input");
        search.type = "search";
        search.placeholder = config.labels.search || "Search messages…";
        search.setAttribute("aria-label", search.placeholder);
        Object.assign(search.style, {
            background: "var(--search-container-background, rgba(11, 20, 26, .06))",
            border: "1px solid transparent", borderRadius: "8px", color: "inherit",
            font: "inherit", margin: "0 12px 8px", outline: "none", padding: "8px 10px",
        });
        const items = document.createElement("div");
        items.style.overflowY = "auto";
        search.addEventListener("input", () => renderItems(items, search.value));
        panel.append(heading, search, items);
        renderItems(items);
        document.body.appendChild(panel);
        const rect = anchor.getBoundingClientRect();
        const panelRect = panel.getBoundingClientRect();
        panel.style.left = `${Math.max(12, Math.min(rect.left, innerWidth - panelRect.width - 12))}px`;
        panel.style.top = `${Math.max(12, rect.top - panelRect.height - 8)}px`;
        popup = panel;
        search.focus();
    }

    function closePopup() {
        popup?.remove();
        popup = null;
    }

    function restoreSelection(element) {
        if (!savedRange || !element.contains(savedRange.commonAncestorContainer)) return false;
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(savedRange);
        return true;
    }

    function insertMessage(content) {
        const element = observedComposer?.isConnected ? observedComposer : composer();
        closePopup();
        if (!element) return false;
        const editor = lexicalEditor(element);
        const insertText = command(editor, "CONTROLLED_TEXT_INSERTION_COMMAND");
        if (!editor || !insertText) return false;
        const hadSelection = restoreSelection(element);
        element.focus();
        window.__zapzapAttendantSignature?.prepareComposer?.(element);
        let text = String(content);
        if (!hadSelection && element.innerText && !element.innerText.endsWith("\n")) {
            text = `\n${text}`;
        }
        try {
            editor.dispatchCommand(insertText, text);
            element.focus();
            savedRange = null;
            return true;
        } catch (error) {
            console.error("[ZapZap Quick Messages] insertion failed", error);
            return false;
        }
    }

    function onDocumentPointerDown(event) {
        if (!popup || popup.contains(event.target) || button?.contains(event.target)) return;
        closePopup();
    }

    function onKeyDown(event) {
        if (event.key === "Escape" && popup) closePopup();
    }

    function configure(nextConfig) {
        config = Object.freeze({
            messages: Array.isArray(nextConfig?.messages) ? nextConfig.messages : [],
            labels: nextConfig?.labels || {},
        });
        if (button) {
            button.setAttribute("aria-label", config.labels.button || "Quick messages");
            button.setAttribute("title", config.labels.button || "Quick messages");
        }
        if (popup) openPopup(button);
        installButton();
    }

    document.addEventListener("pointerdown", onDocumentPointerDown, true);
    document.addEventListener("keydown", onKeyDown, true);
    const root = document.querySelector("#app") || document.documentElement;
    observer = new MutationObserver(queueReconcile);
    observer.observe(root, { childList: true, subtree: true });

    window[RUNTIME_NAME] = {
        configure,
        insertMessage,
        destroy() {
            observer?.disconnect();
            observer = null;
            document.removeEventListener("pointerdown", onDocumentPointerDown, true);
            document.removeEventListener("keydown", onKeyDown, true);
            closePopup();
            button?.remove();
            button = null;
            delete window[RUNTIME_NAME];
        },
    };
})();
