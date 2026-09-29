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
The [known desktop capture limitation](../README.md#known-capture-limitation)
is not conclusively resolved. Use **Type a combination instead** if capture
is unavailable or a chord launches its existing action.

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
cd ~/.config/omarchy/plugins/io.github.oddlycrusty.omakeybinds
python3 remove_overrides.py
```

This keeps unrelated personal content in `bindings.lua`, backs up bindings and
state, removes only the marked block, validates Hyprland, then writes empty
managed state. Empty state preserves symlinks and contains no saved commands.
Cleanup can recover from malformed state without trying to interpret it.
Ambiguous or incomplete block markers require manual recovery.

## Manual recovery

Close the plugin and stop other configuration editors before recovery. Keep
separate copies of the current bindings and state first, even if they appear
broken. Recovery replaces the selected files and can undo later edits.

### Find both backups

Bindings and state backups live beside their **resolved file targets**. With
ordinary files these are under `~/.config/hypr` and `~/.config/omarchy`; with
symlinks they may be inside your dotfiles repository. These read-only commands
respect `XDG_CONFIG_HOME` and locate both sets:

```bash
omak_config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
omak_bindings_target=$(readlink -f -- "$omak_config_root/hypr/bindings.lua")
omak_state_target=$(readlink -f -- "$omak_config_root/omarchy/omakeybinds-overrides.json")
ls -lt -- "${omak_bindings_target}.bak.omakeybinds-"*
ls -lt -- "${omak_state_target}.bak.omakeybinds-"*
```

Stop if a target cannot be resolved; investigate the missing file or broken
symlink first. `ls` reports no match when no backups exist for a target.
Backup suffixes are independently generated random values, **not matching pair
IDs**. Modification times help find candidates, but do not prove a match.
Successful helper responses identify their pair as `backup` and `stateBackup`;
the GUI does not provide a backup-history browser.

### Check that the state belongs to the bindings

For version-2 state, the stored `block_digest` must match the exact managed
block in the candidate bindings. From the installed plugin directory, replace
both placeholder paths below with the chosen backups. This check reads files
only; it does not restore them, execute Lua, or reload Hyprland:

```bash
python3 - /absolute/path/to/bindings-backup /absolute/path/to/state-backup <<'PY'
import sys
from pathlib import Path
from shortcut_store import check_block_state, load_state, read_text

bindings_path, state_path = map(Path, sys.argv[1:3])
if not bindings_path.is_file() or not state_path.is_file():
    raise SystemExit('Select two existing backup files; nothing has been restored.')
state = load_state(state_path)
if state['version'] != 2:
    raise SystemExit('Legacy state has no version-2 fingerprint; inspect the original backup pair manually.')
check_block_state(read_text(bindings_path), state)
print('Managed block and state are consistent. Review the rest of the bindings before restoring.')
PY
```

Matching the managed block does not validate unrelated Lua or prove the two
files came from the same operation. Review the remaining contents locally;
backups can contain private commands. Legacy version-1 state needs manual
comparison with its original bindings, not a guessed fingerprint.

If state did not exist before an operation, there is no state backup. Restore
that earlier state only after confirming its bindings contain no managed block;
preserve the current state separately rather than leaving incompatible metadata
beside those bindings. If a managed block exists but no matching state can be
found, do not invent state or a hash: use matching external backups, seek help,
or deliberately choose the documented managed-only cleanup.

### Restore and validate

Once a pair is confirmed, copy the selected backups over the two resolved
targets, preserving any configuration symlinks. Use explicit selected filenames,
not globs, and keep the backups. Then run:

```bash
hyprctl reload
hyprctl configerrors
```

Do not resume editing until reload succeeds and the configuration-error output
is empty. Reopen OmaKeybinds and rescan; a remaining state/block mismatch must
be resolved rather than bypassed. Failed operations can leave useful backups,
and the newest backup is not necessarily the one you want.

The lock serializes OmaKeybinds operations. External editors do not take that
lock; the helper checks for concurrent changes and does not overwrite a newer
bindings file detected during validation. A process crash or power loss between
the two file replacements is not a fully atomic transaction: a later scan
detects a block/state mismatch and refuses edits until recovery.

Configuration reloads execute the user's configuration in Hyprland. Rollback
restores files but cannot undo arbitrary side effects in existing user Lua.
Scanning itself does not execute that Lua. Error responses do not quote
configuration diagnostics that might contain credentials.
