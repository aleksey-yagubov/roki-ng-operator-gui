"""Headless field-template/map check using the real runtime parameter schema."""
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'roki-ng')]

from PySide6.QtCore import QObject,QUrl,QMetaObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

from operator_gui.controller import Controller
from roki_ng.parameters import Parameters
from roki_ng.field_config import disk_model,line_model


def main():
    app=QGuiApplication([])
    with tempfile.TemporaryDirectory() as directory:
        backend=Controller('127.0.0.1',1,Path(directory))
        view=QQuickView()
        context=view.rootContext()
        context.setContextProperty('backend',backend)
        context.setContextProperty('controls',backend.control)
        context.setContextProperty('fieldEditor',backend.field_editor)
        warnings=[]
        view.engine().warnings.connect(lambda messages:warnings.extend(str(m) for m in messages))
        try:
            params=Parameters(directory)
            editor=backend.field_editor
            editor.values={k:v for k,v in params.values.items() if k.startswith('field.') or k=='match.own_goal'}
            editor.metas={k:params.describe(k) for k in editor.values if k.startswith('field.')}
            editor.changed.emit()
            view.setSource(QUrl.fromLocalFile(str(ROOT/'qml/FieldPanel.qml')))
            assert view.rootObject() is not None,warnings
            view.setResizeMode(QQuickView.SizeRootObjectToView)
            view.resize(1150,720);view.show();QTest.qWait(100)
            button=view.rootObject().findChild(QObject,'competitionFieldTemplate')
            assert button.property('enabled')
            QMetaObject.invokeMethod(button,'clicked')
            QTest.qWait(100)
            merged=editor.values|editor.drafts
            for key,value in editor.drafts.items():params.validate(key,value)
            assert len(disk_model(merged))==6 and len(line_model(merged))==14
            assert params.values['field.geometry']['length']==3.35
            assert not backend.transport.connected
            assert not warnings,warnings
            image=view.grabWindow()
            assert not image.isNull()
            output=ROOT/'artifacts'/'field-template.png'
            output.parent.mkdir(exist_ok=True)
            assert image.save(str(output))
            print('Field template: QML, metric map and draft-only behavior passed; screenshot:',output)
        finally:
            view.close()
            backend.shutdown()
            # Destroy the QML scene before its Python context objects.
            from shiboken6 import delete
            delete(view)


if __name__=='__main__':main()
