# Changelog

All notable changes are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-09-28

### Added

- A typed-combination alternative in both editors, with conflict checks that
  do not require pressing an existing global shortcut.
- Two-step Add shortcut dialog for installed apps, websites, folders, and custom
  commands, with app search/icons, a folder picker, and automatic descriptions.
- Review the exact command, capture keys, and explicitly confirm conflicts
  before saving. No actions are launched during preview or saving.
- Recheck launcher identity and live bindings before creation; reuse the shared
  lock, private backups, validation, and rollback transaction.
- Mark new shortcuts as Added by you and retain that identity through editing,
  deletion, and restoration.

### Fixed

- Keep deleted source-defined actions visible when their old key is reused;
  restoring elsewhere preserves the new owner. Occupied restoration targets
  require choosing another key, and unnamed actions still trigger warnings.
- Request Wayland shortcut inhibition during add/edit dialogs so the compositor
  does not consume occupied combinations before conflict checks. Refuse key
  recording until protection is active, and release it on close.
- Encode Lua strings safely and replace managed blocks without interpreting
  command backslashes. Descriptions are never inserted into Lua comments.
- Preserve toggle calls, binding options, Unicode, and raw physical/mouse keys.
- Apply all managed unbinds before rebindings so moving one shortcut does not
  remove another shortcut that reused its original key.
- Fail closed on malformed or mismatched managed state and stale editor views.
- Serialize edits, reset, and cleanup; use unique private backups and preserve
  symlinked configuration files and unrelated line endings.
- Give reset the same validation and rollback behavior as edits and respect
  `XDG_CONFIG_HOME` consistently.

### Changed

- Use native Omarchy controls and theme colors in a content-sized Add dialog.
  App selection (click or Enter) advances directly to focused key capture.
  Rename shortcuts on the review page and expand command details when needed.
- Simplify dialog chrome with quieter action tabs, app icon fallbacks, larger
  supporting text, individual shortcut keycaps, and one prominent save action.
- Scan compositor metadata directly without executing the user's Lua config.
- Only edit unambiguous, supported binding expressions. Local functions,
  dynamic expressions, submaps, and unavailable runtime data remain read-only.
- Send opaque selection tokens over stdin and recheck the selection and
  conflicts in the helper before writing.
- Recover old state only when its original binding can be reconstructed safely;
  otherwise require backup recovery or explicit managed-only cleanup.
- Retain displaced managed bindings in the Deleted view for restoration.

## [1.1.1] - 2026-09-27

### Fixed

- Send shortcut data to the update helper through standard input so editing,
  restoring, and deleting bindings do not expose private commands in process arguments.

## [1.1.0] - 2026-09-26

### Added

- Two-step shortcut deletion from the row editor, with deleted custom
  shortcuts retained in the Deleted view.
- Restoration by selecting a deleted shortcut, with conflicting keys blocked
  until the user chooses a free combination.

## [1.0.3] - 2026-09-26

### Changed

- Simplified development instructions so marketplace static analysis does not
  mistake a contributor clone example for a runtime remote-build capability.

## [1.0.2] - 2026-09-26

### Added

- Marketplace-ready root preview image.
- Explicit runtime dependency documentation for marketplace review.

## [1.0.1] - 2026-09-26

### Fixed

- Explicitly replacing a key used by an earlier OmaKeybinds edit now removes
  the displaced managed entry instead of retaining two entries for one key.

## [1.0.0] - 2026-09-26

### Added

- Searchable Omarchy Shell shortcut browser and taskbar widget.
- Default, changed, custom, and deleted classifications with filters and counts.
- Safe shortcut editor with collision detection and explicit replacement consent.
- Settings menu and confirmed reset to the installed Omarchy defaults.
- Theme-aware in-shell logo and standalone project artwork.
- Backups, post-write Hyprland validation, automatic rollback, and managed-only cleanup.

[1.1.0]: https://github.com/OddlyCrusty/omakeybinds/releases/tag/v1.1.0
[1.0.3]: https://github.com/OddlyCrusty/omakeybinds/releases/tag/v1.0.3
[1.0.2]: https://github.com/OddlyCrusty/omakeybinds/releases/tag/v1.0.2
[1.0.1]: https://github.com/OddlyCrusty/omakeybinds/releases/tag/v1.0.1
[1.0.0]: https://github.com/OddlyCrusty/omakeybinds/releases/tag/v1.0.0
