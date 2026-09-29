#!/usr/bin/env python3
"""Remove only the managed block, preserving all other bytes and symlinks."""
import json

from shortcut_store import BINDINGS, STATE, mutation_lock, replace_block, transaction, read_text


def without_managed_block(source: str) -> str:
    return replace_block(source, "")


def main() -> int:
    try:
        with mutation_lock(STATE):
            original = read_text(BINDINGS)
            backups = transaction(BINDINGS, STATE, original, without_managed_block(original), None)
        print(json.dumps({"ok": True, "message": "Managed overrides removed; other personal bindings preserved.", **backups}))
        return 0
    except (OSError, ValueError, UnicodeError):
        print(json.dumps({"ok": False, "message": "Cleanup could not complete safely. Check configuration and backups before retrying."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
