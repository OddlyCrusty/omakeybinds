import QtQuick
import qs.Commons
import qs.Ui as Ui

// An alternative to chord recording: ordinary text entry never needs to
// invoke the global combination that the user is trying to assign.
Column {
  id: root
  required property var host
  property string value: ""
  property bool editing: false
  property bool updating: false
  property bool valid: true
  signal selected(string combination)
  spacing: Style.space(5)

  function normalize(text) {
    var modifiers = ["SUPER", "CTRL", "ALT", "SHIFT"]
    var tokens = text.toUpperCase().split("+").map(function(token) { return token.trim().replace(/^CONTROL$/, "CTRL") })
    var keys = tokens.filter(function(token) { return modifiers.indexOf(token) === -1 })
    if (keys.length !== 1 || !/^[A-Z0-9_:]+$/.test(keys[0])) return ""
    var key = keys[0]
    if (/^(CODE|MOUSE):[0-9]+$|^MOUSE_(UP|DOWN|LEFT|RIGHT)$/.test(key)) key = key.toLowerCase()
    return modifiers.filter(function(modifier) { return tokens.indexOf(modifier) !== -1 }).concat([key]).join(" + ")
  }

  function syncValue() {
    if (updating) return
    entry.text = value
    valid = true
  }
  onValueChanged: syncValue()
  Component.onCompleted: syncValue()

  Ui.Button {
    text: root.editing ? "▾  Type a combination" : "▸  Type a combination instead"
    foreground: root.host.muted
    fontFamily: root.host.fontFamily
    horizontalPadding: 0
    focusable: true
    onClicked: {
      root.editing = !root.editing
      if (root.editing) Qt.callLater(function() { entry.forceActiveFocus(); entry.selectAll() })
    }
  }
  Ui.TextField {
    id: entry
    objectName: "typedShortcut"
    visible: root.editing
    width: parent.width
    foreground: root.host.foreground
    font.family: root.host.fontFamily
    placeholderText: "SUPER + CTRL + SHIFT + D"
    Accessible.name: "Type shortcut combination"
    maximumLength: 100
    selectByMouse: true
    onTextEdited: {
      var combination = root.normalize(text)
      root.valid = combination !== ""
      root.updating = true
      root.selected(combination)
      root.updating = false
    }
  }
  Text {
    visible: root.editing
    width: parent.width
    textFormat: Text.PlainText
    text: root.valid ? "Type the names normally; do not hold the shortcut keys."
      : "Enter one key, optionally with SUPER, CTRL, ALT or SHIFT, separated by +."
    color: root.host.muted
    font.family: root.host.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.WordWrap
  }
}
