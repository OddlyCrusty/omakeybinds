"""Discover desktop launchers and prepare new actions without launching anything."""
from __future__ import annotations

import configparser
import json
import os
import re
import shlex
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from shortcut_model import binding_spec, lua_string
from shortcut_store import digest


def data_roots() -> list[Path]:
    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    system = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return list(dict.fromkeys(Path(p) for p in [home, *system.split(":")] if p and Path(p).is_absolute()))


def unescape(value: str) -> str:
    return re.sub(r"\\([sntr\\])", lambda m: {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}[m[1]], value)


def localized(entry, key: str) -> str:
    locale = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG", "C")
    locale = re.sub(r"\.[^@]+", "", locale)
    language, _, modifier = locale.partition("@")
    base = language.split("_")[0]
    for candidate in dict.fromkeys([locale, language, base + "@" + modifier if modifier else base, base]):
        if key + "[" + candidate + "]" in entry:
            return unescape(entry[key + "[" + candidate + "]"])
    return unescape(entry.get(key, ""))


def applications() -> list[dict]:
    """XDG precedence is applied before filtering, including hidden overrides.

    Exec is never parsed into a shell command. UWSM handles desktop launching.
    Ambiguous IDs within a data root are omitted, not guessed.
    """
    seen = set()
    result = []
    desktops = set(filter(None, os.environ.get("XDG_CURRENT_DESKTOP", "").split(":")))
    for root in data_roots():
        directory = root / "applications"
        entries = {}
        for path in sorted(directory.rglob("*.desktop")):
            app_id = str(path.relative_to(directory)).replace("/", "-")
            entries.setdefault(app_id, []).append(path)
        for app_id, paths in entries.items():
            if app_id in seen:
                continue
            seen.add(app_id)
            # UWSM treats ':' as an action suffix. Reject unsafe/unsupported IDs.
            if len(paths) != 1 or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.desktop", app_id):
                continue
            path = paths[0]
            try:
                raw = path.read_text(encoding="utf-8")
                parser = configparser.ConfigParser(interpolation=None, strict=True)
                parser.optionxform = str
                parser.read_string(raw)
                entry = parser["Desktop Entry"]
                if entry.get("Type") != "Application" or any(entry.get(k) == "true" for k in ("Hidden", "NoDisplay")):
                    continue
                only = set(filter(None, entry.get("OnlyShowIn", "").split(";")))
                excluded = set(filter(None, entry.get("NotShowIn", "").split(";")))
                if (only and not desktops.intersection(only)) or desktops.intersection(excluded):
                    continue
                executable = unescape(entry.get("TryExec", ""))
                if executable and not shutil.which(executable):
                    continue
                name = localized(entry, "Name")
                if not name or not entry.get("Exec"):
                    continue
                result.append({"id": app_id, "name": name, "icon": unescape(entry.get("Icon", "")),
                               "comment": localized(entry, "Comment"), "terminal": entry.get("Terminal") == "true",
                               "revision": digest(str(path) + "\0" + raw)})
            except (OSError, UnicodeError, configparser.Error, KeyError):
                continue
    return sorted(result, key=lambda item: (item["name"].casefold(), item["id"]))


def prepare(target: dict) -> dict:
    if (not isinstance(target, dict) or set(target) != {"type", "value", "description"}
            or any(not isinstance(v, str) for v in target.values())
            or target["type"] not in ("app", "website", "folder", "command")
            or not target["value"].strip() or len(target["value"]) > 4096
            or len(target["description"]) > 160
            or any(ord(c) < 32 or ord(c) == 127 for v in target.values() for c in v)):
        raise ValueError("Choose an action and enter a valid, single-line value and description.")
    kind, value = target["type"], target["value"]
    revision = ""
    if kind == "app":
        matches = [app for app in applications() if app["id"] == value]
        if len(matches) != 1:
            raise ValueError("This app launcher is no longer available. Go back and choose an installed app.")
        if not shutil.which("uwsm-app"):
            raise ValueError("Omarchy's uwsm-app launcher is unavailable.")
        app = matches[0]
        command = "uwsm-app -- " + shlex.quote(app["id"])
        description = "Launch " + app["name"]
        revision = app["revision"]
        detail = "Uses the installed app launcher" + (" in a terminal." if app["terminal"] else ".")
    elif kind == "website":
        try:
            url = urlsplit(value)
            valid = (url.scheme in ("https", "http") and url.hostname and url.port != 0
                     and not url.username and not url.password and not any(c.isspace() for c in value))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("Enter a complete http:// or https:// website address without credentials or spaces.")
        command = "xdg-open " + shlex.quote(value)
        description = "Open " + url.hostname
        detail = "Opens in your default browser."
    elif kind == "folder":
        path = Path(value).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("Choose an existing folder using an absolute path or ~/.")
        command = "xdg-open " + shlex.quote(str(path))
        description = "Open " + (path.name or str(path))
        detail = "Opens in your default file manager."
    else:
        command = value
        description = "Custom command"
        detail = "Advanced: runs this shell command with your user permissions when you press the shortcut."
    if kind in ("website", "folder") and not shutil.which("xdg-open"):
        raise ValueError("The xdg-open launcher is unavailable.")
    description = target["description"].strip() or description[:160]
    spec = binding_spec(lua_string(command))
    # The review page may rename the shortcut, but cannot change the reviewed
    # action. Labels are validated above and encoded as literal Lua strings.
    token = digest(json.dumps([kind, value, spec, revision], sort_keys=True, ensure_ascii=False))
    return {"description": description, "command": command, "detail": detail, "token": token, "spec": spec}


if __name__ == "__main__":
    try:
        print(json.dumps({"apps": applications(), "error": ""}, ensure_ascii=False))
    except (OSError, ValueError):
        print(json.dumps({"apps": [], "error": "Could not read the installed application list."}))
