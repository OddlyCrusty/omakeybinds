import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock


PLUGIN = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, PLUGIN / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scanner = load("scan_shortcuts")
updater = load("update_shortcut")
resetter = load("reset_shortcuts")
cleaner = load("remove_overrides")


class ScannerTests(unittest.TestCase):
    def test_parser_preserves_action_expression(self):
        bindings, unbound = scanner.parse_bindings(
            'hl.unbind("SUPER + F")\no.bind("SUPER + G", "Full screen", hl.dsp.window.fullscreen({ mode = "fullscreen" }))',
            "test.lua",
        )
        self.assertEqual(unbound, ["SUPER + F"])
        self.assertEqual(bindings[0].key, "SUPER + G")
        self.assertEqual(bindings[0].action, 'hl.dsp.window.fullscreen({ mode = "fullscreen" })')

    def test_normalizes_modifier_order(self):
        self.assertEqual(scanner.normalize_key("shift + super + c"), "SUPER + SHIFT + C")

    def test_managed_override_builds_without_unbound_previous_value(self):
        default = scanner.Binding("SUPER + F", "Full screen", source="test.lua", action="action()")
        active = scanner.Binding("SUPER + G", "Full screen", source="Hyprland")
        managed = {
            "id": "one",
            "original_key": "SUPER + F",
            "current_key": "SUPER + G",
            "description": "Full screen",
            "action": "action()",
            "kind": "changed",
            "previous": "SUPER + F — Full screen",
        }
        with mock.patch.object(scanner, "default_bindings", return_value=[default]), \
             mock.patch.object(scanner, "current_runtime_bindings", return_value=[active] * 11), \
             mock.patch.object(scanner, "managed_overrides", return_value=[managed]), \
             mock.patch.object(scanner, "read", return_value=""):
            result = scanner.build()
        self.assertEqual(result["items"][0]["previous"], managed["previous"])


class UpdaterTests(unittest.TestCase):
    def request(self, **changes):
        data = dict(origin_key="SUPER + F", old_key="SUPER + F", new_key="SUPER + G",
                    description="Private shortcut", action='"app --token test-secret-ä"', kind="custom")
        data.update(changes)
        return data

    def test_stdin_request_preserves_private_action(self):
        request = self.request(action='"app --token test-secret \\\"quoted\\\""\n-- Unicode: ä')
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(request))):
            self.assertEqual(updater.read_request().action, request["action"])

    def test_invalid_requests_fail_without_writes_or_private_output(self):
        requests = ["", "test-secret", "[]", "null", json.dumps({"action": "test-secret"})]
        requests += [json.dumps(self.request(**change)) for change in (
            {"action": None}, {"kind": "test-secret"}, {"previous_kind": "test-secret"},
            {"extra": "test-secret"}, {"new_key": 123})]
        for request in requests:
            with self.subTest(request=request), \
                 mock.patch.object(sys, "stdin", io.StringIO(request)), \
                 mock.patch.object(sys, "stdout", new_callable=io.StringIO) as output, \
                 mock.patch.object(updater, "load_state") as load_state:
                self.assertEqual(updater.main(), 2)
                self.assertFalse(json.loads(output.getvalue())["ok"])
                self.assertNotIn("test-secret", output.getvalue())
                load_state.assert_not_called()

    def test_edit_delete_restore_from_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            bindings = Path(directory) / "bindings.lua"
            state = Path(directory) / "overrides.json"
            bindings.write_text("-- Personal bindings\n")
            for kind in ("custom", "deleted", "custom"):
                request = self.request(id="private", kind=kind, previous_kind="custom")
                with self.subTest(kind=kind), \
                     mock.patch.object(updater, "BINDINGS", bindings), \
                     mock.patch.object(updater, "STATE", state), \
                     mock.patch.object(sys, "stdin", io.StringIO(json.dumps(request))), \
                     mock.patch.object(sys, "stdout", new_callable=io.StringIO) as output, \
                     mock.patch.object(updater, "hyprctl", return_value=CompletedProcess([], 0, "", "")):
                    self.assertEqual(updater.main(), 0)
                    self.assertTrue(json.loads(output.getvalue())["ok"])
                    saved = json.loads(state.read_text())["overrides"][0]
                    self.assertEqual(saved["action"], request["action"])
                    self.assertEqual(saved["kind"], kind)
                    self.assertEqual("o.bind(" in bindings.read_text(), kind != "deleted")
                    self.assertNotIn("test-secret", output.getvalue())

    def test_private_action_is_absent_from_process_arguments(self):
        command = [sys.executable, str(PLUGIN / "update_shortcut.py")]
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) as process:
            try:
                # Keep stdin open so the helper remains alive while inspecting argv.
                process.stdin.write(json.dumps(self.request(new_key="")))
                process.stdin.flush()
                arguments = Path(f"/proc/{process.pid}/cmdline").read_bytes()
                self.assertNotIn(b"test-secret", arguments)
                self.assertNotIn(b"--action", arguments)
                output, errors = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 2)
                self.assertFalse(json.loads(output)["ok"])
                self.assertEqual(errors, "")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_managed_block_unbinds_original_and_collision(self):
        block = updater.managed_block([
            {
                "original_key": "SUPER + F",
                "current_key": "SUPER + G",
                "description": "Full screen",
                "action": 'hl.dsp.window.fullscreen({ mode = "fullscreen" })',
            }
        ])
        self.assertIn('hl.unbind("SUPER + F")', block)
        self.assertIn('hl.unbind("SUPER + G")', block)
        self.assertIn('o.bind("SUPER + G", "Full screen", hl.dsp.window.fullscreen', block)

    def test_replaces_existing_managed_block(self):
        source = "-- Personal\n" + updater.BEGIN + "\nold\n" + updater.END + "\n"
        replaced = updater.replace_block(source, updater.BEGIN + "\nnew\n" + updater.END + "\n")
        self.assertIn("-- Personal", replaced)
        self.assertIn("\nnew\n", replaced)
        self.assertNotIn("\nold\n", replaced)

    def test_replacement_removes_managed_collision(self):
        existing = [
            {"id": "first", "current_key": "SUPER + F"},
            {"id": "second", "current_key": "SUPER + G"},
        ]
        entry = {"id": "first", "current_key": "SUPER + G"}
        self.assertEqual(updater.upsert_override(existing, entry), [entry])

    def test_deleted_override_only_unbinds_shortcut(self):
        block = updater.managed_block([{
            "original_key": "SUPER + F",
            "current_key": "SUPER + F",
            "description": "Full screen",
            "action": "action()",
            "kind": "deleted",
        }])
        self.assertIn('hl.unbind("SUPER + F")', block)
        self.assertNotIn("o.bind(", block)


class DeletedShortcutTests(unittest.TestCase):
    def test_managed_custom_deletion_remains_visible(self):
        custom = scanner.Binding("SUPER + G", "My shortcut", source="bindings.lua", action='"my-command"')
        managed = {
            "id": "deleted-one",
            "original_key": "SUPER + G",
            "current_key": "SUPER + G",
            "description": "My shortcut",
            "action": '"my-command"',
            "kind": "deleted",
            "previous": "SUPER + G — My shortcut",
        }
        with mock.patch.object(scanner, "default_bindings", return_value=[]), \
             mock.patch.object(scanner, "current_runtime_bindings", return_value=[]), \
             mock.patch.object(scanner, "managed_overrides", return_value=[managed]), \
             mock.patch.object(scanner, "read", return_value='o.bind("SUPER + G", "My shortcut", "my-command")\nhl.unbind("SUPER + G")'):
            result = scanner.build()
        self.assertEqual(result["counts"]["deleted"], 1)
        self.assertEqual(result["items"][0]["description"], "My shortcut")
        self.assertTrue(result["items"][0]["editable"])
        self.assertEqual(result["items"][0]["restoreKind"], "changed")

    def test_changed_override_remains_active_without_runtime_data(self):
        managed = {
            "id": "changed-one",
            "original_key": "SUPER + F",
            "current_key": "SUPER + G",
            "description": "Full screen",
            "action": "action()",
            "kind": "changed",
            "previous": "SUPER + F — Full screen",
        }
        source = 'hl.unbind("SUPER + F")\nhl.unbind("SUPER + G")\no.bind("SUPER + G", "Full screen", action())'
        with mock.patch.object(scanner, "default_bindings", return_value=[]), \
             mock.patch.object(scanner, "current_runtime_bindings", return_value=[]), \
             mock.patch.object(scanner, "managed_overrides", return_value=[managed]), \
             mock.patch.object(scanner, "read", return_value=source):
            result = scanner.build()
        self.assertEqual(result["counts"]["changed"], 1)

    def test_plain_deleted_default_can_be_restored(self):
        default = scanner.Binding("SUPER + D", "Docker", source="test.lua", action='"docker"')
        with mock.patch.object(scanner, "default_bindings", return_value=[default]), \
             mock.patch.object(scanner, "current_runtime_bindings", return_value=[]), \
             mock.patch.object(scanner, "managed_overrides", return_value=[]), \
             mock.patch.object(scanner, "read", return_value='hl.unbind("SUPER + D")'):
            result = scanner.build()
        deleted = result["items"][0]
        self.assertEqual(deleted["description"], "Docker")
        self.assertEqual(deleted["action"], '"docker"')
        self.assertTrue(deleted["editable"])
        self.assertEqual(deleted["restoreKind"], "default")


class ResetterTests(unittest.TestCase):
    def test_success_clears_managed_state_after_refresh_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "omakeybinds-overrides.json"
            state.write_text('{"overrides": []}\n', encoding="utf-8")
            successful = CompletedProcess([], 0, "", "")
            with mock.patch.object(resetter, "STATE", state), mock.patch.object(resetter, "run", return_value=successful) as invoked:
                self.assertEqual(resetter.main(), 0)
            self.assertFalse(state.exists())
            self.assertEqual(invoked.call_count, 3)
            self.assertEqual(invoked.call_args_list[0].args[0], ["omarchy", "refresh", "config", "hypr/bindings.lua"])
            self.assertEqual(len(list(Path(directory).glob("*.bak.*"))), 1)


class CleanerTests(unittest.TestCase):
    def test_removes_only_managed_block(self):
        source = "-- Personal before\n" + updater.BEGIN + "\nmanaged\n" + updater.END + "\n-- Personal after\n"
        result = cleaner.without_managed_block(source)
        self.assertIn("-- Personal before", result)
        self.assertIn("-- Personal after", result)
        self.assertNotIn("managed overrides", result)
        self.assertNotIn("\nmanaged\n", result)


if __name__ == "__main__":
    unittest.main()
