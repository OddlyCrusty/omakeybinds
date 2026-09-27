# Architecture

OmaKeybinds is an Omarchy Shell bar-widget plugin. It has no daemon and performs
work only while its panel is used.

## Components

- `BarWidget.qml` integrates the icon and popup with Omarchy Shell.
- `Panel.qml` provides search, filtering, editing, conflict confirmation, and
  settings UI.
- `OmaKeybindsLogo.qml` draws the theme-aware taskbar mark without external
  assets.
- `scan_shortcuts.py` parses Omarchy defaults and user bindings, consults the
  live keybinding menu when available, and emits one JSON document.
- `update_shortcut.py` writes the managed override block transactionally.
- `reset_shortcuts.py` delegates a full reset to Omarchy's supported refresh
  command.
- `remove_overrides.py` removes only OmaKeybinds-managed data for clean
  uninstallation.

## Data flow

1. Opening or refreshing the panel starts the scanner as a short-lived process.
2. The scanner reads Omarchy defaults, `bindings.lua`, runtime bindings, and
   OmaKeybinds state, then returns classified JSON over standard output.
3. The QML panel searches and filters this in memory.
4. An accepted edit, confirmed deletion, or restoration starts the updater
   with a JSON request on standard input, keeping private commands out of
   process arguments. The updater creates a backup, atomically replaces
   its marked block, reloads Hyprland, validates, and either saves state or
   rolls back.

The UI never evaluates shortcut commands. Preserved Lua actions are written
back only for an existing parsed binding.
