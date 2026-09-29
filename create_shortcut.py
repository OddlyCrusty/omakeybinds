#!/usr/bin/env python3
"""Prepare or create a shortcut; private action data is accepted only on stdin."""
from __future__ import annotations

import json
import re
import sys
import uuid

import scan_shortcuts as scanner
from shortcut_actions import prepare
from shortcut_model import display_key, normalize_key
from shortcut_store import BINDINGS, STATE, digest, mutation_lock, replace_block, transaction
from update_shortcut import managed_block, upsert_override


def read_request() -> dict:
    raw = sys.stdin.read(32769)
    try:
        if len(raw) > 32768:
            raise ValueError()
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError()
        fields = {"operation", "target"}
        if request.get("operation") == "create":
            fields |= {"snapshot", "token", "new_key", "replace"}
            if type(request.get("replace")) is not bool:
                raise ValueError()
            for key in ("snapshot", "token"):
                if not isinstance(request.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", request[key]):
                    raise ValueError()
            if not isinstance(request.get("new_key"), str):
                raise ValueError()
            request["new_key"] = normalize_key(request["new_key"])
        elif request.get("operation") != "prepare":
            raise ValueError()
        if set(request) != fields:
            raise ValueError()
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ValueError("Could not read the new shortcut request.") from error
    return request


def apply_request(request: dict) -> dict:
    prepared = prepare(request["target"])
    if request["operation"] == "prepare":
        return {"ok": True, **{k: v for k, v in prepared.items() if k != "spec"}}
    if prepared["token"] != request["token"]:
        raise ValueError("The action or app launcher changed. Go back and review it again.")
    with mutation_lock(STATE):
        current, original, overrides = scanner.snapshot()
        if current["error"] or request["snapshot"] != current["snapshot"]:
            raise ValueError("Live bindings are unavailable or changed. Cancel, rescan, and try again.")
        key = normalize_key(request["new_key"])
        conflicts = [item for item in current["items"] if not item["disabled"]
                     and (item["key"] == key or display_key(item["key"]) == display_key(key))]
        if conflicts and not request["replace"]:
            raise ValueError("The selected key is occupied. Choose another key or explicitly confirm replacement.")
        if any(not item["editable"] or item["key"] != key for item in conflicts):
            raise ValueError("This key has a read-only or physical-key conflict. Choose another combination.")
        entry = {"id": uuid.uuid4().hex, "original_key": key, "current_key": key,
                 "description": prepared["description"], "kind": "custom", "created": True,
                 "previous": "; ".join(item["description"] for item in conflicts), **prepared["spec"]}
        overrides = upsert_override(overrides, entry)
        block = managed_block(overrides)
        state = {"version": 2, "overrides": overrides, "block_digest": digest(block)}
        backups = transaction(BINDINGS, STATE, original, replace_block(original, block), state)
        return {"ok": True, "message": "Shortcut added.", **backups}


def main() -> int:
    try:
        result = apply_request(read_request())
    except UnicodeError:
        result = {"ok": False, "message": "Unsupported text encoding. No shortcut was added."}
    except ValueError as error:
        result = {"ok": False, "message": str(error)}
    except (OSError, RecursionError):
        result = {"ok": False, "message": "Could not safely access the launcher or shortcut configuration."}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
