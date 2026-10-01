import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal

from operator_gui.video import video_request
from operator_gui.video_receiver import receiver_description
from tests import test_operator
from tests.test_operator import wait_until


SETTINGS = dict(sensorWidth=1600, sensorHeight=1300, depth=10, width=800, height=648,
                fps=60, codec="jpeg", bitrate=2000000, port=5004, decoder="vajpegdec")


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
        assert getattr(self, 'prepared', False), 'Receiver must be prepared before start/attach'
        self.ready.emit()

    def stop(self):
        self.stopped.emit()

    def shutdown(self):
        pass


class Item:
    def window(self):
        return self


class VideoTests(unittest.TestCase):
    setUpClass = classmethod(test_operator.OperatorTests.setUpClass.__func__)
    tearDown = test_operator.OperatorTests.tearDown
    connect = test_operator.OperatorTests.connect

    def setUp(self):
        with patch("operator_gui.video.Receiver", ReceiverStub):
            test_operator.OperatorTests.setUp(self)

    def manual(self):
        self.connect()
        self.controller.control.acquire()
        wait_until(lambda: self.controller.control.owns)
        self.controller.control.enterManual()
        wait_until(lambda: self.controller.control.view["manual"] and not self.controller.control.pending)
        video = self.controller.video
        video.item = Item()
        return video

    def test_catalog_pagination_has_no_start_side_effects(self):
        self.connect()
        video=self.controller.video
        video.getCatalogs()
        wait_until(lambda:not video.catalog_pending)
        self.assertEqual([s['id'] for s in video.sources], ['direct-gst','runtime','localisation'])
        self.assertFalse(any(m['op'] in ('camera.start','videostream.start','videostream.create') for m in self.robot.requests))

    def test_observer_attaches_without_lease_and_window_close_is_local(self):
        video=self.manual()
        video.start(SETTINGS);wait_until(lambda:video.phase=='running')
        ident=video.info['stream_id']
        video.stop();wait_until(lambda:not video.info and not video.pending)
        self.robot.streams[ident].update(state='running',run_id='other',ssrc=1234)
        self.controller.control.lease=None
        video=self.controller.localisation_video
        video.item=Item()
        video.watchStream(ident,5004,'vajpegdec')
        wait_until(lambda:video.phase=='running')
        attach=next(m for m in self.robot.requests if m['op']=='videostream.attach')
        self.assertNotIn('lease_epoch',attach['body'])
        before=len(self.robot.requests)
        video.closeWindow()
        self.assertEqual(len(self.robot.requests),before)
        self.assertEqual(video.phase,'running')

    def test_run_change_requires_explicit_reattach(self):
        video=self.manual();video.start(SETTINGS)
        wait_until(lambda:video.phase=='running')
        video.response('videostream.status',dict(video.info,run_id='new-run'),'video')
        wait_until(lambda:not video.info and not video.pending)
        self.assertIn('перезапущена',video.error)


    def test_remote_stop_releases_stream_and_explains_frozen_image(self):
        video=self.manual()
        video.startLocalisation()
        wait_until(lambda:video.phase=='running')
        video.response('videostream.status',dict(video.info,state='stopped'),'video')
        wait_until(lambda:not video.info and not video.pending)
        self.assertTrue(video.view['canStart'])
        self.assertIn('остановлен на роботе',video.error)
        self.assertFalse(video.timer.isActive())

    def test_localisation_video_uses_stream_worker_source(self):
        video=self.manual()
        video.startLocalisation()
        wait_until(lambda: video.phase=='running')
        request=next(m for m in self.robot.requests if m['op']=='videostream.create')
        self.assertEqual(request['body']['source'],'localisation')
        self.assertNotIn('sensor',request['body'])
        self.assertEqual(request['body']['output']['width'],800)
        video.stop()
        wait_until(lambda: not video.info and not video.pending)

    def test_explicit_start_receiver_before_remote_and_stop_without_lease(self):
        self.connect()
        video = self.controller.video
        video.start(SETTINGS)
        self.assertFalse(any(m["op"].startswith("videostream.") for m in self.robot.requests))
        self.controller.control.acquire()
        wait_until(lambda: self.controller.control.owns)
        self.controller.control.enterManual()
        wait_until(lambda: self.controller.control.view["manual"] and not self.controller.control.pending)
        video.start(SETTINGS)
        wait_until(lambda: video.phase == "receiver")
        self.assertFalse(any(m["op"] == "videostream.start" for m in self.robot.requests))
        video.attach(Item())
        wait_until(lambda: video.phase == "running")
        self.controller.control.lease = None
        video.stop()
        wait_until(lambda: not video.info and not video.pending)
        self.assertTrue(all(not s.get("attached") for s in self.robot.streams.values()))

    def test_settings_editable_without_control_and_capabilities_visible(self):
        video = self.controller.video
        self.assertTrue(video.view["canEditSettings"])
        self.assertFalse(video.view["canStart"])
        self.connect()
        video.getCapabilities()
        wait_until(lambda: bool(video.capabilities))
        self.assertIn("h264", video.view["capabilitiesSummary"])
        self.assertTrue(video.view["canEditSettings"])
        self.assertIn("Получить управление", video.view["startBlockedReason"])
        self.controller.control.acquire()
        wait_until(lambda: self.controller.control.owns and not self.controller.control.pending)
        self.assertTrue(video.view["canStart"])

    def test_stop_while_create_is_in_flight(self):
        video = self.manual()
        self.robot.drop_once.add("videostream.create")
        video.start(SETTINGS)
        video.stop()
        wait_until(lambda: video.phase == "idle" and not video.pending)
        self.assertTrue(all(not s.get("attached") for s in self.robot.streams.values()))
        self.assertFalse(any(m["op"] == "videostream.start" for m in self.robot.requests))

    def test_receiver_error_detaches_remote_stream(self):
        video = self.manual()
        video.start(SETTINGS)
        wait_until(lambda: video.phase == "running")
        video.receiver.error.emit("test pipeline error")
        wait_until(lambda: not video.info and not video.pending)
        self.assertIn("test pipeline error", video.error)
        self.assertTrue(all(not s.get("attached") for s in self.robot.streams.values()))

    def test_unknown_create_prevents_duplicate_streams(self):
        video = self.manual()
        video.failed("videostream.create", "Response timeout (operation outcome unknown)", "video")
        self.assertFalse(video.view["canStart"])
        self.controller.disconnectRobot()
        wait_until(lambda: not self.controller.transport.connected)
        self.assertFalse(video.unknown_create)

    def test_main_and_localisation_players_are_independent_subscriptions(self):
        main=self.manual()
        debug=self.controller.localisation_video;debug.item=Item()
        main.start(dict(SETTINGS,backend='runtime'))
        wait_until(lambda:main.phase=='running')
        main_id=main.info['stream_id']
        debug.startLocalisation();wait_until(lambda:debug.phase=='running')
        self.assertNotEqual(main_id,debug.info['stream_id'])
        self.assertEqual(main.info['destination'][1],5004)
        self.assertEqual(debug.info['destination'][1],5006)
        debug.stop();wait_until(lambda:not debug.info and not debug.pending)
        self.assertEqual(main.phase,'running')
        self.assertIn(main_id,self.robot.streams)
        self.assertFalse(any(m['op'] in ('camera.stop','localisation.stop') for m in self.robot.requests))


class VideoValidationTests(unittest.TestCase):
    def test_spec_and_decoder_choices_with_qimage(self):
        spec = video_request(SETTINGS)
        self.assertNotIn("bitrate", spec["codec"])
        self.assertEqual(spec["sensor"], dict(width=1600, height=1300, depth=10))
        for codec, decoders in (("JPEG", ("vajpegdec", "jpegdec")),
                                ("H264", ("vah264dec", "avdec_h264"))):
            info = dict(encoding_name=codec, payload_type=96, ssrc=123)
            for decoder in decoders:
                launch = receiver_description(info, decoder, 30)
                self.assertIn(decoder, launch)
                self.assertIn("appsink name=frames", launch)
                self.assertIn("video/x-raw,format=RGBA", launch)
        for values in (dict(height=650), dict(fps="nan"), dict(depth=9), dict(port=80)):
            with self.assertRaises(ValueError):
                video_request(SETTINGS | values)
