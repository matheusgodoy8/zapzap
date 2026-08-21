# Changelog

All changes and additions to ZapZap are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/).
Every pull request or commit that changes the repository must add or update an
entry under the version currently marked `In development`, including internal,
documentation, test, packaging, and workflow changes.

This mandatory record starts after version 7.4.1. The 7.4.1 entry below is the
historical baseline; older release summaries remain available in the GitHub
releases and the AppStream metadata.

## [7.4.7] - In development

### Fixed

- Fixed unread-message badges not appearing in KDE Plasma by publishing the
  launcher update through Plasma's supported D-Bus protocol and retaining a
  dynamic window-icon fallback.
- Restored the numeric unread-message badge on each active account avatar and
  kept the desktop badge synchronized with the sum from multiple accounts.
- Identified native notifications with the account name saved by the user,
  before the contact name, and exposed ZapZap's display name to desktop shells.
- Fixed the global unread count missing from the Windows taskbar by publishing
  a native numeric overlay instead of relying only on Qt window-icon changes.

## [7.4.6] - 2026-08-20

### Fixed

- Fixed Linux AppImages failing at startup when a continuously published
  reduced Qt Base package lagged behind the official Qt QML and WebEngine
  modules.

## [7.4.5] - 2026-08-20

### Added

- Added an opt-in pre-release channel to automatic and manual update checks for
  official Windows executables and Linux AppImages.
- Added the total unread-message count to supported Linux taskbars through
  Qt's native application badge integration.

## [7.4.4] - 2026-08-18

### Fixed

- Fixed the Windows executable and taskbar using Python's icon by embedding the
  ZapZap icon and assigning the process a stable Windows application identity.
- Prevented attendant identification from redirecting typing in WhatsApp's
  conversation search to an empty message composer.

### Added

- Added the total unread-message count to the Windows taskbar icon, matching
  the existing numeric indicator used by the system tray.
- Added an opt-in verified auto-updater and manual update checks to the About
  page for official Windows executables and Linux AppImages.
- Added local attendant identification for shared WhatsApp accounts, with
  isolated preferences selected by account and optional signatures for text
  messages, media captions, and media sent without a caption.
- Added a rolling `continuous` GitHub pre-release that rebuilds and replaces
  Windows and AppImage assets after every push to the main branch.

### Changed

- Adopted versioned development cycles so new work identifies itself with the
  next numeric version while release builds retain the version being published.
- Pointed official project links, diagnostics, release checks, and verified
  update downloads to `matheusgodoy8/zapzap`.
- Embedded the source commit in generated build metadata so consecutive
  continuous AppImages have distinct, verifiable contents for update checks.
- Allowed the documentation contract to validate a dated release-closing
  changelog before its tag is published.

### Removed

- Removed the experimental desktop-sharing picker after Wayland portal and
  PipeWire sessions caused unbounded memory growth; the existing WebEngine
  permission flow remains unchanged while the integration is redesigned.

## [7.4.2] - 2026-08-14

### Fixed

- Prevented invalid HTTP cache limits from stopping startup by repairing stored
  values and falling back to Qt's automatic cache management.
- Prevented malformed Qt-facing settings from aborting startup or account
  loading by repairing scale, window state, cache type, tray theme, zoom,
  spellcheck, proxy, theme, and download parameters with scoped fallbacks.
- Kept failed proxy changes pending with visible feedback while preserving the
  previously active proxy, and isolated a failed WebEngine profile so other
  accounts can still load and the failed account can be retried.
- Connected the persistent-cookies preference to each WebEngine profile and
  migrated the JavaScript memory-limit selector to the startup flag while
  keeping its legacy key synchronized.

### Added

- Added a sidebar shortcut for WhatsApp Web's native app lock, keeping lock
  setup and authentication entirely inside WhatsApp.
- Added this changelog as the mandatory source of truth for all project changes
  and additions.
- Added strict proxy isolation for explicit HTTP and SOCKS5 proxies, using
  Chromium's native policy to block non-proxied WebRTC UDP after restart.

### Changed

- Applied the global proxy before any functional WebEngine profile is created
  and kept proxy failures fail-closed without a direct-connection fallback.

### Removed

- Removed misleading per-account proxy settings and proxy changes during
  account switching; all accounts now use the single global proxy.

## [7.4.1] - 2026-08-12

### Added

- Added an update indicator with release details and quick access to release
  notes and downloads.

### Changed

- Improved reliability when ZapZap is closed by the operating system.
- Included performance improvements.

[7.4.7]: https://github.com/matheusgodoy8/zapzap/compare/7.4.6...HEAD
[7.4.6]: https://github.com/matheusgodoy8/zapzap/compare/7.4.5...7.4.6
[7.4.5]: https://github.com/matheusgodoy8/zapzap/compare/7.4.4...7.4.5
[7.4.4]: https://github.com/matheusgodoy8/zapzap/compare/7.4.2...7.4.4
[7.4.2]: https://github.com/matheusgodoy8/zapzap/compare/7.4.1...7.4.2
[7.4.1]: https://github.com/matheusgodoy8/zapzap/releases/tag/7.4.1
