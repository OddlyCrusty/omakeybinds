import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "io.github.oddlycrusty.omakeybinds"
  ipcTarget: "io.github.oddlycrusty.omakeybinds"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color muted: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.62)
  readonly property color surface: Color.popups.background
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property string scannerPath: decodeURIComponent(Qt.resolvedUrl("scan_shortcuts.py").toString().replace(/^file:\/\//, ""))
  readonly property string updaterPath: decodeURIComponent(Qt.resolvedUrl("update_shortcut.py").toString().replace(/^file:\/\//, ""))
  readonly property string resetterPath: decodeURIComponent(Qt.resolvedUrl("reset_shortcuts.py").toString().replace(/^file:\/\//, ""))

  property var shortcuts: []
  property string scanSnapshot: ""
  property string editSnapshot: ""
  property var filteredShortcuts: []
  property var counts: ({ all: 0, default: 0, changed: 0, custom: 0, deleted: 0 })
  property string activeFilter: "all"
  property string query: ""
  property bool loading: false
  property string errorMessage: ""
  property bool editOpen: false
  property bool addOpen: false
  readonly property bool captureRequested: editOpen || (addOpen && addDialog.step === 1)
  readonly property bool captureProtected: shortcutInhibitor.active
  property string editMode: "edit"
  property var editItem: null
  property string editKey: ""
  property string editMessage: ""
  property bool saving: false
  property bool deleteConfirm: false
  property bool conflictAccepted: false
  property bool filterMenuOpen: false
  property bool settingsOpen: false
  property bool resetConfirmOpen: false
  property bool resetting: false
  property string resetMessage: ""

  readonly property var filters: [
    { key: "all", label: "All", menuLabel: "All shortcuts" },
    { key: "default", label: "Default", menuLabel: "Defaults only" },
    { key: "changed", label: "Changed", menuLabel: "Changed only" },
    { key: "custom", label: "Custom", menuLabel: "Custom only" },
    { key: "deleted", label: "Deleted", menuLabel: "Deleted only" }
  ]

  function alpha(c, a) {
    var col = Qt.color(c)
    return Qt.rgba(col.r, col.g, col.b, a)
  }

  function statusColor(status) {
    if (status === "changed") return "#f5b942"
    if (status === "custom") return "#58c7f3"
    if (status === "deleted") return "#ff6b6b"
    return "#7bd88f"
  }

  function filterCount(key) {
    return key === "all" ? counts.all : (counts[key] || 0)
  }

  function activeFilterLabel() {
    for (var i = 0; i < filters.length; i++)
      if (filters[i].key === activeFilter) return filters[i].menuLabel
    return "All shortcuts"
  }

  function applyFilters() {
    var needle = String(query || "").trim().toLowerCase()
    var output = []
    for (var i = 0; i < shortcuts.length; i++) {
      var item = shortcuts[i]
      if (activeFilter !== "all" && item.status !== activeFilter) continue
      var haystack = [item.key, item.displayKey, item.description, item.command, item.previous, item.source].join(" ").toLowerCase()
      if (needle && haystack.indexOf(needle) === -1) continue
      output.push(item)
    }
    filteredShortcuts = output
  }

  function refresh() {
    loading = true
    errorMessage = ""
    if (scanner.running) {
      scanner.rescanPending = true
      return
    }
    scanner.running = true
  }

  function startEdit(item) {
    if (!item || !item.editable || saving || resetting || loading) return
    editItem = item
    editSnapshot = scanSnapshot
    editMode = item.disabled ? "restore" : "edit"
    editKey = item.key
    editMessage = ""
    typedShortcut.editing = false
    conflictAccepted = false
    deleteConfirm = false
    editOpen = true
    Qt.callLater(function() { keyCapture.forceActiveFocus() })
  }

  function startAdd() {
    if (loading || saving || resetting || addDialog.busy || !scanSnapshot || errorMessage) return
    filterMenuOpen = false
    addOpen = true
    addDialog.open(scanSnapshot)
  }

  function cancelEdit() {
    if (saving) return
    editOpen = false
    editItem = null
    editMessage = ""
    conflictAccepted = false
    deleteConfirm = false
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function keyName(event) {
    if (event.key >= Qt.Key_A && event.key <= Qt.Key_Z) return String.fromCharCode(event.key)
    if (event.key >= Qt.Key_0 && event.key <= Qt.Key_9) return String.fromCharCode(event.key)
    var names = ({})
    names[Qt.Key_Return] = "RETURN"
    names[Qt.Key_Enter] = "RETURN"
    names[Qt.Key_Space] = "SPACE"
    names[Qt.Key_Tab] = "TAB"
    names[Qt.Key_Backspace] = "BACKSPACE"
    names[Qt.Key_Delete] = "DELETE"
    names[Qt.Key_Escape] = "ESCAPE"
    names[Qt.Key_Left] = "LEFT"
    names[Qt.Key_Right] = "RIGHT"
    names[Qt.Key_Up] = "UP"
    names[Qt.Key_Down] = "DOWN"
    names[Qt.Key_Home] = "HOME"
    names[Qt.Key_End] = "END"
    names[Qt.Key_PageUp] = "PAGEUP"
    names[Qt.Key_PageDown] = "PAGEDOWN"
    names[Qt.Key_Comma] = "COMMA"
    names[Qt.Key_Period] = "PERIOD"
    names[Qt.Key_Slash] = "SLASH"
    names[Qt.Key_Minus] = "MINUS"
    names[Qt.Key_Equal] = "EQUAL"
    if (event.key >= Qt.Key_F1 && event.key <= Qt.Key_F35) return "F" + (event.key - Qt.Key_F1 + 1)
    return names[event.key] || ""
  }

  function captureKey(event) {
    if (saving) { event.accepted = true; return }
    if (event.key === Qt.Key_Escape) {
      cancelEdit()
      event.accepted = true
      return
    }
    if (!captureProtected) {
      editMessage = "Protected key capture is unavailable. Do not press a global shortcut; close and reopen the editor."
      event.accepted = true
      return
    }
    if (event.key === Qt.Key_Shift || event.key === Qt.Key_Control || event.key === Qt.Key_Alt || event.key === Qt.Key_Meta)
      return
    var key = keyName(event)
    if (!key) return
    var parts = []
    if (event.modifiers & Qt.MetaModifier) parts.push("SUPER")
    if (event.modifiers & Qt.ControlModifier) parts.push("CTRL")
    if (event.modifiers & Qt.AltModifier) parts.push("ALT")
    if (event.modifiers & Qt.ShiftModifier) parts.push("SHIFT")
    parts.push(key)
    editKey = parts.join(" + ")
    editMessage = ""
    conflictAccepted = false
    event.accepted = true
  }

  function collisionFor(key) {
    var matches = []
    for (var i = 0; i < shortcuts.length; i++) {
      var item = shortcuts[i]
      if (!item.disabled && (item.key === key || item.displayKey === key) && (editMode === "restore" || !editItem || item.token !== editItem.token))
        matches.push(item.description || "Unnamed shortcut")
    }
    return matches.join("; ")
  }

  function applyEdit() {
    if (!editItem || !editKey || saving) return
    if (collisionFor(editKey) !== "" && !conflictAccepted) {
      editMessage = "Confirm that the existing shortcut may be replaced before applying."
      return
    }
    saving = true
    editMessage = ""
    startUpdate(editKey, "edit")
  }

  function restoreShortcut() {
    if (!editItem || !editKey || saving) return
    if (collisionFor(editKey) !== "") {
      editMessage = "That shortcut is already in use. Press another key combination to restore this action."
      return
    }
    saving = true
    editMessage = ""
    startUpdate(editKey, "restore")
  }

  function deleteShortcut() {
    if (!editItem || saving) return
    if (!deleteConfirm) {
      deleteConfirm = true
      editMessage = "Select Delete shortcut again to confirm."
      return
    }
    saving = true
    editMessage = ""
    startUpdate(editItem.key, "delete")
  }

  function startUpdate(newKey, operation) {
    updater.payload = JSON.stringify({
      token: editItem.token,
      snapshot: editSnapshot,
      new_key: newKey,
      operation: operation,
      replace: conflictAccepted
    })
    updater.stdinEnabled = true
    updater.running = true
  }

  function ingestUpdate(raw) {
    try {
      var result = JSON.parse(String(raw || ""))
      if (!result.ok) {
        editMessage = result.message || "The shortcut could not be changed."
        return
      }
      editOpen = false
      editItem = null
      conflictAccepted = false
      deleteConfirm = false
      refresh()
      Qt.callLater(function() { keyCatcher.forceActiveFocus() })
    } catch (error) {
      editMessage = "Could not read the update result: " + error
    } finally {
      saving = false
    }
  }

  function openSettings() {
    filterMenuOpen = false
    resetConfirmOpen = false
    resetMessage = ""
    settingsOpen = true
  }

  function closeSettings() {
    if (resetting) return
    settingsOpen = false
    resetConfirmOpen = false
    resetMessage = ""
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function resetAllShortcuts() {
    if (resetting) return
    resetting = true
    resetMessage = ""
    resetter.command = ["python3", resetterPath]
    resetter.running = true
  }

  function ingestReset(raw) {
    try {
      var result = JSON.parse(String(raw || ""))
      resetMessage = result.message || (result.ok ? "Shortcuts reset." : "Reset failed.")
      if (result.ok) {
        resetConfirmOpen = false
        activeFilter = "all"
        refresh()
      }
    } catch (error) {
      resetMessage = "Could not read the reset result: " + error
    } finally {
      resetting = false
    }
  }

  function ingest(raw) {
    try {
      var result = JSON.parse(String(raw || ""))
      shortcuts = result.items || []
      scanSnapshot = result.snapshot || ""
      counts = result.counts || ({ all: shortcuts.length, default: 0, changed: 0, custom: 0, deleted: 0 })
      errorMessage = result.error || ""
      applyFilters()
    } catch (error) {
      shortcuts = []
      scanSnapshot = ""
      counts = ({ all: 0, default: 0, changed: 0, custom: 0, deleted: 0 })
      filteredShortcuts = []
      errorMessage = "Could not read shortcut data: " + error
    }
    loading = false
  }

  function open() {
    refresh()
    root.controller.show()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function openFromHotkey() {
    open()
    Qt.callLater(function() {
      if (root.opened && root.bar && typeof root.bar.setCenterHoverRevealSuppressed === "function")
        root.bar.setCenterHoverRevealSuppressed(true)
    })
  }

  function close() {
    if (saving || resetting || addDialog.busy) return
    if (root.bar && typeof root.bar.setCenterHoverRevealSuppressed === "function")
      root.bar.setCenterHoverRevealSuppressed(false)
    searchField.focus = false
    filterMenuOpen = false
    editOpen = false
    editItem = null
    addOpen = false
    settingsOpen = false
    resetConfirmOpen = false
    root.controller.hide()
  }

  function toggle() { root.opened ? close() : open() }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  onQueryChanged: applyFilters()
  onActiveFilterChanged: {
    filterMenuOpen = false
    applyFilters()
  }

  Process {
    id: scanner
    property bool rescanPending: false
    command: ["python3", root.scannerPath]
    running: false
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.ingest(text)
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (text && !root.errorMessage) root.errorMessage = String(text).trim()
      }
    }
    onRunningChanged: {
      if (!running) {
        root.loading = false
        if (rescanPending) {
          rescanPending = false
          Qt.callLater(root.refresh)
        }
      }
    }
  }

  Process {
    id: resetter
    running: false
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.ingestReset(text)
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (text && root.settingsOpen && !root.resetMessage) root.resetMessage = String(text).trim()
      }
    }
    onRunningChanged: {
      if (!running && root.resetting && root.resetMessage) root.resetting = false
    }
  }

  Process {
    id: updater
    property string payload: ""
    command: ["python3", root.updaterPath]
    running: false
    onStarted: {
      write(payload)
      stdinEnabled = false
      payload = ""
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.ingestUpdate(text)
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (text && root.editOpen && !root.editMessage) root.editMessage = String(text).trim()
      }
    }
    onRunningChanged: {
      if (!running && root.saving && root.editMessage) root.saving = false
    }
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.openFromHotkey() }
    function close(): void { root.close() }
    function show(): void { root.openFromHotkey() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh() }
  }

  ShortcutInhibitor {
    id: shortcutInhibitor
    window: panel
    // Focus alone does not suppress compositor binds. Scope inhibition to the
    // editor surface and its visible dialogs; never alter global bindings.
    enabled: root.opened && root.captureRequested
    onActiveChanged: {
      if (active && root.editOpen) Qt.callLater(function() { if (root.editOpen) keyCapture.forceActiveFocus() })
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: false
    focusTarget: keyCatcher
    // Retain focus for recording, but preserve the shell's normal focus prime
    // while browsing. The app/folder picker is not a recording surface.
    WlrLayershell.keyboardFocus: !panel.open ? WlrKeyboardFocus.None
      : root.captureRequested || !panel.focusPrimed ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.OnDemand
    contentWidth: panel.fittedContentWidth(Style.space(760), Style.space(900))
    contentHeight: panel.fittedContentHeight(Style.space(670), Style.space(800))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: searchField.activeFocus || root.editOpen || root.settingsOpen || root.addOpen
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(text) {
        if (text === "/") {
          searchField.forceActiveFocus()
          searchField.selectAll()
        } else if (text === "r" || text === "R") root.refresh()
        else if (text >= "1" && text <= "5") root.activeFilter = root.filters[Number(text) - 1].key
      }

      Column {
        id: content
        anchors.fill: parent
        anchors.margins: Style.space(18)
        spacing: Style.space(12)

        Row {
          width: parent.width
          spacing: Style.space(10)

          OmaKeybindsLogo {
            id: headerLogo
            width: Style.space(34)
            height: Style.space(34)
            foreground: root.foreground
            accent: root.statusColor("custom")
          }

          Column {
            width: parent.width - headerLogo.width - addButton.width - refreshButton.width - settingsButton.width - parent.spacing * 4
            spacing: Style.space(3)
            Text {
              text: "OmaKeybinds"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
            }
            Text {
              text: root.loading ? "Scanning Hyprland bindings…" : root.counts.all + " shortcuts · compared with Omarchy defaults"
              color: root.muted
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }

          Button {
            id: addButton
            text: "+ Add"
            height: Style.space(34)
            foreground: root.foreground
            fontFamily: root.fontFamily
            bordered: true
            focusable: true
            enabled: !root.loading && !root.saving && !root.resetting && root.scanSnapshot !== "" && !root.errorMessage
            Accessible.name: "Add a new shortcut"
            onClicked: root.startAdd()
          }

          Rectangle {
            id: refreshButton
            width: Style.space(34)
            height: Style.space(34)
            radius: Style.cornerRadius
            color: refreshMouse.containsMouse ? root.alpha(root.foreground, 0.14) : root.alpha(root.foreground, 0.07)
            Text {
              anchors.centerIn: parent
              text: "󰑐"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.icon
            }
            MouseArea {
              id: refreshMouse
              anchors.fill: parent
              hoverEnabled: true
              onClicked: root.refresh()
            }
          }

          Rectangle {
            id: settingsButton
            width: Style.space(34)
            height: Style.space(34)
            radius: Style.cornerRadius
            color: settingsMouse.containsMouse ? root.alpha(root.foreground, 0.14) : root.alpha(root.foreground, 0.07)
            Text {
              anchors.centerIn: parent
              text: "⚙"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.icon
            }
            MouseArea {
              id: settingsMouse
              anchors.fill: parent
              hoverEnabled: true
              onClicked: root.openSettings()
            }
          }
        }

        Rectangle {
          width: parent.width
          height: Style.space(42)
          radius: Style.cornerRadius
          color: root.alpha(root.foreground, 0.065)
          border.width: searchField.activeFocus ? 1 : 0
          border.color: root.alpha(root.foreground, 0.35)

          Text {
            anchors.left: parent.left
            anchors.leftMargin: Style.space(13)
            anchors.verticalCenter: parent.verticalCenter
            text: "󰑍"
            color: root.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.icon
          }

          TextInput {
            id: searchField
            anchors.left: parent.left
            anchors.leftMargin: Style.space(42)
            anchors.right: clearSearch.left
            anchors.rightMargin: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            clip: true
            text: root.query
            onTextChanged: root.query = text
            Keys.onEscapePressed: {
              if (text) text = ""
              else {
                focus = false
                keyCatcher.forceActiveFocus()
              }
            }

            Text {
              anchors.fill: parent
              visible: !searchField.text && !searchField.activeFocus
              text: "Search keys, actions, commands…   /"
              color: root.muted
              font: searchField.font
              verticalAlignment: Text.AlignVCenter
            }
          }

          Text {
            id: clearSearch
            anchors.right: parent.right
            anchors.rightMargin: Style.space(13)
            anchors.verticalCenter: parent.verticalCenter
            visible: searchField.text !== ""
            text: "×"
            color: root.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            MouseArea { anchors.fill: parent; anchors.margins: -8; onClicked: searchField.text = "" }
          }
        }

        Item {
          id: filterBar
          width: parent.width
          height: Style.space(30)
          z: 20

          Row {
            id: filterPills
            anchors.left: parent.left
            spacing: Style.space(8)
            Repeater {
              model: root.filters
              delegate: Rectangle {
                required property var modelData
                readonly property bool selected: root.activeFilter === modelData.key
                width: filterLabel.implicitWidth + Style.space(22)
                height: Style.space(30)
                radius: height / 2
                color: selected ? root.alpha(root.statusColor(modelData.key), 0.20) : root.alpha(root.foreground, filterMouse.containsMouse ? 0.11 : 0.055)
                border.width: selected ? 1 : 0
                border.color: root.alpha(root.statusColor(modelData.key), 0.65)
                Text {
                  id: filterLabel
                  anchors.centerIn: parent
                  text: modelData.label + "  " + root.filterCount(modelData.key)
                  color: selected ? root.statusColor(modelData.key) : root.muted
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: selected
                }
                MouseArea {
                  id: filterMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  onClicked: root.activeFilter = modelData.key
                }
              }
            }
          }

          Rectangle {
            id: showFilterButton
            anchors.right: parent.right
            width: Style.space(158)
            height: Style.space(30)
            radius: Style.cornerRadius
            color: showFilterMouse.containsMouse || root.filterMenuOpen
              ? root.alpha(root.foreground, 0.12)
              : root.alpha(root.foreground, 0.06)
            border.width: root.filterMenuOpen ? 1 : 0
            border.color: root.alpha(root.foreground, 0.26)

            Text {
              anchors.left: parent.left
              anchors.leftMargin: Style.space(11)
              anchors.verticalCenter: parent.verticalCenter
              text: "Show: " + root.activeFilterLabel()
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
            }

            Text {
              anchors.right: parent.right
              anchors.rightMargin: Style.space(10)
              anchors.verticalCenter: parent.verticalCenter
              text: root.filterMenuOpen ? "▴" : "▾"
              color: root.muted
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }

            MouseArea {
              id: showFilterMouse
              anchors.fill: parent
              hoverEnabled: true
              onClicked: root.filterMenuOpen = !root.filterMenuOpen
            }

            Rectangle {
              id: filterMenu
              anchors.top: parent.bottom
              anchors.topMargin: Style.space(6)
              anchors.right: parent.right
              width: Style.space(178)
              height: filterMenuColumn.implicitHeight + Style.space(10)
              radius: Style.cornerRadius
              visible: root.filterMenuOpen
              z: 100
              color: root.surface
              border.width: 1
              border.color: root.alpha(root.foreground, 0.18)

              Column {
                id: filterMenuColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Style.space(5)

                Repeater {
                  model: root.filters
                  delegate: Rectangle {
                    required property var modelData
                    width: filterMenuColumn.width
                    height: Style.space(34)
                    radius: Style.space(6)
                    color: menuOptionMouse.containsMouse
                      ? root.alpha(root.foreground, 0.10)
                      : (root.activeFilter === modelData.key ? root.alpha(root.statusColor(modelData.key), 0.14) : "transparent")

                    Text {
                      anchors.left: parent.left
                      anchors.leftMargin: Style.space(10)
                      anchors.verticalCenter: parent.verticalCenter
                      text: (root.activeFilter === modelData.key ? "✓  " : "    ") + modelData.menuLabel
                      color: root.activeFilter === modelData.key ? root.statusColor(modelData.key) : root.foreground
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                      font.bold: root.activeFilter === modelData.key
                    }

                    Text {
                      anchors.right: parent.right
                      anchors.rightMargin: Style.space(10)
                      anchors.verticalCenter: parent.verticalCenter
                      text: root.filterCount(modelData.key)
                      color: root.muted
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                    }

                    MouseArea {
                      id: menuOptionMouse
                      anchors.fill: parent
                      hoverEnabled: true
                      onClicked: {
                        root.activeFilter = modelData.key
                        root.filterMenuOpen = false
                      }
                    }
                  }
                }
              }
            }
          }
        }

        Text {
          width: parent.width
          visible: root.errorMessage !== ""
          text: root.errorMessage
          textFormat: Text.PlainText
          color: "#ff9a9a"
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Rectangle {
          width: parent.width
          height: 1
          color: root.alpha(root.foreground, 0.10)
        }

        Item {
          width: parent.width
          height: Math.max(1, content.height - y)

          ListView {
            id: shortcutList
            anchors.fill: parent
            clip: true
            spacing: Style.space(7)
            model: root.filteredShortcuts
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
              required property var modelData
              width: shortcutList.width - Style.space(10)
              height: rowContent.implicitHeight + Style.space(20)
              radius: Style.cornerRadius
              color: rowMouse.containsMouse ? root.alpha(root.foreground, 0.085) : root.alpha(root.foreground, 0.045)

              Column {
                id: rowContent
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Style.space(10)
                spacing: Style.space(7)

                Row {
                  width: parent.width
                  spacing: Style.space(9)

                  Rectangle {
                    width: Math.min(Style.space(250), keyText.implicitWidth + Style.space(18))
                    height: Style.space(28)
                    radius: Style.space(6)
                    color: root.alpha(root.foreground, 0.09)
                    border.width: 1
                    border.color: root.alpha(root.foreground, 0.18)
                    Text {
                      id: keyText
                      anchors.centerIn: parent
                      text: modelData.displayKey || modelData.key
                      textFormat: Text.PlainText
                      color: root.foreground
                      font.family: "monospace"
                      font.pixelSize: Style.font.caption
                      font.bold: true
                    }
                  }

                  Text {
                    width: Math.max(1, parent.width - x - statusPill.width - parent.spacing)
                    height: Style.space(28)
                    text: modelData.description
                    textFormat: Text.PlainText
                    color: modelData.disabled ? root.muted : root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                    font.strikeout: modelData.disabled
                    font.bold: true
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                  }

                  Rectangle {
                    id: statusPill
                    width: statusText.implicitWidth + Style.space(14)
                    height: Style.space(22)
                    radius: height / 2
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.alpha(root.statusColor(modelData.status), 0.16)
                    Text {
                      id: statusText
                      anchors.centerIn: parent
                      text: modelData.disabled ? "DELETED" : modelData.created ? "ADDED BY YOU" : (modelData.status === "default" ? "DEFAULT" : "✦  " + String(modelData.status).toUpperCase())
                      color: root.statusColor(modelData.status)
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption * 0.88
                      font.bold: true
                    }
                  }
                }

                Text {
                  width: parent.width
                  visible: modelData.previous !== "" || modelData.command !== ""
                  text: modelData.previous !== ""
                    ? "Previously: " + modelData.previous
                    : modelData.command
                  textFormat: Text.PlainText
                  color: root.muted
                  font.family: modelData.previous !== "" ? root.fontFamily : "monospace"
                  font.pixelSize: Style.font.caption
                  elide: Text.ElideRight
                }
                Text {
                  width: parent.width
                  visible: !modelData.editable && !!modelData.reason
                  text: modelData.reason || ""
                  textFormat: Text.PlainText
                  color: root.muted
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                }
              }

              MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: modelData.editable ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: root.startEdit(modelData)
              }
            }

            Text {
              anchors.centerIn: parent
              visible: !root.loading && root.filteredShortcuts.length === 0
              text: root.errorMessage || "No shortcuts match this view."
              textFormat: Text.PlainText
              color: root.muted
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
              width: parent.width * 0.7
            }
          }
        }
      }
    }

    Item {
      anchors.fill: parent
      z: 50
      visible: root.editOpen

      Rectangle {
        anchors.fill: parent
        color: root.alpha("#000000", 0.62)
        MouseArea { anchors.fill: parent; onClicked: root.cancelEdit() }
      }

      Rectangle {
        width: Math.min(parent.width - Style.space(48), Style.space(500))
        height: editorColumn.implicitHeight + Style.space(36)
        anchors.centerIn: parent
        radius: Style.cornerRadius
        color: root.surface
        border.width: 1
        border.color: root.alpha(root.foreground, 0.18)
        MouseArea { anchors.fill: parent; onClicked: {} }

        Column {
          id: editorColumn
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.top: parent.top
          anchors.margins: Style.space(18)
          spacing: Style.space(12)

          Text {
            text: root.editMode === "restore" ? "Restore shortcut" : "Change shortcut"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }

          Text {
            width: parent.width
            text: root.editItem ? root.editItem.description : ""
            textFormat: Text.PlainText
            color: root.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            elide: Text.ElideRight
          }

          FocusScope {
            id: keyCapture
            width: parent.width
            height: Style.space(74)
            focus: root.editOpen
            Keys.onPressed: function(event) { root.captureKey(event) }

            Rectangle {
              anchors.fill: parent
              radius: Style.cornerRadius
              color: root.alpha(root.foreground, 0.07)
              border.width: keyCapture.activeFocus ? 2 : 1
              border.color: keyCapture.activeFocus ? root.statusColor("custom") : root.alpha(root.foreground, 0.18)

              Column {
                anchors.centerIn: parent
                spacing: Style.space(5)
                Text {
                  anchors.horizontalCenter: parent.horizontalCenter
                  text: !root.captureProtected ? "Waiting for protected capture…" : root.editKey || "Press a key combination"
                  textFormat: Text.PlainText
                  color: root.foreground
                  font.family: "monospace"
                  font.pixelSize: Style.font.title
                  font.bold: true
                }
                Text {
                  anchors.horizontalCenter: parent.horizontalCenter
                  text: !root.captureProtected ? "Do not press shortcut keys until capture is ready"
                    : !keyCapture.activeFocus ? "Click here to record a key combination"
                    : root.editMode === "restore" ? "Restore with this combination or press another" : "Press the replacement keys now"
                  color: root.muted
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }
              MouseArea { anchors.fill: parent; onClicked: keyCapture.forceActiveFocus() }
            }
          }

          ShortcutEntry {
            id: typedShortcut
            width: parent.width
            host: root
            value: root.editKey
            enabled: !root.saving
            onSelected: function(combination) {
              root.editKey = combination
              root.conflictAccepted = false
              root.editMessage = ""
            }
          }

          Text {
            width: parent.width
            visible: root.editKey !== "" && root.collisionFor(root.editKey) === ""
            text: root.editMode !== "restore" && root.editItem && root.editKey === root.editItem.key
              ? "Current combination for this action."
              : "Available — no active shortcut uses this combination."
            textFormat: Text.PlainText
            color: root.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }

          Rectangle {
            width: parent.width
            height: conflictColumn.implicitHeight + Style.space(24)
            visible: root.collisionFor(root.editKey) !== ""
            radius: Style.cornerRadius
            color: root.alpha("#ff6b6b", 0.11)
            border.width: 1
            border.color: root.alpha("#ff6b6b", 0.45)

            Column {
              id: conflictColumn
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.space(12)
              spacing: Style.space(8)

              Row {
                width: parent.width
                spacing: Style.space(9)
                Text {
                  text: "⚠"
                  color: "#ff6b6b"
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  font.bold: true
                }
                Column {
                  width: parent.width - x
                  spacing: Style.space(3)
                  Text {
                    text: "Shortcut conflict"
                    color: "#ff9a9a"
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                    font.bold: true
                  }
                  Text {
                    width: parent.width
                    text: root.editKey + " is already used by: " + root.collisionFor(root.editKey)
                      + (root.editMode === "restore" ? ". Press another key combination to continue." : "")
                    textFormat: Text.PlainText
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    wrapMode: Text.WordWrap
                  }
                }
              }

              Rectangle {
                width: parent.width
                height: Style.space(34)
                visible: root.editMode !== "restore"
                radius: Style.space(6)
                color: conflictMouse.containsMouse ? root.alpha(root.foreground, 0.10) : root.alpha(root.foreground, 0.055)

                Rectangle {
                  width: Style.space(18)
                  height: width
                  radius: Style.space(4)
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(9)
                  anchors.verticalCenter: parent.verticalCenter
                  color: root.conflictAccepted ? "#ff6b6b" : "transparent"
                  border.width: 1
                  border.color: root.conflictAccepted ? "#ff6b6b" : root.alpha(root.foreground, 0.42)
                  Text {
                    anchors.centerIn: parent
                    visible: root.conflictAccepted
                    text: "✓"
                    color: "white"
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    font.bold: true
                  }
                }

                Text {
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(38)
                  anchors.right: parent.right
                  anchors.rightMargin: Style.space(8)
                  anchors.verticalCenter: parent.verticalCenter
                  text: "Replace the existing shortcut"
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: root.conflictAccepted
                }

                MouseArea {
                  id: conflictMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  onClicked: {
                    root.conflictAccepted = !root.conflictAccepted
                    root.editMessage = ""
                  }
                }
              }
            }
          }

          Text {
            width: parent.width
            visible: root.editMessage !== ""
            text: root.editMessage
            textFormat: Text.PlainText
            color: "#ff6b6b"
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }

          Row {
            width: parent.width
            spacing: Style.space(9)

            Rectangle {
              id: deleteButton
              visible: root.editMode !== "restore"
              width: deleteLabel.implicitWidth + Style.space(24)
              height: Style.space(34)
              radius: Style.cornerRadius
              color: root.alpha("#ff6b6b", deleteMouse.containsMouse ? 0.32 : 0.20)
              border.width: 1
              border.color: root.alpha("#ff6b6b", 0.68)
              Text {
                id: deleteLabel
                anchors.centerIn: parent
                text: root.deleteConfirm ? "Confirm delete" : "Delete shortcut"
                color: "#ff9a9a"
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
              MouseArea {
                id: deleteMouse
                anchors.fill: parent
                hoverEnabled: true
                enabled: !root.saving
                onClicked: root.deleteShortcut()
              }
            }

            Item {
              width: Math.max(0, parent.width - (deleteButton.visible ? deleteButton.width : 0) - cancelButton.width - applyButton.width
                - Style.space(root.editMode === "restore" ? 18 : 27))
              height: 1
            }

            Rectangle {
              id: cancelButton
              width: cancelLabel.implicitWidth + Style.space(24)
              height: Style.space(34)
              radius: Style.cornerRadius
              color: cancelMouse.containsMouse ? root.alpha(root.foreground, 0.12) : root.alpha(root.foreground, 0.065)
              Text {
                id: cancelLabel
                anchors.centerIn: parent
                text: "Cancel"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
              }
              MouseArea { id: cancelMouse; anchors.fill: parent; hoverEnabled: true; onClicked: root.cancelEdit() }
            }

            Rectangle {
              id: applyButton
              width: applyLabel.implicitWidth + Style.space(24)
              height: Style.space(34)
              radius: Style.cornerRadius
              readonly property bool conflictBlocked: root.collisionFor(root.editKey) !== "" && (root.editMode === "restore" || !root.conflictAccepted)
              opacity: root.editKey && !root.saving && !conflictBlocked ? 1 : 0.5
              color: root.alpha(conflictBlocked ? root.foreground : root.statusColor("custom"), applyMouse.containsMouse ? 0.34 : 0.24)
              border.width: 1
              border.color: root.alpha(conflictBlocked ? root.foreground : root.statusColor("custom"), 0.7)
              Text {
                id: applyLabel
                anchors.centerIn: parent
                text: root.saving ? "Applying…"
                  : (root.editMode === "restore"
                    ? (applyButton.conflictBlocked ? "Choose another shortcut" : "Restore shortcut")
                    : (applyButton.conflictBlocked ? "Resolve conflict" : (root.collisionFor(root.editKey) !== "" ? "Replace shortcut" : "Apply shortcut")))
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
              MouseArea {
                id: applyMouse
                anchors.fill: parent
                hoverEnabled: true
                enabled: root.editKey !== "" && !root.saving && !applyButton.conflictBlocked
                onClicked: root.editMode === "restore" ? root.restoreShortcut() : root.applyEdit()
              }
            }
          }
        }
      }
    }

    AddShortcut {
      id: addDialog
      anchors.fill: parent
      z: 55
      visible: root.addOpen
      host: root
      onDismissed: {
        root.addOpen = false
        Qt.callLater(function() { keyCatcher.forceActiveFocus() })
      }
      onSaved: {
        root.addOpen = false
        root.activeFilter = "custom"
        root.query = ""
        root.refresh()
        Qt.callLater(function() { keyCatcher.forceActiveFocus() })
      }
    }

    FocusScope {
      id: settingsOverlay
      anchors.fill: parent
      z: 60
      visible: root.settingsOpen
      focus: visible
      Keys.onEscapePressed: root.closeSettings()

      Rectangle {
        anchors.fill: parent
        color: root.alpha("#000000", 0.62)
        MouseArea { anchors.fill: parent; onClicked: root.closeSettings() }
      }

      Rectangle {
        width: Math.min(parent.width - Style.space(48), Style.space(520))
        height: settingsColumn.implicitHeight + Style.space(36)
        anchors.centerIn: parent
        radius: Style.cornerRadius
        color: root.surface
        border.width: 1
        border.color: root.alpha(root.foreground, 0.18)
        MouseArea { anchors.fill: parent; onClicked: {} }

        Column {
          id: settingsColumn
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.top: parent.top
          anchors.margins: Style.space(18)
          spacing: Style.space(12)

          Row {
            width: parent.width

            Text {
              width: parent.width - closeSettingsButton.width
              text: root.resetConfirmOpen ? "Reset all shortcuts?" : "OmaKeybinds settings"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
            }

            Rectangle {
              id: closeSettingsButton
              width: Style.space(30)
              height: Style.space(30)
              radius: Style.cornerRadius
              color: closeSettingsMouse.containsMouse ? root.alpha(root.foreground, 0.12) : "transparent"
              Text {
                anchors.centerIn: parent
                text: "×"
                color: root.muted
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
              }
              MouseArea {
                id: closeSettingsMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.closeSettings()
              }
            }
          }

          Text {
            width: parent.width
            visible: !root.resetConfirmOpen
            text: "Shortcut management"
            color: root.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          Rectangle {
            width: parent.width
            height: Style.space(78)
            visible: !root.resetConfirmOpen
            radius: Style.cornerRadius
            color: resetOptionMouse.containsMouse ? root.alpha("#ff6b6b", 0.13) : root.alpha(root.foreground, 0.055)
            border.width: 1
            border.color: root.alpha("#ff6b6b", 0.28)

            Text {
              anchors.left: parent.left
              anchors.leftMargin: Style.space(14)
              anchors.verticalCenter: parent.verticalCenter
              text: "↺"
              color: "#ff6b6b"
              font.family: root.fontFamily
              font.pixelSize: Style.font.title * 1.2
            }

            Column {
              anchors.left: parent.left
              anchors.leftMargin: Style.space(52)
              anchors.right: optionArrow.left
              anchors.rightMargin: Style.space(10)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(4)
              Text {
                text: "Reset all shortcuts"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
              Text {
                width: parent.width
                text: "Restore the current Omarchy defaults and remove every override"
                color: root.muted
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }

            Text {
              id: optionArrow
              anchors.right: parent.right
              anchors.rightMargin: Style.space(14)
              anchors.verticalCenter: parent.verticalCenter
              text: "›"
              color: root.muted
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
            }

            MouseArea {
              id: resetOptionMouse
              anchors.fill: parent
              hoverEnabled: true
              onClicked: {
                root.resetMessage = ""
                root.resetConfirmOpen = true
              }
            }
          }

          Text {
            width: parent.width
            visible: root.resetConfirmOpen
            text: "This replaces your personal bindings file with the defaults shipped with your current Omarchy version. OmaKeybinds backs up the file and its state first, and restores the file if validation fails."
            color: root.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            wrapMode: Text.WordWrap
          }

          Rectangle {
            width: parent.width
            height: Style.space(58)
            visible: root.resetConfirmOpen
            radius: Style.cornerRadius
            color: root.alpha("#ff6b6b", 0.10)
            border.width: 1
            border.color: root.alpha("#ff6b6b", 0.35)
            Text {
              anchors.fill: parent
              anchors.margins: Style.space(12)
              text: "This changes hypr/bindings.lua in your configuration directory. Your current file remains recoverable from its backup."
              color: "#ff9a9a"
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
              verticalAlignment: Text.AlignVCenter
            }
          }

          Text {
            width: parent.width
            visible: root.resetMessage !== ""
            text: root.resetMessage
            textFormat: Text.PlainText
            color: root.resetMessage.indexOf("reset to") !== -1 ? "#7bd88f" : "#ff6b6b"
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }

          Row {
            anchors.right: parent.right
            spacing: Style.space(9)
            visible: root.resetConfirmOpen

            Rectangle {
              width: resetCancelLabel.implicitWidth + Style.space(24)
              height: Style.space(34)
              radius: Style.cornerRadius
              color: resetCancelMouse.containsMouse ? root.alpha(root.foreground, 0.12) : root.alpha(root.foreground, 0.065)
              Text {
                id: resetCancelLabel
                anchors.centerIn: parent
                text: "Cancel"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
              }
              MouseArea {
                id: resetCancelMouse
                anchors.fill: parent
                hoverEnabled: true
                enabled: !root.resetting
                onClicked: root.resetConfirmOpen = false
              }
            }

            Rectangle {
              width: resetConfirmLabel.implicitWidth + Style.space(24)
              height: Style.space(34)
              radius: Style.cornerRadius
              opacity: root.resetting ? 0.55 : 1
              color: resetConfirmMouse.containsMouse ? "#e94f4f" : "#c83f49"
              Text {
                id: resetConfirmLabel
                anchors.centerIn: parent
                text: root.resetting ? "Resetting…" : "Reset everything"
                color: "white"
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
              MouseArea {
                id: resetConfirmMouse
                anchors.fill: parent
                hoverEnabled: true
                enabled: !root.resetting
                onClicked: root.resetAllShortcuts()
              }
            }
          }
        }
      }
    }
  }
}
