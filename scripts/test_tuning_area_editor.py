"""Qt keyboard regression: area editing must preserve partial input."""
from pathlib import Path
from PySide6.QtCore import QUrl, Qt, QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
app = QGuiApplication([])
view = QQuickView()
view.setSource(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'qml/ValueEditor.qml')))
root = view.rootObject()
assert root
root.setProperty('meta', {'type':'int', 'min':1, 'max':520000})
root.setProperty('commitOnFinish', True)
root.setProperty('initialValue', 50)
root.setWidth(200); root.setHeight(40)
view.resize(240, 70); view.show()
field = root.findChild(QObject, 'valueInput')
values = []
root.edited.connect(values.append)
QTest.qWait(100)
field.forceActiveFocus()
QTest.qWait(50)
field.selectAll()
for key in (Qt.Key_1, Qt.Key_2, Qt.Key_5, Qt.Key_0):
    QTest.keyClick(view, key)
assert field.property('text') == '1250'
assert not values
QTest.keyClick(view, Qt.Key_Return)
assert values[-1] == '1250'
print('Area editor: typing and Enter passed')
view.close()
