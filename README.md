<div align="center">
  <img src="assets/omakeybinds.svg" width="112" height="112" alt="OmaKeybinds logo">
  <h1>OmaKeybinds</h1>
  <p>A taskbar shortcut browser and safe keybinding editor for Omarchy.</p>
</div>

![OmaKeybinds shortcut browser showing category filters and changed shortcuts](preview.png)

OmaKeybinds is a native Omarchy Shell plugin that puts the keyboard shortcuts
you actually use in one searchable interface. It compares the current Hyprland
configuration with the defaults shipped by your installed Omarchy version, so
you can see what is standard, what changed, and what you added yourself.

## Features

- Theme-aware taskbar icon and popup designed for Omarchy Shell.
- Search by key combination, action, command, or source.
- Filters for **Default**, **Changed**, **Custom**, and **Deleted** shortcuts.
- A `✦` marker on changed and custom entries.
- In-place shortcut editing with key capture.
- Guided creation for installed apps, websites, folders, and custom commands.
- Search installed app names and icons without knowing executable names.
- Two-step shortcut deletion from the shortcut editor.
- Conflict warnings that name the actions already using a key; replacement
  requires explicit confirmation.
- A settings menu with a separately confirmed reset to current Omarchy defaults.
- Unique private backups, Hyprland validation, and rollback for edits, reset, and cleanup.
- No telemetry, accounts, network calls, or background service.

## Runtime dependencies

- A current Omarchy installation with Omarchy Shell plugin support.
- Hyprland and the `hyprctl` command.
- Quickshell with `ShortcutInhibitor` support and a compositor that grants
  Wayland keyboard-shortcut inhibition (included in the tested Omarchy setup).
- Python 3.10 or newer.
- Omarchy's existing `uwsm-app` launcher for apps and `xdg-open` for websites/folders.

OmaKeybinds uses only Python's standard library. It does not download code or
require any additional Python, system, or AUR packages.

## Install

```bash
omarchy plugin add https://github.com/OddlyCrusty/omakeybinds.git --enable
```

The widget defaults to the right side of the bar. If it is installed but not
visible, enable it explicitly:

```bash
omarchy plugin enable io.github.oddlycrusty.omakeybinds --section right
```

Open OmaKeybinds by selecting its **O keycap** icon in the taskbar.

## Use

The colored count buttons and the **Show** menu select a category. Search is
applied inside the selected category. Keyboard controls are available while the
popup is open:

| Key | Action |
| --- | --- |
| `/` | Focus search |
| `1`–`5` | Show All, Default, Changed, Custom, or Deleted |
| `R` | Rescan shortcuts |
| `Esc` | Close the current dialog or popup |

The categories mean:

- **Default** — active and unchanged from your installed Omarchy defaults.
- **Changed** — a default key now performs another action, or an action moved.
- **Custom** — an active user binding that has no default counterpart.
- **Deleted** — an inactive default or custom action retained for restoration,
  including actions whose former key is now used by something else. A deleted
  entry does not itself reserve that key.

### Add a shortcut

Select **+ Add**, then choose an action:

- **Installed app:** search by name and click its launcher (or use Up/Down and
  Enter) to continue directly to key capture. The launcher ID is passed to
  `uwsm-app`, which handles its
  arguments, working directory, and terminal behavior; OmaKeybinds never copies
  or guesses the app's `Exec` command.
- **Website:** enter a full `https://` or `http://` address. It opens in your
  default browser. Embedded credentials and other URL schemes are rejected.
- **Folder:** use **Choose folder…** or enter an existing absolute/`~/` path.
  It opens in your default file manager.
- **Custom command:** enter a single-line shell command you understand. Shell
  operators are allowed, and it runs with your user permissions when pressed.

Apps advance automatically when selected; other actions use **Continue**.
Record the key combination, or use **Type a combination instead**. Optionally
change the **Shortcut name**, inspect **Command details**, then select **Save
shortcut**. The plugin does not deliberately launch the action during review
or saving; see the [capture limitation](#known-capture-limitation) below before
pressing an existing global shortcut. This version has no test-launch button. A conflicting key
requires explicit replacement consent. Read-only, ambiguous, or physical-key
alias conflicts require choosing a different combination.

New shortcuts appear under **Custom**, labeled **Added by you**. They use the
same edit, delete, restore, backup, and rollback mechanisms as other managed
shortcuts. The installed launcher and live bindings are checked again before
saving. If either changes, go back to review or cancel and rescan.

App discovery follows XDG data-directory precedence and respects hidden entries,
desktop visibility, locale, and `TryExec`. Invalid or ambiguous launcher IDs,
IDs unsupported by this picker (including spaces/action suffixes), and entries
without an `Exec` line are omitted. Use a custom command for unsupported apps.
Removing an app later can make its saved shortcut stop launching it; the plugin
does not install missing apps or continuously monitor their availability.

### Change a shortcut

Select an editable row, record or type the new combination, then select **Apply
shortcut**. When the key is already used, OmaKeybinds lists the conflicting
actions and keeps Apply blocked until you acknowledge the replacement.

Some multi-action or dynamically generated bindings are displayed but are not
editable. This prevents one edit from silently removing sibling actions bound
to the same key. Bindings that depend on local Lua functions, unsupported
expressions, or submaps are also read-only. Each such row explains why. When
live compositor metadata is unavailable, the source estimate is read-only.

Supported edits preserve the original `o.bind`/`o.bind_toggle` call, options
such as repeat/release/locked behavior, and raw `code:` and mouse identifiers.
The helper rechecks the selection and conflicts immediately before writing;
if bindings changed since opening the editor, cancel and rescan first.

During an edit dialog or the Add dialog's key-capture step, OmaKeybinds retains
exclusive keyboard focus and requests temporary shortcut inhibition to prevent
an occupied combination from launching its existing action. Closing the dialog or panel releases the
request. Wait until the capture box is ready before pressing keys. If protection
is unavailable, the UI shows a warning and refuses to record keys. Compositor
emergency shortcuts or explicitly inhibition-bypassing bindings may still run.

Both dialogs also offer **Type a combination instead**. Type names such as
`SUPER + CTRL + SHIFT + D` normally, without holding those modifier keys.
This works without chord recording and shows the same live-view conflicts.
Deleted entries do not occupy keys. An occupied restore destination requires
another combination; restoring never replaces its current owner.

### Known capture limitation

A desktop-specific report remains unresolved: pressing an occupied combination
can launch its existing application instead of recording the keys and showing
the conflict. Full-editor isolated tests pass, including
`SUPER + CTRL + SHIFT + D`, but that does not prove the reported normal-desktop
failure is fixed.

If recording fails, the app launches, or the box says **Waiting for protected
capture**, stop trying the chord. Choose **Type a combination instead** and
type its names normally, such as `SUPER + CTRL + SHIFT + D`; do not hold those
keys together. The typed path uses the same conflict checks. Cancel and rescan
if bindings changed while the dialog was open.

For a bug report, include whether this happened in Add or Change, the capture
box message, reproduction steps, and your Omarchy/Hyprland/plugin versions.
Remove private commands, paths, and credentials from any logs or screenshots;
see [contributing](CONTRIBUTING.md).

### Delete a shortcut

Select an editable row, choose **Delete shortcut**, then choose **Confirm
delete**. The shortcut is safely unbound and remains available in the
**Deleted** filter so the change is easy to identify.

Select a shortcut in the **Deleted** view to restore it. OmaKeybinds proposes
its previous key combination. If that key is already occupied, restoration is
blocked and the dialog asks you to record or type a different combination.
For example, if deleted action A used `SUPER + J` and action B now uses it,
restore A to a free key such as `SUPER + K`. B keeps `SUPER + J`.

### Reset every shortcut

Open the cogwheel menu and choose **Reset all shortcuts**. This is intentionally
destructive: it restores `~/.config/hypr/bindings.lua` from the current Omarchy
defaults and removes custom, changed, and deleted shortcuts in that file. A
second confirmation is required. OmaKeybinds reads the defaults from the
installed Omarchy directory, creates unique backups of your bindings and state,
and rolls back the bindings if reload, validation, or state saving fails.
Reset affects the bindings file only; it does not change flags in `hyprland.lua`
or other separately included configuration files.

## Safety and files

Scanning reads source text and `hyprctl` metadata without executing Lua.
Editing writes one clearly marked managed block to
`~/.config/hypr/bindings.lua` and stores its small metadata file at
`~/.config/omarchy/omakeybinds-overrides.json`. Before an edit, the bindings
file is copied to a unique, owner-only `bindings.lua.bak.omakeybinds-*` file.
`XDG_CONFIG_HOME` is respected when set, and symlinks are preserved by updating
their resolved file targets. Operations share a lock to prevent overlapping writes.

After every edit OmaKeybinds reloads Hyprland and checks `hyprctl configerrors`.
If validation fails, the original bindings file is restored automatically. See
[Safety and recovery](docs/SAFETY.md) for recovery commands and exact behavior.

### Omarchy updates and older OmaKeybinds state

OmaKeybinds does not patch `/usr`, packaged Omarchy files, or shell components.
It uses the installed shell interfaces and reads the installed defaults, so a
system update does not need to preserve plugin-specific system patches.
Unknown binding syntax or unavailable metadata disables editing rather than
guessing. Compatibility with future changes to Omarchy or Hyprland still needs
validation; there is no guarantee against every future API change.

Version 1.2.0 validates managed state against its block and records complete
binding specifications. Older state is reconstructed only when its original
binding is unambiguous and supported. If reconstruction fails, no edits are
made: restore a matching backup or use the documented managed-only cleanup,
then recreate the desired edits. Keep bindings and state backups together.

## Update

Read the [release notes](CHANGELOG.md) and capture limitation before updating.
In an interactive terminal, review and confirm the upstream changes:

```bash
omarchy plugin update io.github.oddlycrusty.omakeybinds
```

Add `--yes` only to skip that confirmation. If updating reports local changes,
back up and inspect the installed checkout; do not discard your changes just
to force an update. This also applies to locally installed development copies.

GitHub code and the marketplace-verified snapshot are different: current
Omarchy install/update commands fetch upstream HEAD, which can be newer than
the reviewed commit. A passing repository CI run is not marketplace approval.
Compare the installed commit with the snapshot linked on the
[marketplace listing](https://omarchyplugins.com/plugin.html?id=io.github.oddlycrusty.omakeybinds):

```bash
git -C ~/.config/omarchy/plugins/io.github.oddlycrusty.omakeybinds rev-parse HEAD
git -C ~/.config/omarchy/plugins/io.github.oddlycrusty.omakeybinds status --short
```

A dirty checkout also differs from its reported commit. See the marketplace's
[installation boundary](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/VERIFICATION.md#installation-boundary).
Updating a listing requires a separate exact-commit request; the current 1.2.0
request and publication status are tracked in
[#9280](https://github.com/omacom/omarchy-plugin-marketplace/issues/9280).

## Uninstall

Plugin removal does not implicitly change your personal keybindings. To first
remove only the block managed by OmaKeybinds while preserving all other custom
bindings, run this from the installed plugin directory:

```bash
cd ~/.config/omarchy/plugins/io.github.oddlycrusty.omakeybinds
python3 remove_overrides.py
omarchy plugin remove io.github.oddlycrusty.omakeybinds --yes
```

If you want to keep the bindings you changed with OmaKeybinds, skip the first
command and remove only the plugin.

## Development

From a local repository checkout, run the release checks:

```bash
cd omakeybinds
./scripts/check.sh
```

The check script compiles the Python helpers, runs the unit tests, validates the
manifest, and uses `omarchy plugin validate .` when Omarchy is available.
When Lua is available, tests also execute generated code with harmless stub
dispatchers. CI installs Lua so these tests are required there. When Qt's QML
linter and the installed Omarchy shell are available, QML imports and structure
are checked without changing the installation.
Architecture and data flow are documented in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Contributions are welcome; read
[CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.
The [1.2.0 work summary](docs/WORK_SUMMARY.md) records implementation details,
test coverage, and remaining manual checks.

## License

[MIT](LICENSE) © OddlyCrusty
