import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from operator_gui.video import video_request
from operator_gui.video_views import VideoViews
from operator_gui.video_receiver import receiver_description
from tests import test_operator
from tests.test_operator import wait_until


SETTINGS = dict(source="direct-gst", sensorWidth=1600, sensorHeight=1300, depth=10,
                width=800, height=648, fps=60, max_fps=30, codec="jpeg", bitrate=2000000)
SOURCE = dict(id="direct-gst", stream_settings=dict(codecs=["jpeg", "h264"], max_fps=[1,120],
              max_size=[1600,1300], jpeg_alignment=8))


class ReceiverStub(QObject):
    ready = Signal()
    stopped = Signal()
    error = Signal(str)
    status = Signal(object)
    imageReady = Signal(object)
    log = Signal(str, str)

    def prepare(self):
        self.prepared = True

    def start(self, *args):
        assert self.prepared, "Prepare local receiver before start/attach"
        self.ready.emit()

    def stop(self):
        self.stopped.emit()

    def shutdown(self):
        pass


class VideoTests(unittest.TestCase):
    setUpClass = classmethod(test_operator.OperatorTests.setUpClass.__func__)
    tearDown = test_operator.OperatorTests.tearDown
    connect = test_operator.OperatorTests.connect

    def setUp(self):
        self.patcher=patch("operator_gui.video.Receiver", ReceiverStub)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        test_operator.OperatorTests.setUp(self)
        self.manager=self.controller.streams

    def manual(self):
        self.connect()
        self.controller.control.acquire()
        wait_until(lambda:self.controller.control.owns)
        self.controller.control.enterManual()
        wait_until(lambda:self.controller.control.view["manual"] and not self.controller.control.pending)
        self.manager.refresh()
        wait_until(lambda:not self.manager.pending)

    def create(self, source="direct-gst"):
        before=self.manager.last_created
        self.manager.create(SETTINGS | dict(source=source))
        wait_until(lambda:self.manager.last_created!=before and not self.manager.pending)
        return self.manager.last_created

    def start(self, ident, port=5004):
        self.manager.connectStream(ident,port,"jpegdec",True)
        wait_until(lambda:self.manager.players[ident].phase=="receiving")
        return self.manager.players[ident]

    def test_catalog_is_explicit_and_create_does_not_start(self):
        self.manual()
        self.assertEqual([s["id"] for s in self.manager.sources],["direct-gst","runtime","localisation"])
        ident=self.create()
        self.assertEqual(self.manager.details[ident]["state"],"created")
        self.assertFalse(self.manager.players)
        self.assertFalse(any(m["op"] in ("camera.start","videostream.start","videostream.attach") for m in self.robot.requests))

    def test_views_share_receiver_and_never_send_commands(self):
        self.manual();ident=self.create();p=self.start(ident)
        requests=len(self.robot.requests)
        views=self.controller.video_views
        first=views.add(ident);second=views.add(ident)
        image=QImage(8,8,QImage.Format.Format_RGB32);image.fill(0xff008000)
        p.receiver.imageReady.emit(image)
        self.assertEqual(len(self.manager.players),1)
        self.assertEqual(views.selected(first),views.selected(second))
        self.assertTrue(self.manager.imageUrl(ident))
        views.remove(first);views.select(second,"");views.remove(second)
        self.assertEqual(len(self.robot.requests),requests)
        self.assertEqual(p.phase,"receiving")

    def test_observer_attach_and_detach_no_lease(self):
        self.manual();ident=self.create()
        self.robot.streams[ident].update(state="running",run_id="other",ssrc=1234)
        self.controller.control.lease=None
        self.manager.connectStream(ident,5004,"jpegdec",False)
        wait_until(lambda:self.manager.players[ident].phase=="receiving")
        attach=next(m for m in self.robot.requests if m["op"]=="videostream.attach")
        self.assertNotIn("lease_epoch",attach["body"])
        self.manager.detach(ident)
        wait_until(lambda:self.manager.players[ident].phase=="stopped")
        self.assertFalse(self.robot.streams[ident]["attached"])

    def test_second_receiver_requires_distinct_port(self):
        self.manual();one=self.create();self.start(one);two=self.create()
        self.manager.connectStream(two,5004,"jpegdec",True)
        self.assertNotIn(two,self.manager.players)
        self.start(two,5006)
        self.assertEqual(len(self.manager.view["active"]),2)

    def test_run_change_clears_image_and_requires_explicit_action(self):
        self.manual();ident=self.create();p=self.start(ident)
        image=QImage(8,8,QImage.Format.Format_RGB32);p.receiver.imageReady.emit(image)
        self.manager.inspect_result(dict(p.info,run_id="new"))
        wait_until(lambda:p.phase=="stopped")
        self.assertIn("перезапущена",p.error)
        self.assertTrue(p.image.isNull())
        self.assertFalse(self.manager.view["active"])

    def test_remote_stop_and_receiver_error(self):
        self.manual();ident=self.create();p=self.start(ident)
        self.manager.inspect_result(dict(p.info,state="stopped"))
        self.assertEqual(p.phase,"stopped")
        self.assertTrue(p.image.isNull())
        self.start(ident)
        p.receiver.error.emit("test decode failure")
        wait_until(lambda:p.phase=="stopped" and not self.manager.busy(ident))
        self.assertIn("test decode failure",p.error)
        self.assertFalse(self.robot.streams[ident]["attached"])

    def test_unknown_creation_requires_acknowledgement_not_retry(self):
        self.manual()
        self.robot.silent=True
        self.manager.create(SETTINGS)
        context=next(k for k,v in self.manager.pending.items() if v[0]=="create")
        self.manager.failed("videostream.create","Response timeout (operation outcome unknown)",context)
        self.assertFalse(self.manager.view["canCreate"])
        self.manager.acknowledgeUnknownCreate()
        self.assertTrue(self.manager.view["canCreate"])

    def test_arbitrary_catalog_source_and_no_sensor_for_runtime(self):
        for source in ("runtime","localisation","future-camera"):
            spec=video_request(SETTINGS,dict(SOURCE,id=source))
            self.assertEqual(spec["source"],source)
            self.assertNotIn("sensor",spec)
            self.assertNotIn("rtp_port",spec)

    def test_view_manifest_restores_only_panels_not_subscriptions(self):
        views=self.controller.video_views
        ident=views.add("1")
        self.assertTrue(views.save())
        restored=VideoViews(Path(self.tmp.name)/"video-views.json")
        self.assertEqual(restored.entries,[dict(id=ident,stream="")])
        views.remove(ident)
        self.assertTrue(views.restore())
        self.assertEqual(views.entries,[dict(id=ident,stream="")])
        self.assertFalse(self.robot.requests)

    def test_request_validation_and_receiver(self):
        spec=video_request(SETTINGS,SOURCE)
        self.assertEqual(spec["mtu"],1400)
        for values in (dict(height=650),dict(fps="nan"),dict(depth=9),dict(codec="bogus")):
            with self.assertRaises(ValueError):video_request(SETTINGS | values,SOURCE)
        info=dict(spec=spec,rtp_port=5004,encoding_name="JPEG",payload_type=26,clock_rate=90000)
        launch=receiver_description(info,"jpegdec",30)
        self.assertIn("appsink name=frames",launch)
