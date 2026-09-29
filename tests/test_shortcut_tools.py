"""Regression coverage for parsing, privacy, and configuration transactions."""
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import shortcut_model as model
import shortcut_store as store
import scan_shortcuts as scanner
import update_shortcut as updater
import reset_shortcuts as resetter
import remove_overrides as cleaner

ROOT = Path(__file__).resolve().parents[1]


def entry(**changes):
    value = dict(id="one", original_key="SUPER + F", current_key="SUPER + G", description="Example",
                 action='"true"', call="o.bind", options="{}", kind="changed", previous="SUPER + F — Example")
    value.update(changes)
    return value


class ModelTests(unittest.TestCase):
    def test_unicode_and_lua_escapes_round_trip(self):
        for text in ['Öppna 🔑', 'quotes " and \\', '\n\r\t\x00123\x1f9', 'code:10', store.BEGIN]:
            with self.subTest(text=text):
                self.assertEqual(model.literal_string(model.lua_string(text)), text)
        self.assertEqual(model.literal_string(r'"\195\150ppna"'), 'Öppna')
        self.assertEqual(model.literal_string(r'"\u{1f511}\z  key"'), '🔑key')
        self.assertEqual(model.literal_string('[=[\nhello]=]'), 'hello')

    def test_calls_ignore_strings_and_all_comment_forms(self):
        source = '''-- o.bind("A", "comment", "false")
--[=[ o.bind("B", "long comment", "false") ]=]
local example = [==[ o.bind("C", "long string", "false") ]==]
local text = 'o.bind("D", "short string", "false")'
o.bind("SUPER + F", "Öppna", "true")
'''
        bindings, unbound = scanner.parse_bindings(source, "test.lua")
        self.assertEqual([(b.key, b.description) for b in bindings], [("SUPER + F", "Öppna")])
        self.assertEqual(unbound, [])

    def test_strings_with_even_backslashes_parse(self):
        value = 'path\\'
        self.assertEqual(model.literal_string(model.lua_string(value)), value)

    def test_unsupported_expressions_are_not_executable_edits(self):
        for expression in ['local_helper("x")', 'function() return true end', 'os.execute("true")',
                           '"ok"); AUDIT_MARKER=true; o.bind("A"', 'hl.dsp.exec_cmd(os.getenv("SECRET"))',
                           '{ launch = get_command() }', 'hl.dsp["exec_cmd"]("true")']:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                model.binding_spec(expression)

    def test_table_and_dispatcher_arguments_preserved(self):
        spec = model.binding_spec('hl.dsp.window.resize({ x = -100, y = 0, relative = true })',
                                  options='{ locked = true, repeating = true, release = true }')
        self.assertEqual(spec['action'], 'hl.dsp.window.resize({ x = -100, y = 0, relative = true })')
        self.assertIn('repeating = true', spec['options'])
        binding = scanner.parse_bindings('o.bind_toggle("SUPER + F", "Toggle", "bar", { locked = true })', 'test')[0][0]
        self.assertEqual(binding.spec()['call'], 'o.bind_toggle')
        self.assertEqual(binding.spec()['options'], '{ locked = true }')

    def test_raw_keys_preserved_and_idempotent(self):
        for key in ['SUPER + code:10', 'SUPER + mouse:272', 'ALT + mouse_down', 'CTRL + SHIFT + A']:
            self.assertEqual(model.normalize_key(key), key)
            self.assertEqual(model.normalize_key(model.normalize_key(key)), key)
        self.assertEqual(model.normalize_key('shift + super + c'), 'SUPER + SHIFT + C')
        self.assertEqual(model.display_key('SUPER + mouse:272'), 'SUPER + LEFT MOUSE BUTTON')
        self.assertEqual(model.display_key('SUPER + code:10'), 'SUPER + 1')

    def test_invalid_key_identifiers_rejected(self):
        for key in ['', 'SUPER + F\nINJECT', 'SUPER + "F"', 'SUPER + F + G', 'LEFT MOUSE BUTTON', 'SUPER']:
            with self.subTest(key=key), self.assertRaises(ValueError):
                model.normalize_key(key)

    def test_existing_block_preserves_all_backslashes(self):
        block = updater.managed_block([entry(action=r'"printf \\n \\\"quoted\\\""')])
        source = store.replace_block('-- Personal\n', block)
        for _ in range(5):
            self.assertEqual(store.replace_block(source, block), source)

    def test_markers_inside_literals_or_long_comments_ignored(self):
        source = 'local text = [=[\n' + store.BEGIN + '\n' + store.END + '\n]=]\n'
        source += '--[[' + store.BEGIN + ']]\n'
        self.assertIsNone(store.block_span(source))
        self.assertEqual(cleaner.without_managed_block(source), source)
        block = updater.managed_block([entry()])
        complete = source + block + '-- trailing\r\n\r\n'
        self.assertEqual(cleaner.without_managed_block(complete), source + '-- trailing\r\n\r\n')

    def test_incomplete_or_duplicate_markers_rejected(self):
        for source in [store.BEGIN + '\n', store.END + '\n', (store.BEGIN + '\n' + store.END + '\n') * 2]:
            with self.assertRaises(ValueError):
                store.block_span(source)

    def test_crlf_markers_and_surrounding_bytes(self):
        source = '-- before\r\n' + store.BEGIN + '\r\nold\r\n' + store.END + '\r\n-- after\r\n'
        self.assertEqual(cleaner.without_managed_block(source), '-- before\r\n-- after\r\n')


@unittest.skipUnless(shutil.which('lua'), 'Lua interpreter needed for generated-code behavior tests')
class LuaTests(unittest.TestCase):
    def lua(self, source):
        prelude = '''
bindings = {}
hl = { unbind = function(key) bindings[key] = nil end }
o = { bind = function(key, description, action, options) bindings[key] = {description, action, options} end }
o.bind_toggle = function(key, description, toggle, options) o.bind(key, description, "omarchy-toggle-" .. toggle, options) end
'''
        result = subprocess.run(['lua', '-'], input=prelude + source, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_description_cannot_execute_lua(self):
        description = 'Label\nAUDIT_MARKER = true --'
        block = updater.managed_block([entry(description=description)])
        self.assertEqual(self.lua(block + '\nprint(AUDIT_MARKER == nil)'), 'true\n')

    def test_escaping_preserves_command_after_repeated_writes(self):
        command = 'printf \\n "quoted" Öppna'
        block = updater.managed_block([entry(action=model.lua_string(command))])
        first = store.replace_block('--personal\n', block)
        second = store.replace_block(first, block)
        self.assertEqual(self.lua(second + '\nio.write(bindings["SUPER + G"][2])'), command)

    def test_reused_origin_survives_later_edit(self):
        overrides = [entry(), entry(id='two', original_key='SUPER + H', current_key='SUPER + F', description='Other')]
        overrides = updater.upsert_override(overrides, entry(current_key='SUPER + J'))
        block = updater.managed_block(overrides)
        self.assertEqual(self.lua(block + '\nprint(bindings["SUPER + F"][1], bindings["SUPER + J"][1])'), 'Other\tExample\n')

    def test_toggle_and_options_keep_semantics(self):
        block = updater.managed_block([entry(action='"bar"', call='o.bind_toggle', options='{ locked = true, repeating = true, release = true }')])
        self.assertEqual(self.lua(block + '\nlocal b=bindings["SUPER + G"]; print(b[2], b[3].locked, b[3].repeating, b[3].release)'), 'omarchy-toggle-bar\ttrue\ttrue\ttrue\n')


class RuntimeTests(unittest.TestCase):
    def test_empty_and_small_successes_are_authoritative(self):
        for data in [[], [{'modmask': 64, 'key': 'F', 'keycode': 0, 'description': 'Example'}]]:
            with mock.patch.object(scanner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(data), '')) as run:
                result = scanner.current_runtime_bindings()
                self.assertEqual(len(result), len(data))
                self.assertEqual(run.call_args.args[0], ['hyprctl', '-j', 'binds'])

    def test_malformed_json_uses_plain_metadata_without_lua_execution(self):
        plain = 'bindd\n\tmodmask: 64\n\tkey: SUPER + code:10\n\tkeycode: 0\n\tdescription: Öppna\n\tsubmap: \n'
        with mock.patch.object(scanner.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 0, '{bad', ''), subprocess.CompletedProcess([], 0, plain, '')]) as run:
            result = scanner.current_runtime_bindings()
            self.assertEqual(result[0].key, 'SUPER + code:10')
            self.assertEqual(result[0].description, 'Öppna')
            self.assertEqual(run.call_args.args[0], ['hyprctl', 'binds'])

    def test_failure_is_not_empty_success(self):
        with mock.patch.object(scanner.subprocess, 'run', side_effect=OSError()):
            self.assertIsNone(scanner.current_runtime_bindings())

    def test_valid_json_with_lost_key_identity_uses_text_fallback(self):
        broken = [{'modmask': 64, 'key': '', 'keycode': 0, 'description': 'Workspace'}]
        plain = 'bindd\n\tmodmask: 64\n\tkey: SUPER + code:10\n\tkeycode: 0\n\tdescription: Workspace\n'
        with mock.patch.object(scanner.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 0, json.dumps(broken), ''), subprocess.CompletedProcess([], 0, plain, '')]):
            self.assertEqual(scanner.current_runtime_bindings()[0].key, 'SUPER + code:10')

    def test_ambiguous_duplicate_runtime_fields_fail_closed(self):
        plain = 'bindd\n\tmodmask: 64\n\tkey: F\n\tkeycode: 0\n\tdescription: Label\n\tkey: G\n'
        with mock.patch.object(scanner.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 0, 'bad', ''), subprocess.CompletedProcess([], 0, plain, '')]):
            self.assertIsNone(scanner.current_runtime_bindings())


class ConfigFixture(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.bindings = self.base / 'bindings.lua'
        self.state = self.base / 'state.json'
        self.defaults = self.base / 'default'
        self.defaults.mkdir()
        self.config = self.base / 'hyprland.lua'
        self.config.write_text('')
        self.bindings.write_text('-- personal\n')
        self.default_source = 'o.bind("SUPER + F", "Example", "true")\no.bind("SUPER + H", "Other", "true")\n'
        (self.defaults / 'basic.lua').write_text(self.default_source)
        self.shipped = self.base / 'shipped.lua'
        self.shipped.write_text('-- shipped bindings\n')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module, key, value in [(scanner, 'USER_BINDINGS', self.bindings), (scanner, 'STATE', self.state),
                                   (scanner, 'DEFAULT_DIR', self.defaults), (scanner, 'HYPRLAND_CONFIG', self.config),
                                   (updater, 'BINDINGS', self.bindings), (updater, 'STATE', self.state),
                                   (resetter, 'BINDINGS', self.bindings), (resetter, 'STATE', self.state),
                                   (resetter, 'DEFAULT_BINDINGS', self.shipped), (cleaner, 'BINDINGS', self.bindings), (cleaner, 'STATE', self.state)]:
            self.stack.enter_context(mock.patch.object(module, key, value))
        self.validation = self.stack.enter_context(mock.patch.object(store, 'validate'))
        self.runtime = self.stack.enter_context(mock.patch.object(scanner, 'current_runtime_bindings', side_effect=self.live))

    def live(self):
        # Simulated compositor: apply literal bind/unbind operations in order.
        current = []
        for operation in scanner.operations(self.default_source + store.read_text(self.bindings), 'fixture'):
            if isinstance(operation, str):
                current = [b for b in current if b.key != operation]
            else:
                current.append(scanner.Binding(operation.key, operation.description, source='Hyprland'))
        return current

    def request(self, key='SUPER + F', operation='edit', new_key='SUPER + G', replace=False, disabled=False):
        view = scanner.build()
        self.assertEqual(view['error'], '')
        row = next(b for b in view['items'] if b['key'] == key and b['disabled'] == disabled)
        self.assertTrue(row['editable'], row)
        return dict(token=row['token'], snapshot=view['snapshot'], new_key=new_key, operation=operation, replace=replace)


class ScannerTests(ConfigFixture):
    def test_unbound_default_remains_deleted_when_key_is_reused(self):
        self.bindings.write_text('hl.unbind("SUPER + F")\no.bind("SUPER + F", "New owner", "true")\n')
        rows = [b for b in scanner.build()['items'] if b['key'] == 'SUPER + F']
        self.assertEqual({(b['description'], b['disabled']) for b in rows},
                         {('Example', True), ('New owner', False)})
        request = self.request(key='SUPER + F', operation='restore', new_key='SUPER + F', disabled=True, replace=True)
        before = self.bindings.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Choose another key to restore'):
            updater.apply_request(request)
        self.assertEqual(self.bindings.read_bytes(), before)
        request['new_key'] = 'SUPER + J'
        updater.apply_request(request)
        self.assertIn(('SUPER + F', 'New owner'), {(b.key, b.description) for b in self.live()})
        self.assertIn(('SUPER + J', 'Example'), {(b.key, b.description) for b in self.live()})
        self.assertFalse(any(b['disabled'] for b in scanner.build()['items']))
        updater.apply_request(self.request(key='SUPER + J', operation='delete'))
        updater.apply_request(self.request(key='SUPER + J', operation='restore', new_key='SUPER + G', disabled=True))
        self.assertIn(('SUPER + F', 'New owner'), {(b.key, b.description) for b in self.live()})

    def test_known_dynamic_default_is_classified_but_read_only(self):
        source = 'for workspace = 1, 10 do o.bind("SUPER + " .. key, "Switch to workspace " .. workspace, action()) end'
        (self.defaults / 'tiling.lua').write_text(source)
        self.runtime.side_effect = None
        self.runtime.return_value = [scanner.Binding('SUPER + code:10', 'Switch to workspace 1')]
        row = scanner.build()['items'][0]
        self.assertEqual(row['status'], 'default')
        self.assertFalse(row['editable'])

    def test_unicode_matches_runtime_and_is_editable(self):
        self.bindings.write_text('o.bind("SUPER + J", "Öppna 🔑", "true")\n')
        row = next(b for b in scanner.build()['items'] if b['key'] == 'SUPER + J')
        self.assertTrue(row['editable'])
        self.assertEqual(row['description'], 'Öppna 🔑')
        self.assertNotIn('spec', row)

    def test_local_helpers_are_read_only(self):
        self.bindings.write_text('o.bind("SUPER + J", "Local", local_function())\n')
        row = next(b for b in scanner.build()['items'] if b['key'] == 'SUPER + J')
        self.assertFalse(row['editable'])
        self.assertIn('cannot be safely moved', row['reason'])

    def test_multi_action_keys_are_read_only(self):
        self.bindings.write_text('o.bind("SUPER + F", "Second", "true")\n')
        rows = [b for b in scanner.build()['items'] if b['key'] == 'SUPER + F']
        self.assertEqual(len(rows), 2)
        self.assertFalse(any(b['editable'] for b in rows))

    def test_small_empty_runtime_does_not_resurrect_defaults(self):
        self.runtime.side_effect = None
        self.runtime.return_value = []
        self.assertEqual(scanner.build()['items'], [])

    def test_fallback_replays_unbind_order_and_disables_edits(self):
        self.bindings.write_text('o.bind("SUPER + J", "Removed", "true")\nhl.unbind("SUPER + J")\n')
        self.runtime.side_effect = None
        self.runtime.return_value = None
        view = scanner.build()
        self.assertIn('read-only', view['error'])
        self.assertFalse(any(b['editable'] for b in view['items']))
        self.assertFalse(any(b['key'] == 'SUPER + J' and not b['disabled'] for b in view['items']))

    def test_corrupt_state_is_visible_error(self):
        for content in ['{broken', '[]', '{"version": 1, "overrides": null}', '{"version": 2, "overrides": [null]}']:
            self.state.write_text(content)
            result = scanner.build()
            self.assertTrue(result['error'])
            self.assertEqual(result['items'], [])

    def test_missing_state_with_existing_block_is_not_empty_state(self):
        self.bindings.write_text(updater.managed_block([entry()]))
        self.assertTrue(scanner.build()['error'])


class EditingTests(ConfigFixture):
    def test_edit_delete_restore_round_trip(self):
        updater.apply_request(self.request())
        updater.apply_request(self.request(key='SUPER + G', operation='delete'))
        deleted = next(b for b in scanner.build()['items'] if b['key'] == 'SUPER + G')
        self.assertTrue(deleted['disabled'])
        updater.apply_request(self.request(key='SUPER + G', operation='restore', new_key='SUPER + J', disabled=True))
        self.assertTrue(any(b.key == 'SUPER + J' and b.description == 'Example' for b in self.live()))
        state = store.load_state(self.state)
        self.assertEqual(state['version'], 2)
        self.assertEqual(len(state['overrides']), 1)
        self.assertEqual(state['overrides'][0]['action'], '"true"')

    def test_unrelated_override_survives_reused_origin(self):
        updater.apply_request(self.request())
        updater.apply_request(self.request(key='SUPER + H', new_key='SUPER + F'))
        updater.apply_request(self.request(key='SUPER + G', new_key='SUPER + J'))
        active = {(b.key, b.description) for b in self.live()}
        self.assertIn(('SUPER + F', 'Other'), active)
        self.assertIn(('SUPER + J', 'Example'), active)

    def test_conflict_requires_explicit_consent(self):
        request = self.request(new_key='SUPER + H')
        with self.assertRaisesRegex(ValueError, 'occupied'):
            updater.apply_request(request)
        self.assertFalse(self.state.exists())
        request['replace'] = True
        updater.apply_request(request)
        self.assertIn(('SUPER + H', 'Example'), {(b.key, b.description) for b in self.live()})

    def test_deleted_key_is_free_and_restoration_preserves_its_new_owner(self):
        updater.apply_request(self.request(operation='delete'))
        updater.apply_request(self.request(key='SUPER + H', new_key='SUPER + F'))
        request = self.request(key='SUPER + F', operation='restore', new_key='SUPER + F', disabled=True)
        with self.assertRaisesRegex(ValueError, 'occupied'):
            updater.apply_request(request)
        request['new_key'] = 'SUPER + J'
        updater.apply_request(request)
        self.assertEqual({(b.key, b.description) for b in self.live()},
                         {('SUPER + F', 'Other'), ('SUPER + J', 'Example')})

    def test_replaced_managed_binding_is_kept_as_restorable_deletion(self):
        updater.apply_request(self.request())
        updater.apply_request(self.request(key='SUPER + H', new_key='SUPER + G', replace=True))
        deleted = [b for b in scanner.build()['items'] if b['disabled']]
        self.assertEqual([b['description'] for b in deleted], ['Example'])
        request = self.request(key='SUPER + G', operation='restore', new_key='SUPER + G', disabled=True, replace=True)
        with self.assertRaisesRegex(ValueError, 'occupied'):
            updater.apply_request(request)
        request['new_key'] = 'SUPER + J'
        updater.apply_request(request)
        self.assertEqual(len([b for b in self.live() if b.key in ('SUPER + G', 'SUPER + J')]), 2)

    def test_stale_snapshot_refuses_write(self):
        request = self.request()
        self.bindings.write_text('-- changed externally\n')
        with self.assertRaisesRegex(ValueError, 'changed since'):
            updater.apply_request(request)
        self.assertEqual(self.bindings.read_text(), '-- changed externally\n')

    def test_corrupt_state_never_discards_existing_overrides(self):
        updater.apply_request(self.request())
        original = self.bindings.read_bytes()
        request = self.request(key='SUPER + G')
        self.state.write_text('{broken')
        with self.assertRaises(ValueError):
            updater.apply_request(request)
        self.assertEqual(self.bindings.read_bytes(), original)

    def test_manual_managed_block_edit_is_detected(self):
        updater.apply_request(self.request())
        self.bindings.write_text(self.bindings.read_text().replace('"true"', '"false"'))
        self.assertTrue(scanner.build()['error'])

    def test_legacy_state_recovers_toggle_type_and_options(self):
        self.default_source = 'o.bind_toggle("SUPER + F", "Example", "bar", { locked = true })\n'
        (self.defaults / 'basic.lua').write_text(self.default_source)
        legacy = entry(action='"bar"')
        legacy.pop('call')
        legacy.pop('options')
        self.state.write_text(json.dumps({'version': 1, 'overrides': [legacy]}))
        self.bindings.write_text(store.BEGIN + '\nhl.unbind("SUPER + F")\no.bind("SUPER + G", "Example", "bar")\n' + store.END + '\n')
        updater.apply_request(self.request(key='SUPER + G', new_key='SUPER + J'))
        result = store.load_state(self.state)['overrides'][0]
        self.assertEqual(result['call'], 'o.bind_toggle')
        self.assertEqual(result['options'], '{ locked = true }')

    def test_unrecoverable_legacy_state_blocks_writes(self):
        legacy = entry(description='No source')
        legacy.pop('call')
        legacy.pop('options')
        self.state.write_text(json.dumps({'version': 1, 'overrides': [legacy]}))
        self.bindings.write_text(updater.managed_block([entry(description='No source')]))
        self.assertTrue(scanner.build()['error'])


class TransactionTests(ConfigFixture):
    def test_reload_failure_rolls_back_without_exposing_error_contents(self):
        before = self.bindings.read_bytes()
        self.validation.side_effect = [ValueError('test-secret'), None]
        with self.assertRaisesRegex(ValueError, 'rolled back') as error:
            updater.apply_request(self.request())
        self.assertNotIn('test-secret', str(error.exception))
        self.assertEqual(self.bindings.read_bytes(), before)
        self.assertFalse(self.state.exists())

    def test_state_write_failure_rolls_back_bindings(self):
        before = self.bindings.read_bytes()
        real_write = store.atomic_write
        def fail_state(path, content):
            if path == self.state:
                raise OSError('test-secret')
            return real_write(path, content)
        with mock.patch.object(store, 'atomic_write', side_effect=fail_state), self.assertRaisesRegex(ValueError, 'rolled back'):
            updater.apply_request(self.request())
        self.assertEqual(self.bindings.read_bytes(), before)

    def test_backup_paths_are_unique_and_private(self):
        first = updater.apply_request(self.request())['backup']
        second = updater.apply_request(self.request(key='SUPER + G', new_key='SUPER + J'))['backup']
        self.assertNotEqual(first, second)
        self.assertEqual(Path(first).read_text(), '-- personal\n')
        self.assertEqual(stat.S_IMODE(Path(first).stat().st_mode), 0o600)

    def test_symlink_target_updated_and_link_retained(self):
        target = self.base / 'dotfiles.lua'
        self.bindings.rename(target)
        self.bindings.symlink_to(target)
        updater.apply_request(self.request())
        self.assertTrue(self.bindings.is_symlink())
        self.assertIn(store.BEGIN, target.read_text())

    def test_mutations_are_serialized(self):
        with store.mutation_lock(self.state):
            with self.assertRaisesRegex(ValueError, 'Another shortcut operation'):
                updater.apply_request(self.request())

    def test_external_edit_during_validation_is_not_overwritten(self):
        def external_edit():
            self.bindings.write_text('-- concurrent edit\n')
        self.validation.side_effect = external_edit
        with self.assertRaisesRegex(ValueError, 'concurrently'):
            updater.apply_request(self.request())
        self.assertEqual(self.bindings.read_text(), '-- concurrent edit\n')

    def test_reset_failure_preserves_original_file_and_state(self):
        updater.apply_request(self.request())
        before, state_before = self.bindings.read_bytes(), self.state.read_bytes()
        self.validation.side_effect = [ValueError('invalid'), None]
        with mock.patch.object(sys, 'stdout', io.StringIO()):
            self.assertEqual(resetter.main(), 1)
        self.assertEqual(self.bindings.read_bytes(), before)
        self.assertEqual(self.state.read_bytes(), state_before)

    def test_reset_uses_selected_config_root_and_preserves_state_symlink(self):
        updater.apply_request(self.request())
        target = self.base / 'state-target.json'
        self.state.rename(target)
        self.state.symlink_to(target)
        with mock.patch.object(sys, 'stdout', io.StringIO()):
            self.assertEqual(resetter.main(), 0)
        self.assertEqual(self.bindings.read_bytes(), self.shipped.read_bytes())
        self.assertTrue(self.state.is_symlink())
        self.assertEqual(store.load_state(self.state)['overrides'], [])

    def test_cleanup_preserves_other_bytes_and_handles_bad_state(self):
        self.bindings.write_bytes(b'-- Personal\r\n\r\n')
        updater.apply_request(self.request())
        self.state.write_text('{broken')
        with mock.patch.object(sys, 'stdout', io.StringIO()):
            self.assertEqual(cleaner.main(), 0)
        self.assertEqual(self.bindings.read_bytes(), b'-- Personal\r\n\r\n\n')
        self.assertEqual(store.load_state(self.state)['overrides'], [])


class PrivacyTests(unittest.TestCase):
    def test_malformed_requests_do_not_echo_input(self):
        for value in ['test-secret', '[]', '{"action": "test-secret"}', 'x' * 9000]:
            with mock.patch.object(sys, 'stdin', io.StringIO(value)), mock.patch.object(sys, 'stdout', new_callable=io.StringIO) as output:
                self.assertEqual(updater.main(), 2)
                self.assertNotIn('test-secret', output.getvalue())
                self.assertFalse(json.loads(output.getvalue())['ok'])

    def test_process_arguments_contain_no_request_data(self):
        command = [sys.executable, str(ROOT / 'update_shortcut.py')]
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            try:
                process.stdin.write('{"action": "test-secret"}')
                process.stdin.flush()
                argv = Path(f'/proc/{process.pid}/cmdline').read_bytes()
                self.assertNotIn(b'test-secret', argv)
                output, errors = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 2)
                self.assertNotIn('test-secret', output + errors)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()


@unittest.skipUnless(shutil.which('qs'), 'Quickshell needed for QML stdin integration')
class QmlTransportTests(unittest.TestCase):
    def test_actual_panel_transport_across_three_operations(self):
        # Exercise the actual transport code from Panel.qml in an isolated shell;
        # only read_request runs in Python, never a configuration mutation.
        panel = (ROOT / 'Panel.qml').read_text()
        start = re.search(r'  function startUpdate\(.*?\n  }', panel, re.S).group()
        started = re.search(r'    onStarted: \{.*?\n    }', panel, re.S).group()
        with tempfile.TemporaryDirectory(prefix='omakeybinds-transport-') as directory:
            path = Path(directory)
            helper = path / 'read_request.py'
            helper.write_text('import sys, json\nsys.path.insert(0, ' + repr(str(ROOT)) + ')\n'
                              'from update_shortcut import read_request\nprint(json.dumps(read_request()))\n')
            qml = '''import QtQuick
import Quickshell
import Quickshell.Io
ShellRoot {
  id: root
  property var editItem: ({ token: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" })
  property string editSnapshot: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  property bool conflictAccepted: false
  property int completed: 0
  property bool valid: false
  property var operations: ["edit", "delete", "restore"]
  __START_FUNCTION__
  Component.onCompleted: startUpdate("SUPER + F", operations[completed])
  Process {
    id: updater
    property string payload: ""
    command: ["python3", __HELPER__]
    __STARTED_HANDLER__
    stdout: StdioCollector {
      onStreamFinished: {
        const data = JSON.parse(text)
        root.valid = data.token === root.editItem.token && data.snapshot === root.editSnapshot
          && data.operation === root.operations[root.completed] && data.new_key === "SUPER + F" && data.replace === false
      }
    }
    onExited: (code, status) => {
      if (code !== 0 || !root.valid) { console.error("TRANSPORT_FAILED"); Qt.quit(); return }
      root.completed++
      if (root.completed === 3) { console.log("TRANSPORT_PASSED"); Qt.quit() }
      else { root.valid = false; Qt.callLater(function() { root.startUpdate("SUPER + F", root.operations[root.completed]) }) }
    }
  }
}'''
            qml = qml.replace('__START_FUNCTION__', start).replace('__STARTED_HANDLER__', started).replace('__HELPER__', json.dumps(str(helper)))
            (path / 'shell.qml').write_text(qml)
            environment = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_QPA_PLATFORMTHEME': 'basic',
                           'XDG_RUNTIME_DIR': directory, 'XDG_CONFIG_HOME': directory, 'XDG_CACHE_HOME': directory}
            result = subprocess.run(['qs', '-p', str(path / 'shell.qml'), '--no-color'],
                                    env=environment, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('TRANSPORT_PASSED', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
