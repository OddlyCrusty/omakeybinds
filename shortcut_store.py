"""Validated state and serialized, recoverable configuration transactions."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from shortcut_model import binding_spec, normalize_key, tokens

BEGIN = "-- BEGIN io.github.oddlycrusty.omakeybinds managed overrides"
END = "-- END io.github.oddlycrusty.omakeybinds managed overrides"
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
BINDINGS = CONFIG_HOME / "hypr/bindings.lua"
STATE = CONFIG_HOME / "omarchy/omakeybinds-overrides.json"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    """Do not translate CRLF: unrelated configuration bytes must survive."""
    return path.read_bytes().decode("utf-8")


def block_span(source: str) -> tuple[int, int] | None:
    markers = []
    for token in tokens(source, comments=True):
        marker = source[token.start:token.end].rstrip("\r")
        if token.kind != "comment" or marker not in (BEGIN, END):
            continue
        line_start = source.rfind("\n", 0, token.start) + 1
        if source[line_start:token.start].strip():
            continue
        markers.append((marker, line_start, token.end + (source[token.end:token.end + 1] == "\n")))
    if not markers:
        return None
    if len(markers) != 2 or [m[0] for m in markers] != [BEGIN, END]:
        raise ValueError("Managed block markers are incomplete or duplicated; restore a backup first.")
    return markers[0][1], markers[1][2]


def replace_block(source: str, block: str) -> str:
    span = block_span(source)
    if span:
        return source[:span[0]] + block + source[span[1]:]
    if not block:
        return source
    return source + ("" if source.endswith("\n") else "\n") + "\n" + block


def load_state(path: Path = STATE) -> dict:
    try:
        raw = read_text(path)
    except FileNotFoundError:
        if path.is_symlink():
            raise ValueError("The state file is a broken symlink.")
        return {"version": 2, "overrides": []}
    except (OSError, UnicodeError) as error:
        raise ValueError("Could not read shortcut state; no changes were made.") from error
    try:
        state = json.loads(raw)
        if (not isinstance(state, dict) or type(state.get("version")) is not int
                or state["version"] not in (1, 2) or not isinstance(state.get("overrides"), list)):
            raise ValueError()
        seen = set()
        for item in state["overrides"]:
            fields = ("id", "original_key", "current_key", "description", "action", "kind")
            if not isinstance(item, dict) or any(not isinstance(item.get(k), str) for k in fields):
                raise ValueError()
            if not item["id"] or item["id"] in seen or item["kind"] not in ("default", "changed", "custom", "deleted"):
                raise ValueError()
            seen.add(item["id"])
            normalize_key(item["original_key"])
            normalize_key(item["current_key"])
            if item.get("previous_kind", "changed") not in ("default", "changed", "custom"):
                raise ValueError()
            if not isinstance(item.get("previous", ""), str):
                raise ValueError()
            if any(type(item.get(field, False)) is not bool for field in ("created", "preserve_origin")):
                raise ValueError()
            if state["version"] == 2:
                if any(not isinstance(item.get(k), str) for k in ("call", "options")):
                    raise ValueError()
                binding_spec(item["action"], item["call"], item["options"])
        if state["version"] == 2 and not isinstance(state.get("block_digest", ""), str):
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
        raise ValueError("Shortcut state is invalid. Restore a backup or remove managed overrides before editing.") from error
    return state


def check_block_state(source: str, state: dict) -> None:
    span = block_span(source)
    if span and not state["overrides"]:
        raise ValueError("Managed bindings have no matching state. Restore state or remove managed overrides first.")
    if state["overrides"] and not span:
        raise ValueError("Shortcut state has no matching managed block. Remove stale managed state before editing.")
    if span and state["version"] == 2 and state.get("block_digest") != digest(source[span[0]:span[1]]):
        raise ValueError("The managed block changed outside OmaKeybinds. Restore it or remove managed overrides first.")


@contextmanager
def mutation_lock(state_path: Path = STATE):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.parent / ".omakeybinds.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("Unsafe shortcut lock file.")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another shortcut operation is running. Try again when it finishes.") from error
        yield
    finally:
        os.close(descriptor)


def target_path(path: Path) -> Path:
    if path.is_symlink():
        path = path.resolve(strict=True)
    if path.exists() and not path.is_file():
        raise ValueError("Configuration target is not a regular file.")
    return path


def atomic_write(path: Path, content: str | bytes) -> None:
    path = target_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content.encode("utf-8") if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def backup(path: Path) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".bak.omakeybinds-", dir=path.parent)
    result = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(path.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        result.unlink(missing_ok=True)
        raise
    return result


def hyprctl(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["hyprctl", *arguments], capture_output=True, text=True, timeout=8, check=False)


def validate() -> None:
    reloaded = hyprctl("reload")
    checked = hyprctl("configerrors")
    if reloaded.returncode or checked.returncode or checked.stdout.strip() or checked.stderr.strip():
        # Configuration errors may quote commands containing credentials.
        raise ValueError("Hyprland rejected the configuration.")


def transaction(bindings: Path, state_path: Path, original: str, replacement: str, new_state: dict | None) -> dict:
    """Caller holds mutation_lock. Commit metadata only after reload validation."""
    bindings = target_path(bindings)
    state_path = target_path(state_path)
    if read_text(bindings) != original:
        raise ValueError("Bindings changed during this operation. Rescan and try again.")
    original_state = state_path.read_bytes() if state_path.exists() else None
    bindings_backup = backup(bindings)
    state_backup = backup(state_path) if original_state is not None else None
    written = False
    try:
        atomic_write(bindings, replacement)
        written = True
        validate()
        if read_text(bindings) != replacement:
            raise ValueError("Bindings changed during validation.")
        if (state_path.read_bytes() if state_path.exists() else None) != original_state:
            raise ValueError("Shortcut state changed during validation.")
        if new_state is None:
            # Preserve a state symlink too: an empty v2 state is equivalent to
            # removal and keeps the user's dotfiles linkage intact.
            atomic_write(state_path, json.dumps({"version": 2, "overrides": []}) + "\n")
        else:
            atomic_write(state_path, json.dumps(new_state, ensure_ascii=False, indent=2) + "\n")
    except Exception as error:
        if written:
            if read_text(bindings) != replacement:
                raise ValueError("Configuration changed concurrently; kept that version. Recover from the backup if needed.") from error
            atomic_write(bindings, original)
            try:
                validate()
            except Exception:
                raise ValueError("Original file restored, but Hyprland could not reload it. Check the configuration and reload manually.") from error
        raise ValueError("Change rolled back; configuration or state could not be validated or saved.") from error
    return {"backup": str(bindings_backup), "stateBackup": str(state_backup) if state_backup else ""}
