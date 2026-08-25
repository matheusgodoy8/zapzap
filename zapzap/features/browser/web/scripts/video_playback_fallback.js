(() => {
    "use strict";

    if (window.__zapzapVideoPlaybackFallbackInstalled) {
        return;
    }
    window.__zapzapVideoPlaybackFallbackInstalled = true;

    const message = __ZAPZAP_VIDEO_MESSAGE__;
    const saveLabel = __ZAPZAP_VIDEO_SAVE__;
    const openLabel = __ZAPZAP_VIDEO_OPEN__;
    const closeLabel = __ZAPZAP_VIDEO_CLOSE__;
    const fetchErrorMessage = __ZAPZAP_VIDEO_FETCH_ERROR__;
    const openFilePrefix = "zapzap-open-video-";
    const trackedVideoBlobs = new Map();
    const probedVideoBlobs = new WeakSet();
    const presentedVideoBlobs = new WeakSet();
    const presentedStreamVideos = new WeakSet();
    const nativeCreateObjectURL = URL.createObjectURL;
    const nativeRevokeObjectURL = URL.revokeObjectURL;
    const nativeFetch = window.fetch.bind(window);
    let activeFallbackCleanup = null;
    let videoDownloadArmedUntil = 0;

    const isVideoDownloadControl = (target) => {
        if (!(target instanceof Element)) {
            return false;
        }
        if (target.closest('[data-zapzap-video-fallback="true"]')) {
            return false;
        }
        const control = target.closest('button,[role="button"]');
        if (!control) {
            return false;
        }
        const description = [
            control.getAttribute("aria-label") || "",
            control.getAttribute("title") || "",
            control.textContent || "",
        ].join(" ");
        const hasDownloadIcon = Boolean(
            control.querySelector('[data-icon*="download" i]')
        );
        const hasDownloadLabel = /\b(download|baixar)\b/i.test(description);
        const hasFileSize = /\b\d+(?:[.,]\d+)?\s*(?:kb|mb|gb)\b/i.test(
            description
        );
        return hasDownloadIcon || hasDownloadLabel || hasFileSize;
    };

    document.addEventListener("click", (event) => {
        if (isVideoDownloadControl(event.target)) {
            videoDownloadArmedUntil = Date.now() + 2 * 60 * 1000;
        }
    }, true);

    const isVideoDownloadArmed = () => Date.now() <= videoDownloadArmedUntil;

    const isVideoBlob = (value) => (
        typeof Blob !== "undefined"
        && value instanceof Blob
        && typeof value.type === "string"
        && value.type.toLowerCase().startsWith("video/")
    );

    const isWhatsAppStreamVideo = (sourceUrl) => {
        try {
            const parsed = new URL(sourceUrl, window.location.href);
            return (
                parsed.protocol === "https:"
                && parsed.origin === "https://web.whatsapp.com"
                && parsed.pathname === "/stream/video"
            );
        } catch (_error) {
            return false;
        }
    };

    const timestamp = () => {
        const now = new Date();
        const pad = (value) => String(value).padStart(2, "0");
        return (
            `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`
            + `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
        );
    };

    const extensionFor = (blob) => {
        const mimeType = (blob && blob.type ? blob.type : "").toLowerCase();
        if (mimeType.includes("webm")) {
            return "webm";
        }
        if (mimeType.includes("quicktime")) {
            return "mov";
        }
        if (mimeType.includes("ogg")) {
            return "ogv";
        }
        if (mimeType.includes("x-m4v")) {
            return "m4v";
        }
        return "mp4";
    };

    const requestDownload = (objectUrl, fileName) => {
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = fileName;
        anchor.hidden = true;
        (document.body || document.documentElement).appendChild(anchor);
        anchor.click();
        anchor.remove();
    };

    const requestSystemPlayerDownload = (blob) => {
        const objectUrl = nativeCreateObjectURL.call(URL, blob);
        requestDownload(
            objectUrl,
            `${openFilePrefix}${timestamp()}.${extensionFor(blob)}`,
        );
        window.setTimeout(() => {
            nativeRevokeObjectURL.call(URL, objectUrl);
        }, 10 * 60 * 1000);
    };

    const fetchStreamVideo = async (sourceUrl) => {
        const response = await nativeFetch(sourceUrl, {
            credentials: "include",
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error("video request failed");
        }
        if (response.url && !isWhatsAppStreamVideo(response.url)) {
            throw new Error("unexpected video response origin");
        }

        const downloaded = await response.blob();
        if (!downloaded.size) {
            throw new Error("empty video response");
        }
        if (isVideoBlob(downloaded)) {
            return downloaded;
        }

        // WhatsApp currently serves /stream/video as application/octet-stream.
        // The failed HTMLVideoElement and the constrained route establish that
        // this response is video; assigning a video MIME lets DownloadManager
        // keep its strict MIME check without handling arbitrary downloads.
        return downloaded.slice(0, downloaded.size, "video/mp4");
    };

    const createButton = (label) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = label;
        button.style.cssText = [
            "appearance:none",
            "border:1px solid rgba(255,255,255,.35)",
            "border-radius:999px",
            "background:rgba(32,44,51,.94)",
            "color:#fff",
            "cursor:pointer",
            "font:600 13px system-ui,sans-serif",
            "padding:8px 14px",
        ].join(";");
        return button;
    };

    const showFallback = ({
        blob = null,
        fallbackUrl = null,
        streamVideo = null,
        streamUrl = "",
    }) => {
        if (blob && presentedVideoBlobs.has(blob)) {
            nativeRevokeObjectURL.call(URL, fallbackUrl);
            return;
        }
        if (streamVideo && presentedStreamVideos.has(streamVideo)) {
            return;
        }
        if (blob) {
            presentedVideoBlobs.add(blob);
        }
        if (streamVideo) {
            presentedStreamVideos.add(streamVideo);
        }
        videoDownloadArmedUntil = 0;

        if (activeFallbackCleanup) {
            activeFallbackCleanup();
        }

        const banner = document.createElement("div");
        banner.dataset.zapzapVideoFallback = "true";
        banner.setAttribute("role", "alert");
        banner.style.cssText = [
            "position:fixed",
            "top:20px",
            "left:50%",
            "transform:translateX(-50%)",
            "z-index:2147483647",
            "display:flex",
            "flex-direction:column",
            "align-items:center",
            "gap:12px",
            "box-sizing:border-box",
            "width:min(520px,calc(100vw - 32px))",
            "padding:18px 48px 18px 20px",
            "border:1px solid rgba(255,255,255,.2)",
            "border-radius:12px",
            "box-shadow:0 8px 28px rgba(0,0,0,.35)",
            "background:rgba(17,27,33,.97)",
            "color:#fff",
            "text-align:center",
            "font:14px/1.4 system-ui,sans-serif",
        ].join(";");

        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.textContent = "×";
        closeButton.setAttribute("aria-label", closeLabel);
        closeButton.style.cssText = [
            "position:absolute",
            "top:8px",
            "right:10px",
            "border:0",
            "background:transparent",
            "color:#fff",
            "cursor:pointer",
            "font:24px/1 system-ui,sans-serif",
            "padding:4px 8px",
        ].join(";");

        const explanation = document.createElement("div");
        explanation.textContent = message;

        const actions = document.createElement("div");
        actions.style.cssText = (
            "display:flex;flex-wrap:wrap;justify-content:center;gap:8px"
        );

        const openButton = createButton(openLabel);
        openButton.addEventListener("click", async () => {
            if (blob) {
                requestDownload(
                    fallbackUrl,
                    `${openFilePrefix}${timestamp()}.${extensionFor(blob)}`,
                );
                return;
            }

            openButton.disabled = true;
            openButton.style.opacity = "0.65";
            try {
                const fetchedBlob = await fetchStreamVideo(streamUrl);
                requestSystemPlayerDownload(fetchedBlob);
                cleanup();
            } catch (_error) {
                explanation.textContent = fetchErrorMessage;
                openButton.disabled = false;
                openButton.style.opacity = "1";
            }
        });

        let cleanedUp = false;
        const cleanup = () => {
            if (cleanedUp) {
                return;
            }
            cleanedUp = true;
            banner.remove();
            if (fallbackUrl) {
                nativeRevokeObjectURL.call(URL, fallbackUrl);
            }
            if (streamVideo) {
                presentedStreamVideos.delete(streamVideo);
            }
            if (activeFallbackCleanup === cleanup) {
                activeFallbackCleanup = null;
            }
        };
        activeFallbackCleanup = cleanup;
        closeButton.addEventListener("click", cleanup);

        if (blob) {
            const saveButton = createButton(saveLabel);
            saveButton.addEventListener("click", () => {
                requestDownload(
                    fallbackUrl,
                    `WhatsApp-video-${timestamp()}.${extensionFor(blob)}`,
                );
            });
            actions.append(saveButton);
        }
        actions.append(openButton);
        banner.append(closeButton, explanation, actions);
        (document.body || document.documentElement).appendChild(banner);
        window.setTimeout(cleanup, 10 * 60 * 1000);
    };

    const probeVideoBlob = (blob) => {
        if (probedVideoBlobs.has(blob)) {
            return;
        }
        probedVideoBlobs.add(blob);

        const fallbackUrl = nativeCreateObjectURL.call(URL, blob);
        const probe = document.createElement("video");
        probe.preload = "auto";
        probe.muted = true;
        probe.playsInline = true;
        let settled = false;

        const finishAsSupported = () => {
            if (settled) {
                return;
            }
            settled = true;
            videoDownloadArmedUntil = 0;
            probe.removeAttribute("src");
            probe.load();
            nativeRevokeObjectURL.call(URL, fallbackUrl);
        };
        const finishAsUnsupported = () => {
            if (settled) {
                return;
            }
            settled = true;
            probe.removeAttribute("src");
            probe.load();
            showFallback({blob, fallbackUrl});
        };

        probe.addEventListener("canplay", finishAsSupported, {once: true});
        probe.addEventListener("error", finishAsUnsupported, {once: true});
        probe.src = fallbackUrl;
        probe.load();

        window.setTimeout(() => {
            if (settled) {
                return;
            }
            if (probe.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
                finishAsSupported();
            } else {
                finishAsUnsupported();
            }
        }, 8000);
    };

    URL.createObjectURL = function createObjectURL(value) {
        const objectUrl = nativeCreateObjectURL.call(this, value);
        if (isVideoBlob(value)) {
            trackedVideoBlobs.set(objectUrl, value);
            if (isVideoDownloadArmed()) {
                window.setTimeout(() => probeVideoBlob(value), 0);
            }
        }
        return objectUrl;
    };

    URL.revokeObjectURL = function revokeObjectURL(objectUrl) {
        trackedVideoBlobs.delete(String(objectUrl));
        return nativeRevokeObjectURL.call(this, objectUrl);
    };

    document.addEventListener("error", (event) => {
        if (!(event.target instanceof HTMLVideoElement)) {
            return;
        }
        const mediaError = event.target.error;
        if (!mediaError || ![3, 4].includes(mediaError.code)) {
            return;
        }
        const sourceUrl = event.target.currentSrc || event.target.src || "";
        if (isWhatsAppStreamVideo(sourceUrl)) {
            showFallback({
                streamVideo: event.target,
                streamUrl: sourceUrl,
            });
            return;
        }
        if (!isVideoDownloadArmed()) {
            return;
        }
        if (!sourceUrl.startsWith("blob:https://web.whatsapp.com/")) {
            return;
        }
        const blob = trackedVideoBlobs.get(sourceUrl);
        if (!blob) {
            return;
        }
        showFallback({
            blob,
            fallbackUrl: nativeCreateObjectURL.call(URL, blob),
        });
    }, true);
})();
