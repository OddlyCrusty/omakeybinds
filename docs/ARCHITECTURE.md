# Architecture

OmaKeybinds is an Omarchy Shell bar-widget plugin. It has no daemon and performs
work only while its panel is used.

## Components

- `BarWidget.qml` integrates the icon and popup with Omarchy Shell.
- `Panel.qml` provides search, filtering, editing, conflict confirmation, and
  settings UI.
- `AddShortcut.qml` provides a two-step action picker and shortcut review.
- `OmaKeybindsLogo.qml` draws the theme-aware taskbar mark without external
  assets.
- `scan_shortcuts.py` parses Omarchy defaults and user bindings, consults the
  live `hyprctl` metadata when available, and emits one JSON document.
- `update_shortcut.py` writes the managed override block transactionally.
- `shortcut_actions.py` discovers XDG desktop entries and prepares literal
  launch commands without executing them. App IDs go through `uwsm-app`;
  folders and websites use `xdg-open` with shell-quoted arguments.
- `create_shortcut.py` accepts prepare/create requests on stdin, rechecks the
  prepared action and live snapshot, and creates a new managed binding through
  the same transaction used by edits.
- `shortcut_model.py` lexes Lua without evaluation, handles literal escaping,
  preserves canonical keys, and accepts only supported binding specifications.
- `shortcut_store.py` validates state and block identity, coordinates the shared
  lock, and implements unique backups, atomic file writes, and rollback.
- `reset_shortcuts.py` restores the installed default bindings through the same
  transaction mechanism as normal edits.
- `remove_overrides.py` removes only OmaKeybinds-managed data for clean
  uninstallation.

## Data flow

1. Opening or refreshing the panel starts the scanner as a short-lived process.
2. The scanner reads Omarchy defaults, `bindings.lua`, direct `hyprctl` metadata, and
   OmaKeybinds state, then returns classified JSON over standard output.
3. The QML panel searches and filters this in memory.
4. An accepted edit, confirmed deletion, or restoration starts the updater
   with an opaque selection token, snapshot identity, destination key, operation,
   and replacement consent as JSON on standard input. The helper reconstructs
   the binding from a fresh snapshot and verifies consent and editability.
   The updater creates backups, atomically replaces
   its marked block, reloads Hyprland, validates, and either saves state or
   rolls back.
5. Creating a shortcut first prepares a typed target (app ID, URL, folder, or
   custom command) without writes. The UI reviews the command and sends its
   preparation token plus the target, snapshot, key, and replacement consent
   on stdin. Creation reconstructs the action and checks these identities before
   writing. Desktop launcher content changes invalidate the preparation token.
   The preparation token covers the action, not its display name: the review
   page may rename the shortcut without altering the approved command. Names
   are still validated and escaped by the backend.

Neither the UI nor scanner evaluates shortcut commands or user Lua. Only
unambiguous supported actions are rewritten; local functions and dynamic
expressions remain read-only. The generated block unbinds every affected key
before adding active bindings, preserving call type and options.

State version 2 records the full binding specification and managed-block hash.
Version 1 is reconstructed from an unambiguous original source binding or
refused. Backups retain the previous state. A missing, malformed, or mismatched
state file is never treated as permission to discard the existing block.
