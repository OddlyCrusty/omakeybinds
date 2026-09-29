#!/usr/bin/env python3
"""Inspect source text and compositor metadata without executing Lua config."""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from shortcut_model import binding_spec, calls, display_key, literal_string, normalize_key, split_arguments, tokens
from shortcut_store import BINDINGS, STATE, block_span, check_block_state, digest, load_state, read_text

DEFAULT_DIR = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "default/hypr/bindings"
USER_BINDINGS = BINDINGS
HYPRLAND_CONFIG = BINDINGS.parent / "hyprland.lua"


@dataclass
class Binding:
    key: str
    description: str
    command: str = ""
    source: str = ""
    action: str = ""
    call: str = "o.bind"
    options: str = "{}"
    reason: str = ""
    runtime_flags: dict = field(default_factory=dict)

    def spec(self) -> dict[str, str]:
        if self.reason:
            raise ValueError(self.reason)
        return binding_spec(self.action, self.call, self.options)


def read(path: Path) -> str:
    try:
        return read_text(path)
    except FileNotFoundError:
        return ""


def operations(source: str, source_name: str) -> list[Binding | str]:
    result = []
    for name, body in calls(source, ("o.bind", "o.bind_toggle", "hl.unbind")):
        arguments = split_arguments(body)
        raw_key = literal_string(arguments[0]) if arguments else None
        if raw_key is None:
            continue
        try:
            key = normalize_key(raw_key)
        except ValueError:
            continue
        if name == "hl.unbind":
            if len(arguments) == 1:
                result.append(key)
            continue
        description = literal_string(arguments[1]) if len(arguments) > 1 else None
        if description is None:
            continue
        action = arguments[2] if len(arguments) >= 3 else ""
        options = arguments[3] if len(arguments) >= 4 else "{}"
        reason = ""
        try:
            if len(arguments) not in (3, 4):
                raise ValueError()
            binding_spec(action, name, options)
        except (ValueError, UnicodeError):
            reason = "This binding uses code that cannot be safely moved. Edit it in your configuration."
        preview = literal_string(action)
        result.append(Binding(key, description, (preview if preview is not None else action)[:180], source_name,
                              action, name, options, reason))
    return result


def parse_bindings(source: str, source_name: str) -> tuple[list[Binding], list[str]]:
    parsed = operations(source, source_name)
    return [x for x in parsed if isinstance(x, Binding)], [x for x in parsed if isinstance(x, str)]


def generated_defaults(source: str, source_name: str) -> list[Binding]:
    """Recognize shipped numeric-loop labels for comparison only, never editing.

    Discovery uses lexical calls, so examples in comments/strings are ignored.
    These templates do not evaluate Lua or invent a reusable action expression.
    """
    result = []
    templates = {
        '"Switch to workspace " .. workspace': ("SUPER", 10),
        '"Move window to workspace " .. workspace': ("SUPER + SHIFT", 10),
        '"Move window silently to workspace " .. workspace': ("SUPER + ALT + SHIFT", 10),
        '"Switch to group window " .. index': ("SUPER + ALT", 5),
        '"Bar panel " .. panel': ("SUPER + CTRL", 9),
    }
    for _, body in calls(source, ("o.bind",)):
        args = split_arguments(body)
        if len(args) < 3:
            continue
        description = " ".join(args[1].split())
        if description not in templates:
            continue
        # Only known default files use these comparison templates.
        if source_name not in ("tiling.lua", "utilities.lua"):
            continue
        modifiers, count = templates[description]
        label = literal_string(description.split(" .. ", 1)[0])
        for number in range(1, count + 1):
            result.append(Binding(normalize_key(f"{modifiers} + code:{number + 9}"), label + str(number),
                                  source=source_name, reason="This dynamically generated default is read-only."))
    return result


def default_bindings() -> list[Binding]:
    config_tokens = tokens(read(HYPRLAND_CONFIG))
    disabled = set()
    for index in range(len(config_tokens) - 2):
        a, b, c = config_tokens[index:index + 3]
        if a.kind == "name" and b.kind == "symbol" and b.value == "=" and c.kind == "name" and c.value == "false":
            disabled.add(a.value)
    if "omarchy_default_bindings" in disabled:
        return []
    result = []
    for path in sorted(DEFAULT_DIR.glob("*.lua")):
        source = read(path)
        if path.name == "applications.lua" and "omarchy_preinstalled_bindings" in disabled:
            source = source.split("if o.preinstalled_bindings_enabled()", 1)[0]
        parsed, _ = parse_bindings(source, path.name)
        result.extend(parsed)
        result.extend(generated_defaults(source, path.name))
    return result


def runtime_binding(record: dict) -> Binding:
    mask = int(record.get("modmask", 0))
    key = str(record.get("key", ""))
    keycode = int(record.get("keycode", 0))
    key = key.split(" + ")[-1] if key else (f"code:{keycode}" if keycode else "")
    mods = [name for name, bit in (("SUPER", 64), ("CTRL", 4), ("ALT", 8), ("SHIFT", 1)) if mask & bit]
    try:
        key = normalize_key(" + ".join(mods + [key]))
        reason = ""
    except ValueError:
        key = " + ".join(mods + [key or "UNKNOWN"])
        reason = "Hyprland did not report a usable key identity."
    if record.get("submap") or mask & ~77:
        reason = "Submap bindings and additional modifier types are read-only."
    return Binding(key, str(record.get("description", "")), source="Hyprland", reason=reason,
                   runtime_flags=record)


def current_runtime_bindings() -> list[Binding] | None:
    """None means unavailable; an empty list is a successful empty snapshot."""
    try:
        completed = subprocess.run(["hyprctl", "-j", "binds"], capture_output=True, text=True, timeout=5, check=False)
        if completed.returncode == 0:
            try:
                data = json.loads(completed.stdout)
                if (isinstance(data, list) and all(isinstance(item, dict) for item in data)
                        and all(item.get("key") or item.get("keycode") for item in data)):
                    return [runtime_binding(item) for item in data]
            except (ValueError, TypeError):
                pass
        completed = subprocess.run(["hyprctl", "binds"], capture_output=True, text=True, timeout=5, check=False)
        if completed.returncode:
            return None
        records = []
        record = None
        for line in completed.stdout.splitlines():
            if re.match(r"^bind\w*\s*$", line):
                record = {}
                records.append(record)
            elif record is not None and (match := re.match(r"^\s+([a-zA-Z_]+): ?(.*)$", line)):
                if match[1] in record:
                    return None
                record[match[1]] = match[2]
        if completed.stdout.strip() and not records:
            return None
        if any(not {"modmask", "key", "keycode", "description"}.issubset(item) for item in records):
            return None
        return [runtime_binding(item) for item in records]
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return None


def canonical_overrides(state: dict, originals: list[Binding]) -> list[dict]:
    result = []
    for saved in state["overrides"]:
        item = dict(saved)
        if state["version"] == 1:
            # Recover omitted v1 fields only from an unambiguous original.
            matches = [b for b in originals if b.description == item["description"] and
                       (b.key == item["original_key"] or display_key(b.key) == item["original_key"])]
            if len(matches) != 1:
                raise ValueError("Older overrides cannot be safely reconstructed. Remove managed overrides before editing.")
            original = matches[0]
            item.update(original.spec())
            if item["current_key"] == item["original_key"]:
                item["current_key"] = original.key
            item["original_key"] = original.key
        else:
            item.update(binding_spec(item["action"], item["call"], item["options"]))
        item["original_key"] = normalize_key(item["original_key"])
        item["current_key"] = normalize_key(item["current_key"])
        result.append(item)
    return result


def snapshot() -> tuple[dict, str, list[dict]]:
    source = read_text(USER_BINDINGS)
    defaults = default_bindings()
    span = block_span(source)
    personal_source = source if span is None else source[:span[0]] + source[span[1]:]
    personal, _ = parse_bindings(personal_source, USER_BINDINGS.name)
    state = load_state(STATE)
    check_block_state(source, state)
    overrides = canonical_overrides(state, defaults + personal)
    runtime = current_runtime_bindings()
    live = runtime is not None
    parsed = operations(source, USER_BINDINGS.name)
    custom = [item for item in parsed if isinstance(item, Binding)]
    unbound = [item for item in parsed if isinstance(item, str)]
    if runtime is None:
        active = list(defaults)
        for operation in parsed:
            if isinstance(operation, str):
                active = [b for b in active if b.key != operation]
            else:
                active.append(operation)
    else:
        active = runtime
    counts_by_key = Counter(item.key for item in active)
    output = []
    for item in active:
        candidates = [b for b in custom if (b.key, b.description) == (item.key, item.description)]
        if not candidates:
            candidates = [b for b in defaults if (b.key, b.description) == (item.key, item.description)]
        managed = next((m for m in overrides if m["current_key"] == item.key and m["description"] == item.description and m["kind"] != "deleted"), None)
        reason = item.reason
        spec = None
        if managed:
            spec = binding_spec(managed["action"], managed["call"], managed["options"])
        elif len(candidates) == 1:
            try:
                spec = candidates[0].spec()
            except ValueError:
                reason = candidates[0].reason
        else:
            reason = "The original action is dynamic, ambiguous, or unavailable. Edit it in your configuration."
        if counts_by_key[item.key] != 1:
            reason = "Multiple actions share this key; editing one could remove the others."
        if not live:
            reason = "Live keybindings are unavailable. This is a read-only source estimate."
        original = [b for b in defaults if b.key == item.key]
        status = "default" if any(b.description == item.description for b in original) else ("changed" if original else "custom")
        if any((b.key, b.description) == (item.key, item.description) for b in custom):
            status = "changed" if original else "custom"
        if managed:
            status = managed["kind"]
        row = {
            "key": item.key, "displayKey": display_key(item.key), "description": item.description,
            "command": candidates[0].command if len(candidates) == 1 else "", "source": candidates[0].source if len(candidates) == 1 else "Hyprland",
            "status": status, "previous": managed.get("previous", "") if managed else "; ".join(b.description for b in original) if status == "changed" else "",
            "disabled": False, "editable": spec is not None and not reason, "reason": reason,
            "overrideId": managed["id"] if managed else "", "originKey": managed["original_key"] if managed else item.key,
            "restoreKind": "", "spec": spec,
            "created": managed.get("created", False) if managed else False,
        }
        output.append(row)
    for managed in overrides:
        if managed["kind"] != "deleted":
            continue
        output.append({
            "key": managed["current_key"], "displayKey": display_key(managed["current_key"]), "description": managed["description"],
            "command": "", "source": USER_BINDINGS.name, "status": "deleted", "previous": managed.get("previous", ""),
            "disabled": True, "editable": live, "reason": "" if live else "Live keybindings are unavailable; restoration is disabled.",
            "overrideId": managed["id"], "originKey": managed["original_key"], "restoreKind": managed.get("previous_kind", "changed"),
            "spec": binding_spec(managed["action"], managed["call"], managed["options"]),
            "created": managed.get("created", False),
        })
    for key in dict.fromkeys(unbound):
        # A reused key does not resurrect its previous action. Keep that
        # action available for restoration, but do not duplicate actions
        # already represented by a live row or a managed move/tombstone.
        originals = [b for b in defaults + personal if b.key == key
                     and not any(a.key == key and a.description == b.description for a in active)
                     and not any(key in (m["original_key"], m["current_key"])
                                 and m["description"] == b.description for m in overrides)]
        spec = None
        if len(originals) == 1:
            try:
                spec = originals[0].spec()
            except ValueError:
                pass
        if not originals:
            continue
        output.append({
            "key": key, "displayKey": display_key(key), "description": originals[0].description if len(originals) == 1 else "Deleted",
            "command": "", "source": USER_BINDINGS.name, "status": "deleted", "previous": "; ".join(b.description for b in originals),
            "disabled": True, "editable": live and spec is not None, "reason": "" if live and spec else "This deleted action cannot be safely reconstructed.",
            "overrideId": "", "originKey": key, "restoreKind": "default" if originals[0] in defaults else "custom", "spec": spec,
        })
    priority = {"deleted": 0, "changed": 1, "custom": 2, "default": 3}
    output.sort(key=lambda item: (priority[item["status"]], item["key"], item["description"]))
    for row in output:
        row["token"] = digest(json.dumps(row, sort_keys=True, ensure_ascii=False))
    counts = {kind: sum(row["status"] == kind for row in output) for kind in priority}
    counts["all"] = len(output)
    revision = digest(json.dumps([source, state, [vars(b) for b in defaults], [vars(b) for b in runtime] if live else None], sort_keys=True, ensure_ascii=False))
    result = {"items": output, "counts": counts, "snapshot": revision,
              "error": "" if live else "Live keybindings are unavailable. Showing a read-only source estimate."}
    return result, source, overrides


def build() -> dict:
    try:
        result, _, _ = snapshot()
        for row in result["items"]:
            row.pop("spec", None)
        return result
    except (OSError, ValueError, UnicodeError, RecursionError):
        return {"items": [], "counts": {"all": 0, "default": 0, "changed": 0, "custom": 0, "deleted": 0},
                "snapshot": "", "error": "Could not safely read bindings or managed state. Check the configuration and restore a backup or remove managed overrides if necessary."}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, separators=(",", ":")))
