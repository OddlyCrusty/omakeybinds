# OmaKeybinds 1.2.0 work summary

This describes repository work from 2026-09-28 and the UI follow-up on
2026-09-29. A local test copy was installed at the user's request on September
28. The implementation was subsequently committed and pushed as `48ee608`.
Documentation-only follow-ups do not change its runtime behavior. GitHub
availability is separate from marketplace publication; the current target and
review/publication status are recorded in
[update request #9280](https://github.com/omacom/omarchy-plugin-marketplace/issues/9280).

## New shortcut creation

- Added a **+ Add** button and a two-step, theme-aware dialog.
- Search installed apps by name, icon, and launcher ID; no executable knowledge
  is needed. XDG precedence, hidden entries, locale, desktop visibility, and
  executable availability checks are respected.
- Delegate app launching to the existing `uwsm-app` desktop-entry interface
  instead of reconstructing launcher commands.
- Add HTTP(S) websites, existing folders (including a folder picker), or
  explicitly entered custom shell commands.
- Suggest descriptions and show the exact command before saving.
- Capture key combinations, explain conflicts, require explicit replacement
  consent, and refuse unsafe read-only/physical-key alias replacements.
- Warn about unmodified keys that could interfere with normal typing.
- Recheck the reviewed action, launcher content, and live shortcut snapshot
  before writing. Creation uses the same transaction as edits.
- Label created shortcuts **Added by you**; retain that identity through key
  edits, deletion, and restoration.
- Preview and saving do not deliberately launch the selected action. A
  test-launch button and curated Omarchy-action picker are not included.

## Audit and safety fixes carried into this version

The September 29 UI follow-up replaces generic controls with Omarchy's own
buttons, fields, toggles, and cursor surfaces. The dialog now sizes to its
content. Clicking an app or pressing Enter in search advances directly to
focused key capture; the second page supports renaming and expandable command
details. Errors stay visible beside the footer, including missing launchers.
The subsequent visual pass reduces outlined controls, adds app icon fallbacks
and readable keycaps, makes the save action prominent, and uses a disclosure
button instead of a settings toggle for command details. Both pages were
rendered and inspected; screenshot checks wait for theme transitions to settle.

- Keep requests on stdin rather than helper process arguments. Existing edits
  now send selection tokens instead of trusting commands supplied by the UI.
- Escape Lua strings correctly, preserve Unicode and backslashes, and stop
  descriptions from becoming executable Lua comments.
- Parse source without evaluating Lua or mistaking comments/strings for calls.
- Preserve toggle calls, supported binding options, and raw physical/mouse key
  identifiers. Local helpers, ambiguous multi-action bindings, submaps, and
  unsupported expressions remain read-only with explanations.
- Unbind all affected keys before adding managed bindings so moving one does
  not remove another that reused its previous key.
- Preserve displaced managed bindings as restorable deleted entries.
- Read live metadata directly from `hyprctl`; handle small/empty results and
  use a defensive plain-text fallback when JSON loses key identities. Source
  fallback is read-only and preserves bind/unbind ordering.
- Validate managed state and its block fingerprint, reject stale snapshots,
  and recover legacy state only when its original binding is unambiguous.
- Serialize mutation helpers with a shared lock. Use unique private backups,
  atomic replacements, and rollback on reload, validation, or state-save failure.
- Preserve configuration symlinks, unrelated file bytes/line endings, and
  honor `XDG_CONFIG_HOME` consistently.
- Give reset and managed-only cleanup the same transaction protections.
- Improve rescan sequencing, repeated stdin handoff, and saving-state guards.

## Verification

- The complete local release check passes: 82 tests with the opt-in live
  protocol test enabled, Python
  compilation, manifest checks, QML imports/structure, native Omarchy plugin
  validation, and whitespace checks.
- Tests cover the audit regressions, harmless Lua execution through stub
  dispatchers, transaction failures and rollback, creation lifecycle, app
  discovery, URL/path quoting, stale requests, and malformed input.
- The real new dialog was exercised in an isolated, headless Quickshell
  process: prepare, capture, conflict consent, and save transport. Its helper
  was harmless and performed no real configuration writes or launches.
- The actual complete Panel component compiles against the installed shell.
- The review dialog was visually inspected and its dark-theme contrast fixed.
- Read-only discovery found 57 launchers on the test machine, including three
  terminal launchers. No app was launched to test this feature.
- QML still reports advisory warnings, largely from dynamic shell properties;
  these are not represented as a warning-free lint result.
- The occupied Super+Ctrl+Shift+D regression is covered in both editors. A
  separate opt-in test (`OMAKEYBINDS_WAYLAND_SMOKE=1 ./scripts/check.sh`)
  confirms shortcut inhibition activates and releases for both dialog states.
  It now also instantiates the complete editor and sends real Wayland keys
  through both dialogs, checking occupied/deleted keys, typed input, and the
  restore prompt. Save helpers are absent from this fixture. The default live
  chord uses F35; a separate opt-in run exercised Super+Ctrl+Shift+D.

## Follow-up: reused keys and capture troubleshooting

- Keep deleted source-defined actions visible after another action reuses
  their old key; they do not count as occupied keys.
- Refuse restoration onto an occupied key even if a replacement flag is sent.
  Prompt for another combination, preserving the current owner.
- Preserve the old key's unrelated owner when restoring a source-defined
  deletion elsewhere, including subsequent edits/deletes/restores.
- Show an explicit available/current-key hint, and report unnamed bindings
  as conflicts rather than displaying an empty warning.
- Add an Omarchy-styled **Type a combination instead** option to both dialogs.
  This checks conflicts without requiring the user to press a global chord.
- Refocus the existing editor when compositor capture protection activates;
  distinguish a focused recording box from one that needs clicking.
- The previously reported failure has not reproduced in the complete isolated
  editor, including the actual D combination. Passing those tests does not
  establish that the user's normal-shell reproduction is resolved; it still
  needs a user retest after deployment/restart.

## Omarchy compatibility and remaining limits

No files in `/usr` were changed. Development and tests wrote only the repository
and temporary files. The user subsequently requested a local plugin install
and shell restart, which were performed with the previous plugin backed up;
their actual keybindings were not changed. The Omarchy skill informed use of the
user configuration layer, packaged interfaces, and post-write validation; no
system patches, local package installs, or Hyprland reloads were needed for this
development work. The CI workflow installs Lua on its disposable GitHub runner,
not on the user's machine.

The implementation uses current installed interfaces and reads installed
defaults. It cannot guarantee compatibility with every future Omarchy or
Hyprland update. Unsupported cases are refused rather than guessed.

The picker deliberately omits unsupported/ambiguous desktop IDs and entries
without `Exec`. Uninstalling an app later can invalidate its saved shortcut.
There is no continuous availability monitor. Guided openers do not sandbox
applications, and custom commands deliberately allow shell execution when the
shortcut is pressed.

No end-to-end save was performed against the user's actual desktop. Mutation
tests use temporary fixtures with simulated compositor validation. The folder
picker's native portal interaction and actual launches still merit a manual
smoke test after an explicitly chosen installation/update.

Two files (bindings and state) cannot be replaced as one crash-proof operation.
The plugin detects a later mismatch, but a power loss can require recovery.
External editors do not honor the plugin lock. Configuration reloads execute
the user's existing Lua, whose arbitrary side effects cannot be rolled back.
See [Safety and recovery](SAFETY.md) for details.

README, changelog, architecture, safety documentation, manifest, and release
checks were updated along with the implementation. The previous v1.1.1 GitHub
review and validation do not certify later commits. Marketplace reports apply
only to their explicitly recorded SHA, not automatically to newer GitHub code.
