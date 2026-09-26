#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

python3 -m py_compile scan_shortcuts.py update_shortcut.py reset_shortcuts.py remove_overrides.py
python3 -m unittest discover -s tests -v
python3 -c 'import json, pathlib; data=json.loads(pathlib.Path("manifest.json").read_text()); assert data["schemaVersion"] == 1; assert data["id"] == "io.github.oddlycrusty.omakeybinds"; assert data["entryPoints"]["barWidget"] == "BarWidget.qml"'

if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin validate .
else
  echo "omarchy is unavailable; skipped native plugin validation"
fi
