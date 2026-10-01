import unittest
from PySide6.QtCore import QCoreApplication, QObject, Signal
from operator_gui.camera import Camera
from tests.test_field_editor import Session


class Control(QObject):
    changed=Signal()
    barrierIssued=Signal()
    owns=True
    pending=False
    error=""

    def __init__(self):
        super().__init__()
        self.commands=[]

    def command(self,op,body,**options):
        self.commands.append((op,body,options))
        return True


class CameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.session=Session()
        self.control=Control()
        self.camera=Camera(self.session,self.control)

    def tearDown(self):
        self.camera.shutdown()

    def test_explicit_read_does_not_create_or_start_video(self):
        self.assertFalse(self.session.requests)
        self.camera.refresh()
        self.assertEqual([r[0] for r in self.session.requests],
                         ["camera.capabilities","camera.status","camera.controls.list"])
        self.camera.refresh()
        self.assertEqual(len(self.session.requests),3)
        self.assertFalse(self.control.commands)

    def test_pages_unknown_support_and_requested_values(self):
        self.camera.response("camera.controls.list",dict(items=[
            dict(key="camera.ae_enabled",type="bool",value=False,supported=None)],
            next_offset=2),"camera-ui:camera.controls.list")
        self.assertIsNone(self.camera.metas["camera.ae_enabled"]["supported"])
        self.assertEqual(self.session.requests[-1][1],dict(offset=2,limit=2))

    def test_freeze_apply_and_save_are_distinct(self):
        key="camera.exposure_us"
        self.camera.values[key]=8000
        self.camera.response("camera.controls.freeze",dict(values={key:7000},source_sequence=42),
                             "camera-ui:camera.controls.freeze")
        self.assertEqual(self.camera.drafts[key],7000)
        self.camera.apply(False)
        self.assertEqual(self.control.commands[-1][:2],
                         ("camera.controls.set",dict(values={key:7000})))
        self.camera.apply(True)
        self.assertEqual(self.control.commands[-1][0],"camera.controls.save")
        self.camera.response("camera.controls.save",dict(values={key:7000}),
                             "camera-ui:camera.controls.save")
        self.assertFalse(self.camera.drafts)

    def test_start_stop_only_camera_and_disconnect_clears(self):
        self.camera.start(16667)
        self.assertEqual(self.control.commands[-1][:2],
                         ("camera.start",dict(frame_duration_us=16667)))
        self.assertTrue(self.control.commands[-1][2]["manual"])
        self.camera.stop()
        self.assertEqual(self.control.commands[-1][0],"camera.stop")
        self.camera.start(1)
        self.assertEqual(len(self.control.commands),2)
        self.camera.watch(True)
        self.session.connected=False
        self.camera.connection()
        self.assertFalse(self.camera.pending)
        self.assertFalse(self.camera.timer.isActive())

    def test_status_does_not_replace_draft(self):
        self.camera.drafts["camera.exposure_us"]=4000
        self.camera.response("camera.status",dict(running=True,requested_controls={"exposure_us":8000}),
                             "camera-ui:camera.status")
        self.assertEqual(self.camera.view["values"]["camera.exposure_us"],4000)
        self.assertEqual(self.camera.view["requested"]["camera.exposure_us"],8000)
