"""Capture regressions, including opt-in real Wayland key delivery."""
import os
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('qs'), 'Quickshell required')
class CaptureTests(unittest.TestCase):
    def test_typed_entry_normalizes_and_invalidates_incomplete_input(self):
        self.run_qml('''import QtQuick
import Quickshell
import "plugin" as Plugin
ShellRoot {
  id: test
  property string result: ""
  QtObject { id: host; property color foreground: "white"; property color muted: "gray"; property string fontFamily: "monospace" }
  Plugin.ShortcutEntry { id: entry; host: host; onSelected: combination => { test.result = combination; entry.value = combination } }
  Timer {
    interval: 1
    running: true
    onTriggered: {
      var cases = [["shift + control + super + d", "SUPER + CTRL + SHIFT + D"],
        ["super + code:10", "SUPER + code:10"], ["alt + mouse:272", "ALT + mouse:272"],
        ["super +", ""], ["super + a + b", ""], ["super + super + a", "SUPER + A"]]
      for (var pair of cases) {
        if (entry.normalize(pair[0]) !== pair[1]) { console.error("NORMALIZATION_FAILED"); Qt.quit(); return }
      }
      var field = entry.children[1]
      field.text = "control + super + d"; field.textEdited()
      if (test.result !== "SUPER + CTRL + D" || !entry.valid) { console.error("TYPED_VALUE_FAILED"); Qt.quit(); return }
      field.text = "SUPER +"; field.textEdited()
      if (test.result || entry.valid || field.text !== "SUPER +") { console.error("INVALID_INPUT_FAILED"); Qt.quit(); return }
      entry.value = "SUPER + J"
      if (field.text !== "SUPER + J" || !entry.valid) { console.error("RECORDED_SYNC_FAILED"); Qt.quit(); return }
      console.log("CAPTURE_PASSED"); Qt.quit()
    }
  }
}''', full_panel=True)

    def run_qml(self, source, wayland=False, full_panel=False):
        with tempfile.TemporaryDirectory(prefix='omakeybinds-capture-') as directory:
            path = Path(directory) / 'shell.qml'
            if full_panel:
                for entry in Path('/usr/share/omarchy/shell').iterdir():
                    if entry.is_dir():
                        (path.parent / entry.name).symlink_to(entry, target_is_directory=True)
                plugin = path.parent / 'plugin'
                plugin.mkdir()
                for entry in ROOT.glob('*.qml'):
                    shutil.copy(entry, plugin)
                panel = plugin / 'Panel.qml'
                panel.write_text(panel.read_text().replace('  id: root\n',
                    '  id: root\n  property alias testEntry: typedShortcut\n  property alias testAdd: addDialog\n', 1))
                dialog = plugin / 'AddShortcut.qml'
                dialog.write_text(dialog.read_text().replace('  id: root\n',
                    '  id: root\n  property alias testCapture: captureBox\n', 1))
                rows = [dict(key='SUPER + J', displayKey='SUPER + J', token='selected', description='Selected test action', disabled=False, editable=True),
                        dict(key='SUPER + CTRL + SHIFT + F35', displayKey='SUPER + CTRL + SHIFT + F35', token='occupied', description='Occupied test action', disabled=False, editable=True),
                        dict(key='SUPER + CTRL + SHIFT + F35', displayKey='SUPER + CTRL + SHIFT + F35', token='deleted', description='Deleted test action', disabled=True, editable=True),
                        dict(key='SUPER + F34', displayKey='SUPER + F34', token='free', description='Free deleted key', disabled=True, editable=True)]
                fixture = json.dumps(dict(items=rows, counts={}, snapshot='test', error=''))
                if os.environ.get('OMAKEYBINDS_CAPTURE_BOUND_KEY') == '1':
                    fixture = fixture.replace('F35', 'D')
                    source = source.replace('F35', 'D')
                (plugin / 'scan_shortcuts.py').write_text('print(' + repr(fixture) + ')')
            path.write_text(source)
            env = {**os.environ, 'QT_QPA_PLATFORM': 'wayland' if wayland else 'offscreen',
                   'QT_QPA_PLATFORMTHEME': 'basic', 'XDG_CONFIG_HOME': directory,
                   'XDG_CACHE_HOME': directory, 'XDG_RUNTIME_DIR': directory}
            if wayland:
                env['WAYLAND_DISPLAY'] = str(Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / os.environ['WAYLAND_DISPLAY'])
            result = subprocess.run(['qs', '-p', str(path), '--no-color'], env=env,
                                    capture_output=True, text=True, timeout=12)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('CAPTURE_PASSED', result.stdout + result.stderr)

    @unittest.skipUnless(os.environ.get('OMAKEYBINDS_WAYLAND_SMOKE') == '1' and shutil.which('wtype'),
                         'Opt-in real keyboard capture test')
    def test_full_editor_receives_real_keys_and_detects_conflict(self):
        # No mutation helper is copied: even a UI regression cannot save a binding.
        # F35 avoids launching a real application if capture fails.
        self.run_qml('''import QtQuick
import Quickshell
import Quickshell.Io
import "plugin" as Plugin
ShellRoot {
  id: test
  property int phase: 0
  function fail(message) { console.error(message); Qt.quit() }
  function typeCombination(text) {
    var entry = editor.testEntry.children[1]
    entry.text = text
    entry.textEdited()
  }
  Plugin.Panel { id: editor; visible: false }
  Process {
    id: typer
    command: ["wtype", "-M", "logo", "-M", "ctrl", "-M", "shift", "-k", "F35", "-m", "shift", "-m", "ctrl", "-m", "logo"]
    onExited: test.phase = test.phase === 20 ? 3 : 5
  }
  Timer {
    interval: 150
    running: true
    repeat: true
    onTriggered: {
      if (test.phase === 0) { editor.open(); test.phase = 1 }
      else if (test.phase === 1 && !editor.loading && editor.shortcuts.length) {
        editor.startEdit(editor.shortcuts[0]); test.phase = 2
      } else if (test.phase === 2 && editor.captureProtected) {
        test.phase = 20; typer.running = true
      } else if (test.phase === 3) {
        console.log("ACTUAL_KEY=" + editor.editKey)
        if (editor.editKey !== "SUPER + CTRL + SHIFT + F35" || editor.collisionFor(editor.editKey) !== "Occupied test action") {
          console.error("REAL_CAPTURE_FAILED"); Qt.quit(); return
        }
        editor.conflictAccepted = true
        test.typeCombination("shift + control + super + F35")
        if (editor.editKey !== "SUPER + CTRL + SHIFT + F35" || !editor.collisionFor(editor.editKey) || editor.conflictAccepted)
          { test.fail("TYPED_CONFLICT_FAILED"); return }
        test.typeCombination("SUPER + F34")
        if (editor.collisionFor(editor.editKey)) { test.fail("DELETED_KEY_NOT_FREE"); return }
        test.typeCombination("SUPER +")
        if (editor.editKey || editor.testEntry.valid) { test.fail("INVALID_TYPED_KEY_ACCEPTED"); return }
        editor.startEdit(editor.shortcuts[2])
        editor.restoreShortcut()
        if (editor.saving || !editor.editMessage || !editor.collisionFor(editor.editKey))
          { test.fail("RESTORE_DID_NOT_PROMPT"); return }
        test.typeCombination("SUPER + F34")
        if (editor.collisionFor(editor.editKey)) { test.fail("RESTORE_NEW_KEY_BLOCKED"); return }
        editor.cancelEdit()
        editor.addOpen = true
        editor.testAdd.step = 1
        Qt.callLater(function() { editor.testAdd.testCapture.forceActiveFocus() })
        test.phase = 4
      } else if (test.phase === 4 && editor.captureProtected) {
        test.phase = 40; typer.running = true
      } else if (test.phase === 5) {
        if (editor.testAdd.key !== "SUPER + CTRL + SHIFT + F35" || editor.testAdd.conflicts.length !== 1 || editor.testAdd.canSave)
          { test.fail("ADD_REAL_CONFLICT_FAILED"); return }
        console.log("CAPTURE_PASSED"); editor.close(); Qt.quit()
      }
    }
  }
  Timer { interval: 7000; running: true; onTriggered: { console.error("FULL_CAPTURE_TIMEOUT phase=" + test.phase); Qt.quit() } }
}''', wayland=True, full_panel=True)

    def test_existing_editor_capture_checks_google_drive_conflict(self):
        source = (ROOT / 'Panel.qml').read_text()
        functions = '\n'.join(re.search(r'  function ' + name + r'\(.*?\n  }', source, re.S).group()
                              for name in ('keyName', 'captureKey', 'collisionFor'))
        self.run_qml('''import QtQuick
import Quickshell
ShellRoot {
  id: root
  property bool saving: false
  property bool captureProtected: false
  property string editKey: "SUPER + J"
  property string editMessage: ""
  property bool conflictAccepted: true
  property string editMode: "edit"
  property var editItem: ({token: "selected"})
  property var shortcuts: [{key: "SUPER + CTRL + SHIFT + D", displayKey: "SUPER + CTRL + SHIFT + D", token: "drive", description: "Google Drive", disabled: false}]
  function cancelEdit() {}
  __FUNCTIONS__
  Timer {
    interval: 1
    running: true
    onTriggered: {
      var event = {key: Qt.Key_D, modifiers: Qt.MetaModifier | Qt.ControlModifier | Qt.ShiftModifier, accepted: false}
      root.captureKey(event)
      if (root.editKey !== "SUPER + J" || !root.editMessage) { console.error("UNPROTECTED_CAPTURE"); Qt.quit(); return }
      root.captureProtected = true
      root.captureKey(event)
      if (root.editKey !== "SUPER + CTRL + SHIFT + D" || root.collisionFor(root.editKey) !== "Google Drive" || root.conflictAccepted || !event.accepted) {
        console.error("CONFLICT_NOT_DETECTED"); Qt.quit(); return
      }
      console.log("CAPTURE_PASSED")
      Qt.quit()
    }
  }
}'''.replace('__FUNCTIONS__', functions))

    @unittest.skipUnless(os.environ.get('OMAKEYBINDS_WAYLAND_SMOKE') == '1' and os.environ.get('WAYLAND_DISPLAY'),
                         'Opt-in live Wayland protocol test')
    def test_live_inhibitor_activates_and_releases_for_both_dialogs(self):
        source = (ROOT / 'Panel.qml').read_text()
        inhibitor = re.search(r'  ShortcutInhibitor \{.*?\n  }', source, re.S).group()
        requested = re.search(r'  readonly property bool captureRequested:.*', source).group()
        focus = re.search(r'    WlrLayershell.keyboardFocus:.*\n.*', source).group()
        self.run_qml('''import QtQuick
import Quickshell
import Quickshell.Wayland
ShellRoot {
  id: root
  property bool opened: true
  property bool editOpen: false
  property bool addOpen: false
  property bool primed: false
  property int phase: 0
  QtObject { id: addDialog; property int step: 1 }
  QtObject { id: keyCapture; function forceActiveFocus() {} }
  __REQUESTED__
  __INHIBITOR__
  PanelWindow {
    id: panel
    property bool open: root.opened
    property bool focusPrimed: root.primed
    visible: root.opened
    implicitWidth: 420
    implicitHeight: 100
    color: "#202020"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "omakeybinds-capture-test"
    WlrLayershell.layer: WlrLayer.Overlay
    __FOCUS__
    Text { anchors.centerIn: parent; color: "white"; text: "OmaKeybinds: checking capture protection…" }
  }
  Timer { interval: 75; running: true; onTriggered: root.primed = true }
  Timer {
    interval: 100
    repeat: true
    running: true
    onTriggered: {
      if (root.phase === 0) { root.editOpen = true; root.phase = 1 }
      else if (root.phase === 1 && shortcutInhibitor.active) { root.editOpen = false; root.phase = 2 }
      else if (root.phase === 2 && !shortcutInhibitor.active) { root.addOpen = true; root.phase = 3 }
      else if (root.phase === 3 && shortcutInhibitor.active) { addDialog.step = 0; root.phase = 4 }
      else if (root.phase === 4 && !shortcutInhibitor.active) { addDialog.step = 1; root.phase = 5 }
      else if (root.phase === 5 && shortcutInhibitor.active) { root.opened = false; root.phase = 6 }
      else if (root.phase === 6 && !shortcutInhibitor.active) { console.log("CAPTURE_PASSED"); Qt.quit() }
    }
  }
  Timer { interval: 5000; running: true; onTriggered: { console.error("CAPTURE_TIMEOUT phase=" + root.phase); Qt.quit() } }
}'''.replace('__INHIBITOR__', inhibitor).replace('__REQUESTED__', requested).replace('__FOCUS__', focus), wayland=True)
