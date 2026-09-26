# Safety and recovery

OmaKeybinds changes keybindings conservatively, but keybinding configuration is
still user data. Keep normal backups of `~/.config/hypr`.

## Managed edits

Every GUI edit:

1. Copies `bindings.lua` to `bindings.lua.bak.omakeybinds-<timestamp>`.
2. Atomically replaces only the block between the OmaKeybinds marker comments.
3. Runs `hyprctl reload` and `hyprctl configerrors`.
4. Restores the backup if reload or validation fails.

The **Reset all shortcuts** action is different: it deliberately invokes
`omarchy refresh config hypr/bindings.lua`, which restores the entire file from
the installed Omarchy defaults. The UI warns about this and requires a second
confirmation.

## Remove only OmaKeybinds edits

From the installed plugin directory, run:

```bash
python3 remove_overrides.py
```

This keeps unrelated personal content in `bindings.lua`, backs up the file,
removes only the marked block and state file, then validates Hyprland.

## Manual recovery

List available backups:

```bash
ls -1t ~/.config/hypr/bindings.lua.bak.omakeybinds-*
```

To restore one, copy the selected file over `~/.config/hypr/bindings.lua` and
run `hyprctl reload`. Inspect the backup before restoring it; the newest file is
not always the one you want.
