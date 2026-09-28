"""Consistent macOS controls beside KDDockWidgets' light dock surfaces."""
import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtQuickControls2 import QQuickStyle


LIGHT_PALETTE = None

def configure(app):
    global LIGHT_PALETTE
    if sys.platform != "darwin":
        return
    # Native macOS controls follow the OS while KDDW 2.4 uses light surfaces.
    # Fusion honours this application-local palette, including floating docks.
    QQuickStyle.setStyle("Fusion")
    palette = QPalette()
    colours = {
        "Window": "#f0f1f3", "WindowText": "#202124",
        "Base": "#ffffff", "AlternateBase": "#f4f5f7",
        "Text": "#202124", "Button": "#e8eaed", "ButtonText": "#202124",
        "ToolTipBase": "#fff8dc", "ToolTipText": "#202124",
        "Highlight": "#2463b4", "HighlightedText": "#ffffff",
        "Link": "#1758a8", "LinkVisited": "#7046a0",
        "Light": "#ffffff", "Midlight": "#e4e6e9", "Mid": "#aeb3ba",
        "Dark": "#737981", "Shadow": "#454950", "PlaceholderText": "#626974",
    }
    for role, colour in colours.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(colour))
    for role in ("WindowText", "Text", "ButtonText"):
        palette.setColor(QPalette.ColorGroup.Disabled,
                         getattr(QPalette.ColorRole, role), QColor("#787e87"))
    LIGHT_PALETTE = palette
    app.setPalette(palette)
