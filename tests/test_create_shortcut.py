"""New shortcut tests; configuration mutations use temporary fixtures only."""
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import create_shortcut as creator
import scan_shortcuts as scanner
import shortcut_actions as actions
import shortcut_store as store
import update_shortcut as updater
from shortcut_model import literal_string
from test_shortcut_tools import ConfigFixture


class ApplicationsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.user = self.root / 'user'
        self.system = self.root / 'system'
        self.environment = mock.patch.dict(os.environ, {
            'XDG_DATA_HOME': str(self.user), 'XDG_DATA_DIRS': str(self.system),
            'XDG_CURRENT_DESKTOP': 'Hyprland', 'LC_ALL': 'sv_SE.UTF-8',
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def desktop(self, root, name='example.desktop', content='Name=Example\nExec=example %U\n'):
        path = root / 'applications' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[Desktop Entry]\nType=Application\n' + content)
        return path

    def test_user_precedence_and_hidden_mask(self):
        self.desktop(self.system)
        self.desktop(self.user, content='Hidden=true\n')
        self.assertEqual(actions.applications(), [])
        self.desktop(self.user, content='Name=Personal\nExec=example\n')
        self.assertEqual(actions.applications()[0]['name'], 'Personal')

    def test_localized_names_nested_ids_and_unescaped_text(self):
        self.desktop(self.user, 'vendor/example.desktop', 'Name=Example\nName[sv_SE]=Öppna\\sapp\nExec=example %U\nTerminal=true\n')
        app = actions.applications()[0]
        self.assertEqual(app['id'], 'vendor-example.desktop')
        self.assertEqual(app['name'], 'Öppna app')
        self.assertTrue(app['terminal'])

    def test_filters_and_malformed_entries(self):
        for number, extra in enumerate(['Hidden=true', 'NoDisplay=true', 'OnlyShowIn=KDE;',
                                        'NotShowIn=Hyprland;', 'TryExec=omakeybinds-no-such-executable',
                                        'Name=Duplicate']):
            self.desktop(self.user, f'{number}.desktop', 'Name=Example\nExec=example\n' + extra + '\n')
        self.assertEqual(actions.applications(), [])

    def test_same_root_ambiguous_ids_and_action_suffixes_excluded(self):
        self.desktop(self.user, 'vendor-example.desktop')
        self.desktop(self.user, 'vendor/example.desktop')
        self.desktop(self.user, 'example:action.desktop')
        self.assertEqual(actions.applications(), [])

    def test_prepare_uses_launcher_not_exec_and_tracks_changes(self):
        path = self.desktop(self.user, content='Name=Example\nExec=example "quoted value" %U\nTerminal=true\nPath=/tmp\n')
        with mock.patch.object(actions.shutil, 'which', return_value='/usr/bin/uwsm-app'):
            target = dict(type='app', value='example.desktop', description='')
            result = actions.prepare(target)
            self.assertEqual(result['command'], 'uwsm-app -- example.desktop')
            self.assertIn('terminal', result['detail'])
            path.write_text(path.read_text().replace('quoted value', 'changed'))
            self.assertNotEqual(actions.prepare(target)['token'], result['token'])
            path.unlink()
            with self.assertRaisesRegex(ValueError, 'no longer available'):
                actions.prepare(target)


class ActionTests(unittest.TestCase):
    def test_websites_are_shell_quoted(self):
        url = 'https://example.com/?q=$(touch${IFS}/tmp/no)&x=\'hello\''
        with mock.patch.object(actions.shutil, 'which', return_value='/usr/bin/xdg-open'):
            result = actions.prepare(dict(type='website', value=url, description=''))
        self.assertEqual(shlex.split(result['command']), ['xdg-open', url])
        self.assertEqual(literal_string(result['spec']['action']), result['command'])

    def test_invalid_websites_rejected(self):
        for url in ['javascript:alert(1)', 'file:///etc/passwd', 'ftp://example.com', 'https://',
                    'https://user:secret@example.com', 'https://example.com/with space', 'https://[bad',
                    'https://example.com:bad']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                actions.prepare(dict(type='website', value=url, description=''))

    def test_folder_paths_with_spaces_quotes_and_unicode(self):
        with tempfile.TemporaryDirectory(prefix="Ö folder's ") as directory:
            with mock.patch.object(actions.shutil, 'which', return_value='/usr/bin/xdg-open'):
                result = actions.prepare(dict(type='folder', value=directory, description='My files'))
            self.assertEqual(shlex.split(result['command']), ['xdg-open', directory])
            self.assertEqual(result['description'], 'My files')
        with self.assertRaises(ValueError):
            actions.prepare(dict(type='folder', value=directory, description=''))

    def test_command_is_only_data_during_preparation(self):
        with mock.patch.object(subprocess, 'run', side_effect=AssertionError('Must not execute')):
            command = 'printf "%s" "Ö $HOME" && echo "done"'
            result = actions.prepare(dict(type='command', value=command, description='My command'))
            self.assertEqual(literal_string(result['spec']['action']), command)

    def test_review_name_is_editable_without_changing_action_token(self):
        target = dict(type='command', value='true', description='')
        original = actions.prepare(target)
        renamed = actions.prepare({**target, 'description': 'My shortcut'})
        self.assertEqual(original['token'], renamed['token'])
        self.assertEqual(renamed['description'], 'My shortcut')
        self.assertNotEqual(original['token'], actions.prepare({**target, 'value': 'false'})['token'])

    def test_invalid_targets_do_not_echo_private_values(self):
        for target in [None, {}, {'type': 'command', 'value': 'SECRET\ncommand', 'description': ''},
                       {'type': 'command', 'value': 'SECRET', 'description': 'x' * 161},
                       {'type': 'command', 'value': '\0SECRET', 'description': ''}]:
            with self.assertRaises(ValueError) as caught:
                actions.prepare(target)
            self.assertNotIn('SECRET', str(caught.exception))

    def test_strict_request_schema_and_bounds(self):
        for request in [dict(operation='bad', target={}), dict(operation='prepare', target={}, extra=True),
                        dict(operation='create', target={}, snapshot='a'*64, token='b'*64, new_key=[], replace=False)]:
            with mock.patch.object(sys, 'stdin', io.StringIO(json.dumps(request))), self.assertRaises(ValueError):
                creator.read_request()
        with mock.patch.object(sys, 'stdin', io.StringIO('x' * 32769)), self.assertRaises(ValueError):
            creator.read_request()


class CreationTests(ConfigFixture):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(mock.patch.object(creator, 'BINDINGS', self.bindings))
        self.stack.enter_context(mock.patch.object(creator, 'STATE', self.state))

    def create_request(self, key='SUPER + J', replace=False, description='New command'):
        target = dict(type='command', value='printf "%s" "hello"', description=description)
        prepared = creator.apply_request(dict(operation='prepare', target=target))
        return dict(operation='create', target=target, token=prepared['token'], snapshot=scanner.build()['snapshot'],
                    new_key=key, replace=replace)

    def test_add_edit_delete_restore_and_added_marker(self):
        creator.apply_request(self.create_request())
        row = next(item for item in scanner.build()['items'] if item['key'] == 'SUPER + J')
        self.assertTrue(row['created'])
        self.assertEqual(row['status'], 'custom')
        updater.apply_request(self.request(key='SUPER + J', new_key='SUPER + K'))
        updater.apply_request(self.request(key='SUPER + K', operation='delete'))
        updater.apply_request(self.request(key='SUPER + K', operation='restore', new_key='SUPER + L', disabled=True))
        row = next(item for item in scanner.build()['items'] if item['key'] == 'SUPER + L')
        self.assertTrue(row['created'])
        self.assertFalse(row['disabled'])

    def test_conflict_consent_and_displaced_managed_action(self):
        request = self.create_request('SUPER + F')
        with self.assertRaisesRegex(ValueError, 'occupied'):
            creator.apply_request(request)
        self.assertFalse(self.state.exists())
        request['replace'] = True
        creator.apply_request(request)
        creator.apply_request(self.create_request('SUPER + F', True, 'Replacement'))
        rows = scanner.build()['items']
        self.assertTrue(any(row['description'] == 'New command' and row['disabled'] for row in rows))
        self.assertEqual(len([row for row in rows if row['key'] == 'SUPER + F' and not row['disabled']]), 1)

    def test_read_only_and_physical_alias_conflicts_refused(self):
        for source, key in [('o.bind("SUPER + J", "Dynamic", local_helper())\n', 'SUPER + J'),
                            ('o.bind("SUPER + code:10", "Physical", "true")\n', 'SUPER + 1')]:
            self.bindings.write_text(source)
            with self.assertRaisesRegex(ValueError, 'read-only or physical-key'):
                creator.apply_request(self.create_request(key, True))
            self.assertEqual(self.bindings.read_text(), source)

    def test_snapshot_or_action_change_refuses_without_write(self):
        request = self.create_request()
        request['target']['value'] = 'changed command'
        with self.assertRaisesRegex(ValueError, 'action or app launcher changed'):
            creator.apply_request(request)
        request = self.create_request()
        self.bindings.write_text('-- changed\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            creator.apply_request(request)
        self.assertFalse(self.state.exists())

    def test_no_runtime_never_allows_creation(self):
        self.runtime.side_effect = None
        self.runtime.return_value = None
        with self.assertRaisesRegex(ValueError, 'Live bindings'):
            creator.apply_request(self.create_request())
        self.assertFalse(self.state.exists())

    def test_prepare_does_not_write_or_reload(self):
        before = self.bindings.read_bytes()
        self.create_request()
        self.assertEqual(self.bindings.read_bytes(), before)
        self.assertFalse(self.state.exists())
        self.validation.assert_not_called()

    def test_name_can_be_changed_on_review_before_saving(self):
        request = self.create_request()
        request['target']['description'] = 'Renamed on review'
        creator.apply_request(request)
        self.assertTrue(any(row['description'] == 'Renamed on review' for row in scanner.build()['items']))

    def test_new_shortcut_failure_rolls_back(self):
        before = self.bindings.read_bytes()
        self.validation.side_effect = [ValueError('private command error'), None]
        with self.assertRaisesRegex(ValueError, 'rolled back'):
            creator.apply_request(self.create_request())
        self.assertEqual(self.bindings.read_bytes(), before)
        self.assertFalse(self.state.exists())


@unittest.skipUnless(shutil.which('qs') and Path('/usr/share/omarchy/shell/Commons').is_dir(), 'Quickshell and Omarchy shell required')
class DialogTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY'), 'Wayland backend required to compile PanelWindow')
    def test_actual_panel_component_compiles(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='omakeybinds-panel-') as directory:
            path = Path(directory)
            for source in Path('/usr/share/omarchy/shell').iterdir():
                if source.is_dir():
                    (path / source.name).symlink_to(source, target_is_directory=True)
            (path / 'shell.qml').write_text('''import QtQuick
import Quickshell
ShellRoot {
  Timer {
    interval: 1
    running: true
    onTriggered: {
    var component = Qt.createComponent(__PANEL__)
    if (component.status === Component.Ready) console.log("PANEL_COMPILED")
    else console.error(component.errorString())
    Qt.quit()
    }
  }
}'''.replace('__PANEL__', json.dumps((repo / 'Panel.qml').as_uri())))
            # Compile only, without instantiating the panel or showing a window.
            # PanelWindow's type registration needs a Wayland connection even
            # when the component is not instantiated; offscreen has no backend.
            display = str(Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / os.environ['WAYLAND_DISPLAY'])
            environment = {**os.environ, 'QT_QPA_PLATFORM': 'wayland', 'WAYLAND_DISPLAY': display, 'QT_QPA_PLATFORMTHEME': 'basic',
                           'XDG_RUNTIME_DIR': directory, 'XDG_CONFIG_HOME': directory, 'XDG_CACHE_HOME': directory}
            result = subprocess.run(['qs', '-p', str(path / 'shell.qml'), '--no-color'],
                                    env=environment, capture_output=True, text=True, timeout=15)
            self.assertIn('PANEL_COMPILED', result.stdout + result.stderr)

    def test_full_dialog_prepare_capture_conflict_and_save_transport(self):
        self.run_dialog_flow('command')

    def test_app_row_selection_advances_and_focuses_capture(self):
        self.run_dialog_flow('app')

    def test_search_enter_advances_and_back_can_select_again(self):
        self.run_dialog_flow('keyboard')

    def test_missing_app_shows_error_on_selection_page(self):
        self.run_dialog_flow('missing')

    def test_super_ctrl_shift_d_conflict_and_unprotected_capture(self):
        self.run_dialog_flow('occupied')

    def test_typed_combination_checks_conflicts_without_capture_protection(self):
        self.run_dialog_flow('typed')

    def run_dialog_flow(self, mode):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='omakeybinds-dialog-') as directory:
            path = Path(directory)
            (path / 'Commons').symlink_to('/usr/share/omarchy/shell/Commons', target_is_directory=True)
            (path / 'Ui').symlink_to('/usr/share/omarchy/shell/Ui', target_is_directory=True)
            shutil.copy(repo / 'ShortcutEntry.qml', path)
            desktop_dir = path / 'data/applications'
            desktop_dir.mkdir(parents=True)
            (desktop_dir / 'HLTV.desktop').write_text('[Desktop Entry]\nType=Application\nName=HLTV\nExec=true\n')
            shutil.copyfile(repo / 'AddShortcut.qml', path / 'AddShortcut.qml')
            # The actual dialog sends to a harmless helper that parses real
            # request schemas. No writes, compositor reloads, or launches.
            (path / 'create_shortcut.py').write_text(
                'import sys, json\nsys.path.insert(0, ' + repr(str(repo)) + ')\n'
                'from create_shortcut import read_request\nfrom shortcut_actions import prepare\n'
                'try:\n'
                '    request = read_request()\n    result = prepare(request["target"])\n'
                '    if request["operation"] == "create":\n'
                '        assert request["token"] == result["token"]\n'
                '        assert request["new_key"] == ' + repr('SUPER + CTRL + SHIFT + D' if mode == 'occupied' else 'SUPER + J') + '\n'
                '        assert request["replace"] is True\n'
                '        assert request["target"]["description"] == "My test shortcut"\n'
                '    result.pop("spec")\n    print(json.dumps({"ok": True, **result}))\n'
                'except ValueError as error:\n    print(json.dumps({"ok": False, "message": str(error)}))\n')
            fixture_id = 'missing.desktop' if mode == 'missing' else 'HLTV.desktop'
            (path / 'shortcut_actions.py').write_text('print(' + repr(json.dumps({'apps': [
                {'id': fixture_id, 'name': 'HLTV', 'icon': '', 'comment': 'Test app'}], 'error': ''})) + ')\n')
            (path / 'shell.qml').write_text('''import QtQuick
import Quickshell
ShellRoot {
  id: shell
  property int phase: 0
  property string testMode: __MODE__
  property bool wentBack: false
  function child(item, name) {
    if (item.objectName === name) return item
    for (var i = 0; item.children && i < item.children.length; i++) {
      var found = child(item.children[i], name)
      if (found) return found
    }
    return null
  }
  QtObject {
    id: host
    property bool captureProtected: true
    property color foreground: "#eeeeee"
    property color muted: "#aaaaaa"
    property color surface: "#222222"
    property string fontFamily: "sans-serif"
    property string occupiedKey: shell.testMode === "occupied" ? "SUPER + CTRL + SHIFT + D" : "SUPER + J"
    property var shortcuts: [{key: occupiedKey, displayKey: occupiedKey, description: "Existing", editable: true, disabled: false}]
    function alpha(c, a) { var v = Qt.color(c); return Qt.rgba(v.r, v.g, v.b, a) }
    function statusColor(s) { return "#58c7f3" }
    function keyName(event) { return String.fromCharCode(event.key) }
  }
  FloatingWindow {
    visible: true
    implicitWidth: 760
    implicitHeight: 670
    AddShortcut {
      id: dialog
      anchors.fill: parent
      host: host
      onSaved: { console.log("DIALOG_PASSED"); Qt.quit() }
    }
  }
  Timer {
    interval: 50
    repeat: true
    running: true
    onTriggered: {
      if (shell.phase === 0) {
        dialog.open("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        if (shell.testMode === "command" || shell.testMode === "occupied") {
          dialog.chooseKind(3)
          shell.child(dialog, "actionValue").text = "printf '%s' 'hello'"
          dialog.review()
          shell.phase = 1
        } else shell.phase = 10
      } else if (shell.phase === 10 && !dialog.appsLoading) {
        shell.child(dialog, "appSearch").text = "hlt"
        shell.phase = 11
      } else if (shell.phase === 11) {
        if (shell.child(dialog, "addShortcutCard").height > 440) { console.error("DIALOG_TOO_TALL"); Qt.quit(); return }
        if (shell.testMode === "keyboard") shell.child(dialog, "appSearch").accepted()
        else {
          var row = shell.child(dialog, "appChoice:" + (shell.testMode === "missing" ? "missing.desktop" : "HLTV.desktop"))
          if (!row) return
          if (__PICKER_SCREENSHOT__ && shell.testMode === "app")
            dialog.grabToImage(function(result) { result.saveToFile(__PICKER_SCREENSHOT__); row.activated() })
          else row.activated()
        }
        shell.phase = 1
      } else if (shell.phase === 1 && dialog.step === 1 && !dialog.busy) {
        if (!dialog.prepared) { console.error("PREPARE_FAILED"); Qt.quit(); return }
        if (!shell.child(dialog, "keyCapture").activeFocus) { console.error("CAPTURE_NOT_FOCUSED"); Qt.quit(); return }
        if (shell.testMode === "keyboard" && !shell.wentBack) {
          shell.wentBack = true
          dialog.back()
          shell.phase = 11
          return
        }
        shell.child(dialog, "actionDescription").text = "My test shortcut"
        if (shell.testMode === "occupied") {
          host.captureProtected = false
          dialog.capture({key: Qt.Key_D, modifiers: Qt.MetaModifier | Qt.ControlModifier | Qt.ShiftModifier, accepted: false})
          if (dialog.key !== "" || dialog.canSave || !dialog.message) { console.error("UNPROTECTED_CAPTURE"); Qt.quit(); return }
          host.captureProtected = true
        }
        if (shell.testMode === "typed") {
          host.captureProtected = false
          var entry = shell.child(dialog, "typedShortcut")
          entry.text = "super + j"
          entry.textEdited()
        } else dialog.capture({key: shell.testMode === "occupied" ? Qt.Key_D : Qt.Key_J,
          modifiers: Qt.MetaModifier | (shell.testMode === "occupied" ? Qt.ControlModifier | Qt.ShiftModifier : 0), accepted: false})
        if (dialog.canSave || dialog.conflicts.length !== 1) { console.error("CONFLICT_FAILED"); Qt.quit(); return }
        dialog.replaceAccepted = true
        if (!dialog.canSave) { console.error("CONSENT_FAILED"); Qt.quit(); return }
        shell.phase = 2
        if (__SCREENSHOT__) screenshotDelay.start()
        else dialog.save()
      } else if (dialog.message) {
        if (shell.testMode === "missing" && dialog.step === 0 && !dialog.busy && dialog.message.indexOf("no longer available") !== -1) console.log("DIALOG_PASSED")
        else console.error("DIALOG_FAILED " + dialog.message)
        Qt.quit()
      }
    }
  }
  Timer {
    id: screenshotDelay
    interval: 200
    onTriggered: dialog.grabToImage(function(result) { result.saveToFile(__SCREENSHOT__); dialog.save() })
  }
  Timer { interval: 8000; running: true; onTriggered: { console.error("DIALOG_TIMEOUT"); Qt.quit() } }
}'''.replace('__MODE__', json.dumps(mode))
                .replace('__PICKER_SCREENSHOT__', json.dumps(os.environ.get('OMAKEYBINDS_TEST_PICKER_SCREENSHOT', '')))
                .replace('__SCREENSHOT__', json.dumps(os.environ.get('OMAKEYBINDS_TEST_SCREENSHOT', ''))))
            environment = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_QPA_PLATFORMTHEME': 'basic',
                           'XDG_RUNTIME_DIR': directory, 'XDG_CONFIG_HOME': directory, 'XDG_CACHE_HOME': directory,
                           'XDG_DATA_HOME': str(path / 'data'), 'XDG_DATA_DIRS': str(path / 'empty-data')}
            result = subprocess.run(['qs', '-p', str(path / 'shell.qml'), '--no-color'],
                                    env=environment, capture_output=True, text=True, timeout=15)
            diagnostics = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, diagnostics)
            self.assertIn('DIALOG_PASSED', diagnostics)
            self.assertNotIn('ReferenceError:', diagnostics)
            self.assertNotIn('TypeError:', diagnostics)
            self.assertNotIn('Binding loop', diagnostics)


if __name__ == '__main__':
    unittest.main()
