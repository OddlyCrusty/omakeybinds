#!/usr/bin/env python3
"""Restore shipped bindings with the same backup/rollback guarantees as edits."""
import json
import os
from pathlib import Path

from shortcut_store import BINDINGS, STATE, mutation_lock, transaction, read_text

DEFAULT_BINDINGS = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "config/hypr/bindings.lua"


def main() -> int:
    try:
        with mutation_lock(STATE):
            original = read_text(BINDINGS)
            defaults = read_text(DEFAULT_BINDINGS)
            backups = transaction(BINDINGS, STATE, original, defaults, None)
        print(json.dumps({"ok": True, "message": "All shortcuts were reset to the current Omarchy defaults.", **backups}))
        return 0
    except (OSError, ValueError, UnicodeError):
        print(json.dumps({"ok": False, "message": "Reset could not complete safely. Check configuration and backups before retrying."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
