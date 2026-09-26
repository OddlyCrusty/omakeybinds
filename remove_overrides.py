#!/usr/bin/env python3
"""Remove only the keybinding block managed by OmaKeybinds."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime

from update_shortcut import BEGIN, BINDINGS, END, STATE, atomic_write, hyprctl


def without_managed_block(source: str) -> str:
    pattern = re.compile(r"\n?" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
    return pattern.sub("\n", source).rstrip() + "\n"


def main() -> int:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    try:
        original = BINDINGS.read_text(encoding="utf-8")
    except OSError as error:
        print(json.dumps({"ok": False, "message": f"Could not read bindings.lua: {error}"}))
        return 1

    cleaned = without_managed_block(original)
    bindings_backup = ""
    state_backup = ""
    try:
        if cleaned != original:
            backup = BINDINGS.with_name(BINDINGS.name + ".bak.omakeybinds-cleanup-" + timestamp)
            shutil.copy2(BINDINGS, backup)
            bindings_backup = str(backup)
            atomic_write(BINDINGS, cleaned)

            reloaded = hyprctl("reload")
            checked = hyprctl("configerrors")
            errors = checked.stdout.strip() or checked.stderr.strip()
            if reloaded.returncode != 0 or checked.returncode != 0 or errors:
                raise RuntimeError(errors or reloaded.stderr.strip() or "Hyprland rejected the cleaned configuration")

        if STATE.exists():
            backup = STATE.with_name(STATE.name + ".bak." + timestamp)
            shutil.copy2(STATE, backup)
            STATE.unlink()
            state_backup = str(backup)
    except Exception as error:
        if bindings_backup:
            shutil.copy2(bindings_backup, BINDINGS)
            try:
                hyprctl("reload")
            except Exception:
                pass
        print(json.dumps({"ok": False, "message": f"Cleanup rolled back: {error}"}))
        return 1

    print(json.dumps({
        "ok": True,
        "message": "OmaKeybinds-managed overrides were removed; other personal bindings were preserved.",
        "bindingsBackup": bindings_backup,
        "stateBackup": state_backup,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
