#!/usr/bin/env python3
"""Reset user keybindings through Omarchy's supported refresh command."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
STATE = CONFIG_HOME / "omarchy/omakeybinds-overrides.json"


def run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def main() -> int:
    try:
        refreshed = run(["omarchy", "refresh", "config", "hypr/bindings.lua"])
    except (OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"ok": False, "message": f"Reset could not start: {error}"}))
        return 1
    if refreshed.returncode != 0:
        message = refreshed.stderr.strip() or refreshed.stdout.strip() or "Omarchy could not reset bindings.lua."
        print(json.dumps({"ok": False, "message": message}))
        return 1

    state_backup = ""
    if STATE.exists():
        state_backup_path = STATE.with_name(STATE.name + ".bak." + datetime.now().strftime("%Y%m%d%H%M%S"))
        shutil.copy2(STATE, state_backup_path)
        STATE.unlink()
        state_backup = str(state_backup_path)

    try:
        reloaded = run(["hyprctl", "reload"], timeout=8)
        checked = run(["hyprctl", "configerrors"], timeout=8)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"ok": False, "message": f"Defaults were restored, but validation could not run: {error}"}))
        return 1

    errors = checked.stdout.strip() or checked.stderr.strip()
    if reloaded.returncode != 0 or checked.returncode != 0 or errors:
        message = errors or reloaded.stderr.strip() or "Hyprland did not accept the refreshed configuration."
        print(json.dumps({"ok": False, "message": f"Defaults were restored, but validation reported: {message}"}))
        return 1

    print(json.dumps({
        "ok": True,
        "message": "All shortcuts were reset to the current Omarchy defaults.",
        "stateBackup": state_backup,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
