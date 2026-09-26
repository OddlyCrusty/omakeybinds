#!/usr/bin/env python3
"""Build a classified view of Omarchy/Hyprland shortcuts."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DIR = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "default/hypr/bindings"
HYPR_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "hypr"
USER_BINDINGS = HYPR_DIR / "bindings.lua"
HYPRLAND_CONFIG = HYPR_DIR / "hyprland.lua"

KEY_NAMES = {
    "code:10": "1", "code:11": "2", "code:12": "3", "code:13": "4",
    "code:14": "5", "code:15": "6", "code:16": "7", "code:17": "8",
    "code:18": "9", "code:19": "0", "code:20": "MINUS", "code:21": "EQUAL",
    "code:59": "COMMA", "code:60": "PERIOD", "code:61": "SLASH",
    "mouse:272": "LEFT MOUSE BUTTON", "mouse:273": "RIGHT MOUSE BUTTON",
    "mouse:274": "MIDDLE MOUSE BUTTON", "mouse_down": "MOUSE WHEEL DOWN",
    "mouse_up": "MOUSE WHEEL UP",
}


@dataclass
class Binding:
    key: str
    description: str
    command: str = ""
    source: str = ""
    action: str = ""


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def lua_strings(text: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r'(["\'])(.*?)(?<!\\)\1', text, re.S):
        raw = match.group(2)
        values.append(bytes(raw, "utf-8").decode("unicode_escape"))
    return values


def split_arguments(body: str) -> list[str]:
    """Split a Lua argument list at top-level commas."""
    result: list[str] = []
    start = 0
    depths = {"(": 0, "{": 0, "[": 0}
    pairs = {")": "(", "}": "{", "]": "["}
    quote = ""
    escaped = False
    for index, char in enumerate(body):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in depths:
            depths[char] += 1
        elif char in pairs:
            depths[pairs[char]] = max(0, depths[pairs[char]] - 1)
        elif char == "," and not any(depths.values()):
            result.append(body[start:index].strip())
            start = index + 1
    result.append(body[start:].strip())
    return result


def literal_string(argument: str) -> str | None:
    match = re.fullmatch(r'(["\'])(.*?)(?<!\\)\1', argument.strip(), re.S)
    if not match:
        return None
    return bytes(match.group(2), "utf-8").decode("unicode_escape")


def calls(source: str, names: tuple[str, ...]) -> list[tuple[str, str]]:
    """Extract balanced Lua calls while respecting strings and comments."""
    pattern = re.compile(r"\b(" + "|".join(re.escape(name) for name in names) + r")\s*\(")
    found: list[tuple[str, str]] = []
    for match in pattern.finditer(source):
        start = match.end()
        depth = 1
        quote = ""
        escaped = False
        index = start
        while index < len(source) and depth:
            char = source[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif source.startswith("--", index):
                newline = source.find("\n", index)
                index = len(source) if newline < 0 else newline
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        if depth == 0:
            found.append((match.group(1), source[start:index - 1]))
    return found


def normalize_key(value: str) -> str:
    value = value.strip().replace("CONTROL", "CTRL")
    value = re.sub(r"\s*\+\s*", " + ", value)
    tokens = [part for part in re.split(r"\s+\+\s+|\s+", value) if part]
    tokens = [KEY_NAMES.get(token.lower(), token).upper() for token in tokens]
    modifiers = [token for token in ("SUPER", "CTRL", "ALT", "SHIFT") if token in tokens]
    keys = [token for token in tokens if token not in modifiers]
    return " + ".join(modifiers + keys)


def command_preview(arguments: list[str]) -> str:
    if len(arguments) < 3:
        return ""
    direct = literal_string(arguments[2])
    if direct is not None:
        return direct[:180]
    strings = lua_strings(arguments[2])
    if strings:
        return strings[0][:180]
    return re.sub(r"\s+", " ", arguments[2]).strip()[:180]


def parse_bindings(source: str, source_name: str) -> tuple[list[Binding], list[str]]:
    bindings: list[Binding] = []
    unbound: list[str] = []
    for name, body in calls(source, ("o.bind", "o.bind_toggle", "hl.unbind")):
        arguments = split_arguments(body)
        key = literal_string(arguments[0]) if arguments else None
        if name == "hl.unbind":
            if key is not None:
                unbound.append(normalize_key(key))
            continue
        description = literal_string(arguments[1]) if len(arguments) >= 2 else None
        if key is not None and description is not None:
            action = arguments[2].strip() if len(arguments) >= 3 else ""
            bindings.append(Binding(normalize_key(key), description, command_preview(arguments), source_name, action))
    return bindings, unbound


def generated_defaults(source_text: str) -> list[Binding]:
    generated: list[Binding] = []
    if '"Switch to workspace " .. workspace' in source_text:
        for workspace in range(1, 11):
            code = 9 + workspace
            generated.extend([
                Binding(normalize_key(f"SUPER + code:{code}"), f"Switch to workspace {workspace}", source="tiling.lua", action=f'hl.dsp.focus({{ workspace = "{workspace}" }})'),
                Binding(normalize_key(f"SUPER + SHIFT + code:{code}"), f"Move window to workspace {workspace}", source="tiling.lua", action=f'hl.dsp.window.move({{ workspace = "{workspace}" }})'),
                Binding(normalize_key(f"SUPER + SHIFT + ALT + code:{code}"), f"Move window silently to workspace {workspace}", source="tiling.lua", action=f'hl.dsp.window.move({{ workspace = "{workspace}", follow = false }})'),
            ])
    if '"Switch to group window " .. index' in source_text:
        for index in range(1, 6):
            generated.append(Binding(normalize_key(f"SUPER + ALT + code:{index + 9}"), f"Switch to group window {index}", source="tiling.lua", action=f"hl.dsp.group.active({{ index = {index} }})"))
    if '"Bar panel " .. panel' in source_text:
        for panel in range(1, 10):
            generated.append(Binding(normalize_key(f"SUPER + CTRL + code:{panel + 9}"), f"Bar panel {panel}", source="utilities.lua", action=f'"omarchy-shell -q shell togglePanelAt right {panel}"'))
    return generated


def default_bindings() -> list[Binding]:
    config = read(HYPRLAND_CONFIG)
    if re.search(r"^\s*omarchy_default_bindings\s*=\s*false", config, re.M):
        return []
    preinstalled = not re.search(r"^\s*omarchy_preinstalled_bindings\s*=\s*false", config, re.M)
    result: list[Binding] = []
    combined = ""
    for path in sorted(DEFAULT_DIR.glob("*.lua")):
        source = read(path)
        combined += source
        parsed, _ = parse_bindings(source, path.name)
        if path.name == "applications.lua" and not preinstalled:
            before_optional = source.split("if o.preinstalled_bindings_enabled()", 1)[0]
            parsed, _ = parse_bindings(before_optional, path.name)
        result.extend(parsed)
    result.extend(generated_defaults(combined))
    return result


def current_runtime_bindings() -> list[Binding]:
    try:
        completed = subprocess.run(
            ["omarchy", "menu", "keybindings", "--print"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    result: list[Binding] = []
    for line in completed.stdout.splitlines():
        if "→" not in line:
            continue
        key, description = line.split("→", 1)
        result.append(Binding(normalize_key(key), description.strip(), source="Hyprland"))
    return result if len(result) > 10 else []


def managed_overrides() -> list[dict[str, str]]:
    path = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "omarchy/omakeybinds-overrides.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in data.get("overrides", []) if isinstance(item, dict)]


def build() -> dict[str, object]:
    defaults = default_bindings()
    custom, unbound = parse_bindings(read(USER_BINDINGS), USER_BINDINGS.name)
    default_by_key: dict[str, list[Binding]] = {}
    for item in defaults:
        default_by_key.setdefault(item.key, []).append(item)

    overrides = managed_overrides()
    deleted_overrides = [item for item in overrides if item.get("kind") == "deleted"]
    deleted_override_keys = {
        normalize_key(item.get("current_key", "")) or normalize_key(item.get("original_key", ""))
        for item in deleted_overrides
    }

    runtime = current_runtime_bindings()
    if runtime:
        active = runtime
    else:
        active = [item for item in defaults if item.key not in set(unbound)]
        active.extend(item for item in custom if item.key not in deleted_override_keys)

    custom_by_pair = {(item.key, item.description): item for item in custom}
    defaults_by_pair = {(item.key, item.description): item for item in defaults}
    active_key_counts: dict[str, int] = {}
    for item in active:
        active_key_counts[item.key] = active_key_counts.get(item.key, 0) + 1
    override_by_pair = {(normalize_key(item.get("current_key", "")), item.get("description", "")): item for item in overrides}
    moved_origin_keys = {normalize_key(item.get("original_key", "")) for item in overrides if item.get("current_key") != item.get("original_key")}
    output: list[dict[str, object]] = []
    active_keys: set[str] = set()
    for item in active:
        active_keys.add(item.key)
        original = default_by_key.get(item.key, [])
        exact_default = any(candidate.description == item.description for candidate in original)
        explicit_custom = (item.key, item.description) in custom_by_pair
        if original and (explicit_custom or not exact_default):
            status = "changed"
        elif not original:
            status = "custom"
        else:
            status = "default"
        custom_item = custom_by_pair.get((item.key, item.description))
        source_item = custom_item or defaults_by_pair.get((item.key, item.description))
        managed = override_by_pair.get((item.key, item.description))
        if managed:
            status = managed.get("kind", status)
        action = managed.get("action", "") if managed else (source_item.action if source_item else "")
        previous = "; ".join(dict.fromkeys(candidate.description for candidate in original)) if status == "changed" else ""
        if managed:
            previous = managed.get("previous", previous)
        output.append({
            "key": item.key,
            "description": item.description,
            "command": custom_item.command if custom_item else item.command,
            "source": custom_item.source if custom_item else item.source,
            "status": status,
            "previous": previous,
            "disabled": False,
            "action": action,
            # Rebinding one action on a multi-action key would unbind its siblings.
            "editable": bool(action) and active_key_counts.get(item.key, 0) == 1,
            "overrideId": managed.get("id", "") if managed else "",
            "originKey": managed.get("original_key", item.key) if managed else item.key,
        })

    # Managed deletions retain their original description and action so the UI can
    # explain exactly what was removed, including shortcuts that were custom.
    for managed in deleted_overrides:
        key = normalize_key(managed.get("current_key", "")) or normalize_key(managed.get("original_key", ""))
        if not key or key in active_keys:
            continue
        output.append({
            "key": key,
            "description": managed.get("description", "Deleted"),
            "command": "",
            "source": USER_BINDINGS.name,
            "status": "deleted",
            "previous": managed.get("previous", ""),
            "disabled": True,
            "action": managed.get("action", ""),
            "editable": bool(managed.get("action", "")),
            "overrideId": managed.get("id", ""),
            "originKey": managed.get("original_key", key),
            "restoreKind": managed.get("previous_kind", "changed"),
        })

    # An explicit unbind without a replacement is still an important changed shortcut.
    custom_keys = {item.key for item in custom}
    for key in unbound:
        if key in default_by_key and key not in active_keys and key not in custom_keys and key not in moved_origin_keys and key not in deleted_override_keys:
            originals = default_by_key[key]
            restorable = len(originals) == 1 and bool(originals[0].action)
            output.append({
                "key": key,
                "description": originals[0].description if len(originals) == 1 else "Deleted",
                "command": "",
                "source": USER_BINDINGS.name,
                "status": "deleted",
                "previous": "; ".join(dict.fromkeys(item.description for item in originals)),
                "disabled": True,
                "action": originals[0].action if len(originals) == 1 else "",
                "editable": restorable,
                "overrideId": "",
                "originKey": key,
                "restoreKind": "default",
            })

    unique: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for item in output:
        identity = (item["key"], item["description"], item["status"], item["disabled"])
        if identity not in seen:
            seen.add(identity)
            unique.append(item)
    priority = {"deleted": 0, "changed": 1, "custom": 2, "default": 3}
    unique.sort(key=lambda item: (priority[str(item["status"])], str(item["key"]), str(item["description"]).lower()))
    counts = {
        "all": len(unique),
        "default": sum(item["status"] == "default" for item in unique),
        "changed": sum(item["status"] == "changed" for item in unique),
        "custom": sum(item["status"] == "custom" for item in unique),
        "deleted": sum(item["status"] == "deleted" for item in unique),
    }
    return {"items": unique, "counts": counts}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, separators=(",", ":")))
