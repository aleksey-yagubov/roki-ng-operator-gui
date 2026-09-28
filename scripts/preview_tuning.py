"""Render the standalone tuning panel without robot connection or docking plugin.

Example: QT_QPA_PLATFORM=offscreen python scripts/preview_tuning.py FRAME.png
Requires sibling roki-ng only to obtain its real parameter schema/defaults.
"""
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'roki-ng')]

from PySide6.QtCore import QUrl,QTimer,QObject,QPoint,Qt
from PySide6.QtGui import QGuiApplication,QImage
from PySide6.QtQuick import QQuickView,QQuickWindow,QSGRendererInterface
from PySide6.QtTest import QTest
from operator_gui.controller import Controller
from operator_gui.vision_tuning import TuningImages
from roki_ng.parameters import Parameters,COLOUR_DEFAULTS


def main():
    app=QGuiApplication([])
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
    with tempfile.TemporaryDirectory() as directory:
        c=Controller('127.0.0.1',8093,Path(directory));p=Parameters(directory);t=c.vision_tuning
        try:
            t.values={k:v for k,v in p.values.items() if k.startswith(('vision.','camera.'))}
            t.metas={k:p.describe(k) for k in t.values}
            t.profiles=list(COLOUR_DEFAULTS);t.profile='green_field'
            image=QImage(sys.argv[1])
            if image.isNull():raise ValueError('Cannot load frame')
            c.video.backend='runtime (офлайн запись)';c.video.receive_image(image)
            t.snapshot();t.notice='Офлайн preview. Робот не подключён, используются defaults.'
            v=QQuickView();v.resize(1050,1100)
            v.engine().addImageProvider('tuning',TuningImages(t))
            for name,obj in [('backend',c),('controls',c.control),('visionTuning',t)]:
                v.rootContext().setContextProperty(name,obj)
            v.setResizeMode(QQuickView.SizeRootObjectToView)
            v.setSource(QUrl.fromLocalFile(str(ROOT/'qml/VisionPanel.qml')))
            if v.errors():raise RuntimeError(str(v.errors()))
            v.show()
            failures=[]
            def finish():
                try:
                    target=ROOT/'artifacts/vision-tuning.png';target.parent.mkdir(exist_ok=True)
                    if not v.grabWindow().save(str(target)):raise RuntimeError('Screenshot failed')
                    source=v.rootObject().findChild(QObject,'tuningSource')
                    pos=source.mapToScene(source.boundingRect().center())
                    QTest.mouseClick(v,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(int(pos.x()),int(pos.y())))
                    assert len(t.drafts)==6,'QML eyedropper did not update six LAB boundaries'
                    tabs=v.rootObject().findChild(QObject,'tuningTabs');tabs.setProperty('currentIndex',1)
                    QTest.qWait(100)
                    assert v.grabWindow().save(str(ROOT/'artifacts/camera-tuning.png'))
                    print('QML click and camera tab passed:',target,flush=True)
                except Exception as exc:failures.append(exc)
                finally:app.quit()
            QTimer.singleShot(700,finish);app.exec();v.setSource(QUrl())
            if failures:raise failures[0]
        finally:c.shutdown()


if __name__=='__main__':main()
