import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Dialogs
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui as Ui

FocusScope {
  id: root
  required property var host
  signal dismissed()
  signal saved()
  property bool busy: false
  property bool appsLoading: false
  property var apps: []
  property var selectedApp: null
  property var prepared: null
  property var target: null
  property string snapshot: ""
  property string key: ""
  property string message: ""
  property int step: 0
  property int kindIndex: 0
  property bool replaceAccepted: false
  property bool commandExpanded: false
  readonly property color accent: Color.accent
  readonly property string kind: ["app", "website", "folder", "command"][kindIndex]
  readonly property var matchingApps: apps.filter(function(app) {
    return (app.name + " " + app.id + " " + app.comment).toLowerCase().indexOf(appSearch.text.toLowerCase()) !== -1
  })
  readonly property var conflicts: host.shortcuts.filter(function(item) {
    return !item.disabled && (item.key === root.key || item.displayKey === root.key)
  })
  readonly property bool unsafeConflict: conflicts.some(function(item) { return !item.editable || item.key !== root.key })
  readonly property bool captureProtected: host.captureProtected === true
  readonly property bool canSave: key !== "" && !busy && !unsafeConflict && (!conflicts.length || replaceAccepted)
  readonly property string helperPath: decodeURIComponent(Qt.resolvedUrl("create_shortcut.py").toString().replace(/^file:\/\//, ""))
  readonly property string appsPath: decodeURIComponent(Qt.resolvedUrl("shortcut_actions.py").toString().replace(/^file:\/\//, ""))
  focus: visible
  Keys.onEscapePressed: cancel()
  onMatchingAppsChanged: appList.currentIndex = matchingApps.length ? 0 : -1
  onStepChanged: body.contentY = 0

  component Label: Text {
    textFormat: Text.PlainText
    color: root.host.foreground
    font.family: root.host.fontFamily
    font.pixelSize: Style.font.body
    wrapMode: Text.WordWrap
  }

  component AppIcon: Rectangle {
    property string iconName: ""
    property string fallback: "↗"
    width: Style.space(40)
    height: width
    radius: Style.cornerRadius
    color: root.host.alpha(root.host.foreground, 0.055)
    Image {
      id: appImage
      anchors.fill: parent
      anchors.margins: Style.space(7)
      source: parent.iconName.indexOf(":") !== -1 ? "" : parent.iconName.charAt(0) === "/"
        ? "file://" + parent.iconName : Quickshell.iconPath(parent.iconName || "application-x-executable", true)
      fillMode: Image.PreserveAspectFit
    }
    Label {
      anchors.centerIn: parent
      visible: appImage.status !== Image.Ready
      text: parent.fallback
      color: root.accent
      font.pixelSize: Style.font.title
    }
  }

  component ActionButton: Ui.Button {
    foreground: root.host.foreground
    accent: root.accent
    fontFamily: root.host.fontFamily
    focusable: true
    bordered: true
    opacity: enabled ? 1 : 0.4
    height: Math.max(implicitHeight, Style.space(34))
  }

  component Field: Ui.TextField {
    foreground: root.host.foreground
    accent: root.accent
    font.family: root.host.fontFamily
    selectByMouse: true
  }

  function open(snapshotValue) {
    snapshot = snapshotValue
    step = 0
    prepared = null
    target = null
    selectedApp = null
    kindIndex = 0
    appSearch.text = ""
    valueField.text = ""
    descriptionField.text = ""
    key = ""
    typedShortcut.editing = false
    message = ""
    replaceAccepted = false
    commandExpanded = false
    if (!catalog.running) { appsLoading = true; catalog.running = true }
    Qt.callLater(function() { appSearch.forceActiveFocus() })
  }

  function cancel() { if (!busy) dismissed() }

  function chooseKind(index) {
    if (busy) return
    kindIndex = index
    valueField.text = ""
    descriptionField.text = ""
    selectedApp = null
    message = ""
    Qt.callLater(function() { (root.kind === "app" ? appSearch : valueField).forceActiveFocus() })
  }

  function chooseApp(app) {
    if (busy || !app) return
    selectedApp = app
    descriptionField.text = ""
    review()
  }

  function chooseCurrentApp() {
    if (appList.currentIndex >= 0 && appList.currentIndex < matchingApps.length)
      chooseApp(matchingApps[appList.currentIndex])
  }

  function moveAppCursor(delta) {
    if (!matchingApps.length) return
    appList.currentIndex = Math.max(0, Math.min(matchingApps.length - 1, appList.currentIndex + delta))
    appList.positionViewAtIndex(appList.currentIndex, ListView.Contain)
  }

  function back() {
    if (busy) return
    step = 0
    message = ""
    Qt.callLater(function() { (root.kind === "app" ? appSearch : valueField).forceActiveFocus() })
  }

  function send(request) {
    if (busy || helper.running) return
    busy = true
    message = ""
    helper.payload = JSON.stringify(request)
    helper.stdinEnabled = true
    helper.running = true
  }

  function review() {
    if (busy) return
    if (kind === "app" && !selectedApp) { message = "Select an installed app first."; return }
    target = { type: kind, value: kind === "app" ? selectedApp.id : valueField.text, description: "" }
    send({ operation: "prepare", target: target })
  }

  function save() {
    if (!canSave || !prepared) return
    // Only the label is editable here; the action remains fingerprinted.
    var finalTarget = { type: target.type, value: target.value, description: descriptionField.text }
    send({ operation: "create", target: finalTarget, snapshot: snapshot, token: prepared.token, new_key: key, replace: replaceAccepted })
  }

  function capture(event) {
    if (event.key === Qt.Key_Escape) { cancel(); event.accepted = true; return }
    if (busy) { event.accepted = true; return }
    if (!captureProtected) {
      message = "Protected key capture is unavailable. Do not press a global shortcut; close and reopen the dialog."
      event.accepted = true
      return
    }
    // Keep Tab available for navigation to the name and buttons.
    if ((event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab)
        && !(event.modifiers & (Qt.MetaModifier | Qt.ControlModifier | Qt.AltModifier))) return
    var name = host.keyName(event)
    if (!name) return
    var parts = []
    if (event.modifiers & Qt.MetaModifier) parts.push("SUPER")
    if (event.modifiers & Qt.ControlModifier) parts.push("CTRL")
    if (event.modifiers & Qt.AltModifier) parts.push("ALT")
    if (event.modifiers & Qt.ShiftModifier) parts.push("SHIFT")
    parts.push(name)
    key = parts.join(" + ")
    replaceAccepted = false
    message = ""
    event.accepted = true
  }

  Process {
    id: catalog
    command: ["python3", root.appsPath]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var result = JSON.parse(text)
          root.apps = result.apps || []
          if (result.error) root.message = result.error
        } catch (error) { root.message = "Could not read installed apps. Close and reopen to retry." }
        root.appsLoading = false
      }
    }
  }

  Process {
    id: helper
    property string payload: ""
    command: ["python3", root.helperPath]
    onStarted: { write(payload); stdinEnabled = false; payload = "" }
    stdout: StdioCollector {
      onStreamFinished: {
        root.busy = false
        try {
          var result = JSON.parse(text)
          if (!result.ok) { root.message = result.message || "Could not save the shortcut."; return }
          if (root.step === 0) {
            root.prepared = result
            descriptionField.text = result.description
            root.commandExpanded = root.kind === "command"
            root.step = 1
            Qt.callLater(function() { captureBox.forceActiveFocus() })
          } else root.saved()
        } catch (error) { root.message = "Could not read the result. Rescan shortcuts before retrying." }
      }
    }
  }

  FolderDialog {
    id: folderPicker
    title: "Choose a folder for the shortcut"
    onAccepted: {
      valueField.text = decodeURIComponent(selectedFolder.toString().replace(/^file:\/\//, ""))
      root.review()
    }
  }

  Rectangle {
    anchors.fill: parent
    color: root.host.alpha(root.host.surface, 0.88)
    MouseArea { anchors.fill: parent; onClicked: root.cancel() }
  }

  Ui.BorderSurface {
    id: card
    objectName: "addShortcutCard"
    anchors.centerIn: parent
    width: Math.min(parent.width - Style.space(36), Style.space(560))
    height: Math.min(parent.height - Style.space(32), header.implicitHeight + bodyColumn.implicitHeight + footer.implicitHeight + Style.space(76))
    radius: Style.cornerRadius
    color: root.host.surface
    borderSpec: Border.flat(root.host.alpha(root.host.foreground, 0.18), Style.normalBorderWidth)
    MouseArea { anchors.fill: parent; onClicked: {} }

    Column {
      id: header
      anchors { left: parent.left; right: parent.right; top: parent.top; margins: Style.space(20) }
      spacing: Style.space(7)
      Row {
        width: parent.width
        Label {
          width: parent.width - stepLabel.implicitWidth
          text: root.step === 0 ? "Add shortcut" : "Set your shortcut"
          font.pixelSize: Style.font.title * 1.12
          font.bold: true
        }
        Label {
          id: stepLabel
          text: root.step === 0 ? "1 / 2" : "2 / 2"
          color: root.host.muted
          font.pixelSize: Style.font.caption
        }
      }
      Label {
        width: parent.width
        text: root.step === 0 ? "What would you like to open?" : "Give this action a home on your keyboard."
        color: root.host.muted
        font.pixelSize: Style.font.caption
      }
    }

    Flickable {
      id: body
      anchors { top: header.bottom; bottom: footer.top; left: parent.left; right: parent.right; margins: Style.space(18) }
      contentHeight: bodyColumn.implicitHeight
      boundsBehavior: Flickable.StopAtBounds
      clip: true
      QQC.ScrollBar.vertical: QQC.ScrollBar {}

      Column {
        id: bodyColumn
        width: body.width - Style.space(4)
        spacing: Style.space(12)

        Column {
          width: parent.width
          spacing: Style.space(14)
          visible: root.step === 0
          enabled: !root.busy

          Row {
            width: parent.width
            spacing: Style.space(6)
            Repeater {
              model: ["App", "Website", "Folder", "Command"]
              delegate: ActionButton {
                required property string modelData
                required property int index
                width: (parent.width - parent.spacing * 3) / 4
                text: modelData
                bordered: false
                selected: root.kindIndex === index
                background: root.host.alpha(root.host.foreground, 0.035)
                height: Style.space(40)
                onClicked: root.chooseKind(index)
              }
            }
          }

          Field {
            id: appSearch
            objectName: "appSearch"
            width: parent.width
            visible: root.kind === "app"
            placeholderText: "Search installed apps…"
            maximumLength: 160
            Accessible.name: "Search installed applications"
            onAccepted: root.chooseCurrentApp()
            Keys.onDownPressed: root.moveAppCursor(1)
            Keys.onUpPressed: root.moveAppCursor(-1)
          }

          Row {
            width: parent.width
            visible: root.kind === "app" && !root.appsLoading
            Label {
              width: parent.width - appCount.implicitWidth
              text: appSearch.text ? "Matching applications" : "Installed applications"
              color: root.host.muted
              font.pixelSize: Style.font.body * 0.9
            }
            Label {
              id: appCount
              text: root.matchingApps.length
              color: root.host.muted
              font.pixelSize: Style.font.body * 0.9
            }
          }

          ListView {
            id: appList
            objectName: "appList"
            width: parent.width
            height: Math.min(Style.space(232), Math.max(Style.space(56), count * Style.space(56)))
            visible: root.kind === "app"
            model: root.matchingApps
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            spacing: Style.space(2)
            QQC.ScrollBar.vertical: QQC.ScrollBar {}
            delegate: Ui.CursorSurface {
              id: appRow
              required property var modelData
              required property int index
              objectName: "appChoice:" + modelData.id
              signal activated()
              width: appList.width - Style.space(8)
              height: Style.space(54)
              foreground: root.host.foreground
              accent: root.accent
              hasCursor: appList.currentIndex === index
              activeFocusOnTab: true
              Accessible.role: Accessible.Button
              Accessible.name: "Choose " + modelData.name
              Accessible.onPressAction: activated()
              onActivated: root.chooseApp(modelData)
              onActiveFocusChanged: if (activeFocus) appList.currentIndex = index
              Keys.onReturnPressed: activated()
              Keys.onEnterPressed: activated()
              Keys.onSpacePressed: activated()
              Row {
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: Style.space(10) }
                spacing: Style.space(12)
                AppIcon {
                  width: Style.space(36)
                  anchors.verticalCenter: parent.verticalCenter
                  iconName: modelData.icon
                }
                Column {
                  width: parent.width - Style.space(70)
                  spacing: Style.space(3)
                  Label { width: parent.width; text: modelData.name; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                  Label { width: parent.width; text: modelData.comment || "Open application"; elide: Text.ElideRight; wrapMode: Text.NoWrap; color: root.host.muted; font.pixelSize: Style.font.body * 0.9 }
                }
                Label { text: "›"; anchors.verticalCenter: parent.verticalCenter; color: root.host.muted }
              }
              MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onEntered: appList.currentIndex = appRow.index
                onClicked: appRow.activated()
              }
            }
            Label {
              anchors.centerIn: parent
              width: parent.width
              visible: root.appsLoading || appList.count === 0
              text: root.appsLoading ? "Reading installed apps…" : "No matches. Try another name or a custom command."
              color: root.host.muted
              horizontalAlignment: Text.AlignHCenter
              font.pixelSize: Style.font.caption
            }
          }

          Field {
            id: valueField
            objectName: "actionValue"
            width: parent.width
            visible: root.kind !== "app"
            placeholderText: root.kind === "website" ? "https://example.com" : root.kind === "folder" ? "~/Documents" : "Command to run"
            maximumLength: 4096
            Accessible.name: "Shortcut action"
            onAccepted: root.review()
          }
          ActionButton { visible: root.kind === "folder"; text: "Choose folder…"; onClicked: folderPicker.open() }
          Label {
            width: parent.width
            visible: root.kind !== "app"
            text: root.kind === "command" ? "Advanced: runs with your user permissions. Only use commands you understand."
              : root.kind === "website" ? "Opens in your default browser." : "Opens in your default file manager."
            color: root.host.muted
            font.pixelSize: Style.font.caption
          }
        }

        Column {
          width: parent.width
          spacing: Style.space(12)
          visible: root.step === 1
          enabled: !root.busy
          Row {
            width: parent.width
            spacing: Style.space(12)
            AppIcon {
              iconName: root.kind === "app" && root.selectedApp ? root.selectedApp.icon : ""
              fallback: root.kind === "command" ? ">_" : root.kind === "folder" ? "/" : "↗"
            }
            Column {
              anchors.verticalCenter: parent.verticalCenter
              width: parent.width - Style.space(52)
              spacing: Style.space(4)
              Label {
                width: parent.width
                text: root.kind === "app" && root.selectedApp ? root.selectedApp.name : root.prepared ? root.prepared.description : ""
                font.bold: true
                font.pixelSize: Style.font.body * 1.15
              }
              Label {
                width: parent.width
                text: root.kind === "app" ? "Launch application" : root.kind === "website" ? "Open in your browser" : root.kind === "folder" ? "Open in your file manager" : "Run custom command"
                color: root.host.muted
                font.pixelSize: Style.font.body * 0.9
              }
            }
          }
          FocusScope {
            id: captureBox
            objectName: "keyCapture"
            width: parent.width
            height: Style.space(120)
            activeFocusOnTab: true
            Keys.onPressed: event => root.capture(event)
            Ui.BorderSurface {
              anchors.fill: parent
              radius: Style.cornerRadius
              color: root.host.alpha(root.accent, captureBox.activeFocus ? 0.065 : 0.025)
              borderSpec: Border.flat(root.host.alpha(root.accent, captureBox.activeFocus ? 0.48 : 0.16), Style.normalBorderWidth)
              Column {
                anchors.centerIn: parent
                width: parent.width - Style.space(24)
                spacing: Style.space(14)
                Item {
                  width: parent.width
                  height: Style.space(40)
                  Row {
                    id: keycaps
                    anchors.centerIn: parent
                    scale: Math.min(1, parent.width / Math.max(1, implicitWidth))
                    spacing: Style.space(8)
                    Repeater {
                      model: root.key ? root.key.split(" + ") : ["SUPER", "SHIFT", "?"]
                      delegate: Row {
                        required property string modelData
                        required property int index
                        spacing: Style.space(8)
                        Rectangle {
                          width: keycapText.implicitWidth + Style.space(24)
                          height: Style.space(40)
                          radius: Style.cornerRadius
                          color: root.host.alpha(root.host.foreground, root.key ? 0.10 : 0.035)
                          border.width: 1
                          border.color: root.host.alpha(root.host.foreground, root.key ? 0.25 : 0.12)
                          Label {
                            id: keycapText
                            anchors.centerIn: parent
                            text: modelData === "SUPER" ? "Super" : modelData === "CTRL" ? "Ctrl" : modelData === "SHIFT" ? "Shift" : modelData === "ALT" ? "Alt" : modelData
                            color: root.key ? root.host.foreground : root.host.muted
                            font.pixelSize: Style.font.body * 1.12
                            font.bold: root.key !== ""
                          }
                        }
                        Label {
                          visible: index < (root.key ? root.key.split(" + ").length : 3) - 1
                          text: "+"
                          color: root.host.muted
                          anchors.verticalCenter: parent.verticalCenter
                        }
                      }
                    }
                  }
                }
                Label {
                  width: parent.width
                  text: !root.captureProtected ? "Waiting for protected capture — do not press shortcut keys yet"
                    : !captureBox.activeFocus ? "Click here to record a key combination"
                    : root.key ? "Press another combination to change it" : "Press the keys you want to use"
                  color: root.host.muted
                  horizontalAlignment: Text.AlignHCenter
                  font.pixelSize: Style.font.body * 0.9
                }
              }
              MouseArea { anchors.fill: parent; onClicked: captureBox.forceActiveFocus() }
            }
          }
          ShortcutEntry {
            id: typedShortcut
            width: parent.width
            host: root.host
            value: root.key
            enabled: !root.busy
            onSelected: function(combination) {
              root.key = combination
              root.replaceAccepted = false
              root.message = ""
            }
          }
          Label {
            width: parent.width
            visible: root.key !== "" && root.key.indexOf(" + ") === -1 && !/^F\d+$/.test(root.key)
            text: "Unmodified keys can intercept normal typing. Consider adding Super, Ctrl, or Alt."
            color: root.host.muted
            font.pixelSize: Style.font.caption
          }
          Column {
            width: parent.width
            spacing: Style.space(6)
            Label { text: "Name"; color: root.host.muted; font.pixelSize: Style.font.body * 0.9 }
            Field {
              id: descriptionField
              objectName: "actionDescription"
              width: parent.width
              placeholderText: "Suggested automatically"
              maximumLength: 160
              Accessible.name: "Shortcut name"
            }
          }
          ActionButton {
            text: root.commandExpanded ? "▾  Hide command" : "▸  Show command"
            bordered: false
            foreground: root.host.muted
            horizontalPadding: 0
            height: implicitHeight
            onClicked: root.commandExpanded = !root.commandExpanded
          }
          Label {
            width: parent.width
            visible: root.commandExpanded
            text: root.prepared ? root.prepared.command : ""
            color: root.host.muted
            font.pixelSize: Style.font.caption
            wrapMode: Text.WrapAnywhere
          }
          Label {
            width: parent.width
            visible: root.conflicts.length > 0
            text: "Already used by: " + root.conflicts.map(function(item) { return item.description }).join("; ")
              + (root.unsafeConflict ? ". Choose another combination; this binding cannot be safely replaced." : "")
            color: Color.urgent
            font.pixelSize: Style.font.caption
          }
          Ui.Toggle {
            visible: root.conflicts.length > 0 && !root.unsafeConflict
            width: parent.width
            label: "Replace existing shortcut"
            foreground: root.host.foreground
            accent: root.accent
            fontFamily: root.host.fontFamily
            titleSize: Style.font.body
            checked: root.replaceAccepted
            onClicked: root.replaceAccepted = !root.replaceAccepted
          }
          Label {
            width: parent.width
            text: "Nothing is launched until you use the shortcut."
            color: root.host.muted
            font.pixelSize: Style.font.caption
          }
        }
      }
    }

    Column {
      id: footer
      anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: Style.space(20) }
      spacing: Style.space(12)
      Label {
        width: parent.width
        visible: root.message !== "" || root.busy
        text: root.message || (root.step === 0 ? "Preparing shortcut…" : "Saving shortcut…")
        color: root.message ? Color.urgent : root.host.muted
        font.pixelSize: Style.font.caption
      }
      Rectangle { width: parent.width; height: 1; color: root.host.alpha(root.host.foreground, 0.12) }
      Row {
        width: parent.width
        spacing: Style.space(8)
        ActionButton { id: cancelButton; text: "Cancel"; bordered: false; foreground: root.host.muted; enabled: !root.busy; onClicked: root.cancel() }
        Item { width: Math.max(0, parent.width - cancelButton.width - (backButton.visible ? backButton.width + parent.spacing : 0) - (nextButton.visible ? nextButton.width + parent.spacing : 0) - parent.spacing); height: 1 }
        ActionButton { id: backButton; text: "Back"; bordered: false; visible: root.step === 1; enabled: !root.busy; onClicked: root.back() }
        ActionButton {
          id: nextButton
          visible: root.step === 1 || root.kind !== "app"
          text: root.busy ? "Working…" : root.step === 0 ? "Continue →" : root.conflicts.length ? "Replace and add" : "Save shortcut"
          bordered: false
          color: enabled ? root.host.alpha(root.accent, hot ? 0.85 : 1) : root.host.alpha(root.host.foreground, 0.08)
          foreground: enabled ? root.host.surface : root.host.muted
          enabled: root.step === 0 ? !root.busy && valueField.text.trim() !== "" : root.canSave
          onClicked: root.step === 0 ? root.review() : root.save()
        }
      }
    }
  }
}
