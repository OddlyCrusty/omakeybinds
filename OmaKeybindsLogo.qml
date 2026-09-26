import QtQuick

// Theme-aware OmaKeybinds mark: an O monogram set into a physical keycap,
// with a small diamond accent representing a remapped key.
Item {
  id: logo

  property color foreground: "white"
  property color accent: foreground

  Rectangle {
    id: keyShadow
    width: parent.width * 0.72
    height: parent.height * 0.64
    anchors.centerIn: parent
    anchors.verticalCenterOffset: parent.height * 0.055
    radius: Math.max(2, width * 0.20)
    color: "transparent"
    border.width: Math.max(1, parent.width * 0.055)
    border.color: Qt.rgba(logo.foreground.r, logo.foreground.g, logo.foreground.b, 0.34)
  }

  Rectangle {
    id: keyFace
    width: parent.width * 0.72
    height: parent.height * 0.64
    anchors.centerIn: parent
    anchors.verticalCenterOffset: -parent.height * 0.035
    radius: Math.max(2, width * 0.20)
    color: "transparent"
    border.width: Math.max(1, parent.width * 0.065)
    border.color: logo.foreground

    Text {
      anchors.centerIn: parent
      anchors.verticalCenterOffset: -parent.height * 0.02
      text: "O"
      color: logo.foreground
      font.family: "sans-serif"
      font.pixelSize: parent.height * 0.62
      font.bold: true
      horizontalAlignment: Text.AlignHCenter
      verticalAlignment: Text.AlignVCenter
    }
  }

  Rectangle {
    width: Math.max(3, parent.width * 0.16)
    height: width
    x: parent.width * 0.69
    y: parent.height * 0.12
    radius: width * 0.18
    rotation: 45
    color: logo.accent
    border.width: Math.max(1, parent.width * 0.035)
    border.color: logo.foreground
  }
}
