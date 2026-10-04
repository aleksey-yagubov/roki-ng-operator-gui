"""Offscreen regression: params.get and params.describe can arrive in either order."""
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine


def main():
    app = QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(
        Path(__file__).resolve().parents[1] / 'qml' / 'ValueEditor.qml')))
    assert not component.isError(), component.errors()
    meta = dict(type='str', choices=['software', 'controller'])
    for value_first in (True, False):
        editor = component.create()
        assert editor is not None, component.errors()
        properties = [('initialValue', 'controller'), ('meta', meta)]
        if not value_first:
            properties.reverse()
        for key, value in properties:
            assert editor.setProperty(key, value)
            app.processEvents()
        app.processEvents()
        assert editor.property('value') == 'controller', (value_first, editor.property('value'))
        editor.setProperty('initialValue', 'software')
        app.processEvents()
        assert editor.property('value') == 'software'
        editor.deleteLater()
        app.processEvents()
    print('Kick parameter editor: both response orders passed')


if __name__ == '__main__':
    main()
