# Safety and recovery

OmaKeybinds changes keybindings conservatively, but keybinding configuration is
still user data. Keep normal backups of `~/.config/hypr`.

## Managed edits

The focused add/edit window requests Wayland shortcut inhibition, not a global
unbind or a temporary Hyprland configuration change. The request exists only
while the panel and an edit/capture step are open. The layer surface keeps
exclusive keyboard focus during this step and returns to the shell's normal
focus policy afterward; the app/folder picker is not inhibited. Capture checks the compositor's active
acknowledgement and refuses recording if it is missing or revoked. The
compositor retains control over emergency/inhibition-bypassing shortcuts.
See the [Quickshell ShortcutInhibitor contract](https://quickshell.org/docs/v0.3.1/types/Quickshell.Wayland/ShortcutInhibitor/).

Every GUI edit or addition:

1. Acquires the shared mutation lock and checks the selected binding against a
   fresh source, state, and compositor snapshot. Stale selections are rejected.
2. Creates uniquely named, owner-only backups of bindings and existing state.
3. Atomically replaces only the managed block, preserving surrounding bytes and
   updating the resolved target when the bindings file is a symlink.
4. Runs `hyprctl reload` and `hyprctl configerrors`, then commits the new state.
5. Restores the original bindings if reload, validation, or state saving fails.

Malformed state, missing state for an existing managed block, or manual changes
to the managed block stop editing. Older state is migrated only when the source
binding can be reconstructed safely. Unsupported Lua is never evaluated to
discover actions. Description text and command escapes remain literal data.

New-shortcut preparation does not launch apps, run commands, or write bindings.
Creation rechecks its reviewed action and live snapshot. The app picker reads
desktop entries, never executes their `Exec` lines, and delegates launching to
Omarchy's `uwsm-app` when the saved shortcut is pressed. Desktop entries are
executable instructions provided by installed apps or the user, not a sandbox.
Only HTTP(S) websites and existing local folders are supported in the guided
openers; their arguments are shell-quoted. Custom commands deliberately permit
shell syntax and run with user permissions. They are sent over stdin, not in
helper process arguments, but are stored in bindings/state and backups just like
other shortcuts. Do not put secrets in a shortcut command.

**Reset all shortcuts** deliberately replaces the entire bindings file with
`$OMARCHY_PATH/config/hypr/bindings.lua` (default `/usr/share/omarchy`). It uses
the same backup, lock, validation, and rollback mechanism. The UI requires a
second confirmation. It does not edit `hyprland.lua` or other included files.
The configured `XDG_CONFIG_HOME` is used consistently for bindings and state.

## Remove only OmaKeybinds edits

From the installed plugin directory, run:

```bash
python3 remove_overrides.py
```

This keeps unrelated personal content in `bindings.lua`, backs up bindings and
state, removes only the marked block, validates Hyprland, then writes empty
managed state. Empty state preserves symlinks and contains no saved commands.
Cleanup can recover from malformed state without trying to interpret it.
Ambiguous or incomplete block markers require manual recovery.

## Manual recovery

List available backups:

```bash
ls -1t ~/.config/hypr/bindings.lua.bak.omakeybinds-*
```

To restore one, copy the selected file over your bindings file and restore its
matching state backup, then run `hyprctl reload`. Respect `XDG_CONFIG_HOME` if
set. Inspect the backups before restoring them; the newest is not always the
one you want. Failed operations may also leave useful backups.

The lock serializes OmaKeybinds operations. External editors do not take that
lock; the helper checks for concurrent changes and does not overwrite a newer
bindings file detected during validation. A process crash or power loss between
the two file replacements is not a fully atomic transaction: a later scan
detects a block/state mismatch and refuses edits until recovery.

Configuration reloads execute the user's configuration in Hyprland. Rollback
restores files but cannot undo arbitrary side effects in existing user Lua.
Scanning itself does not execute that Lua. Error responses do not quote
configuration diagnostics that might contain credentials.
