#!/usr/bin/env python3
"""Check against installed shell imports using a temporary import alias only."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
shell = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
linter = shutil.which("qmllint") or "/usr/lib/qt6/bin/qmllint"
if not shell.is_dir() or not Path(linter).is_file():
    print("QML lint skipped: installed Omarchy shell and Qt linter are required")
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix="omakeybinds-qml-") as directory:
    # qs.* is a Quickshell runtime alias. Make the same read-only import path
    # available to qmllint, without adding anything to the installed shell.
    (Path(directory) / "qs").symlink_to(shell, target_is_directory=True)
    result = subprocess.run([linter, "-I", directory, "-I", "/usr/lib/qt6/qml",
                             *map(str, sorted(root.glob("*.qml")))],
                            capture_output=True, text=True, check=False)
    diagnostics = result.stdout + result.stderr
    blocking = [line for line in diagnostics.splitlines()
                if line.startswith("Error:") or re.search(r"\[(?:import|syntax|unresolved-type|inheritance-cycle|signal-handler-parameters)\]", line)]
    if result.returncode or blocking:
        print(diagnostics)
        raise SystemExit(1)
    print(f"QML imports and structure passed ({diagnostics.count('Warning:')} advisory warnings, mainly dynamic shell properties)")
