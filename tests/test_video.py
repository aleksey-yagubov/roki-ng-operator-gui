import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from operator_gui.video import setting_value
from operator_gui.video_views import VideoViews
from operator_gui.video_receiver import receiver_description
from tests.fake_robot import video_output
from tests import test_operator
from tests.test_operator import wait_until


class ReceiverStub(QObject):
    ready = Signal(int)
    stopped = Signal()
    error = Signal(str)
    status = Signal(object)
    imageReady = Signal(object)
    log = Signal(str, str)
    next_port = 5100

    def prepare(self):
        self.prepared = True

    def start(self, info, *args):
        assert self.prepared
        ReceiverStub.next_port += 1
        self.ready.emit(info['rtp_port'] or ReceiverStub.next_port)

    def stop(self):
        self.stopped.emit()

    def shutdown(self):
        pass


class VideoTests(unittest.TestCase):
    setUpClass = classmethod(test_operator.OperatorTests.setUpClass.__func__)
    tearDown = test_operator.OperatorTests.tearDown
    connect = test_operator.OperatorTests.connect

    def setUp(self):
        self.patcher = patch('operator_gui.video.Receiver', ReceiverStub)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        test_operator.OperatorTests.setUp(self)
        self.manager = self.controller.streams

    def manual(self):
        self.connect()
        self.controller.control.acquire()
        wait_until(lambda: self.controller.control.owns)
        self.controller.control.enterManual()
        wait_until(lambda: self.controller.control.view['manual'] and not self.controller.control.pending)
        self.manager.refresh()
        wait_until(lambda: bool(self.manager.names) and not self.manager.pending)
        self.manager.timer.stop()

    def start(self, name='stream', port=0):
        self.manager.watch(name, port, 'avdec_h264')
        wait_until(lambda: name in self.manager.players and self.manager.players[name].phase == 'receiving')
        return self.manager.players[name]

    def test_catalog_is_explicit_and_does_not_start(self):
        self.connect()
        self.assertFalse(any(m['op'].startswith('videostream.') for m in self.robot.requests))
        self.manager.refresh()
        wait_until(lambda: len(self.manager.names) == 3 and not self.manager.pending)
        self.assertEqual(self.manager.names, ['stream', 'camera', 'localisation'])
        self.assertFalse(self.manager.detail('camera')['available'])
        self.assertFalse(self.manager.players)
        self.assertTrue(all(m['body']['limit'] == 1 for m in self.robot.requests if m['op'] == 'videostream.list'))

    def test_subscribe_auto_port_and_controls_preserved(self):
        self.manual()
        p = self.start()
        request = next(m for m in self.robot.requests if m['op'] == 'videostream.subscribe')
        self.assertEqual(request['body'], dict(name='stream', rtp_port=p.port, lease_epoch=7))
        self.assertGreater(p.port, 0)
        self.assertIn('sensor_depth', self.manager.detail('stream')['controls'])
        self.assertEqual(len(self.controller.video_views.entries), 1)
        self.start()
        self.assertEqual(len(self.controller.video_views.entries), 1)
        self.assertEqual(sum(m['op'] == 'videostream.subscribe' for m in self.robot.requests), 1)

    def test_unchanged_catalogs_and_stats_do_not_reset_selectors(self):
        self.manual(); p = self.start()
        changes = []
        self.manager.outputsChanged.connect(lambda: changes.append('outputs'))
        self.manager.receiversChanged.connect(lambda: changes.append('receivers'))
        self.manager.refresh()
        wait_until(lambda: not self.manager.pending)
        for fps in range(100):
            p.status(dict(fps=fps, frames=fps*10))
        self.assertEqual(changes, [])
        self.manager.inspect_result(dict(p.info, state='stopped'))
        self.assertEqual(changes, ['receivers'])

    def test_views_share_receiver_and_never_send_commands(self):
        self.manual(); p = self.start()
        requests = len(self.robot.requests)
        views = self.controller.video_views
        first = views.add('stream'); second = views.add('stream')
        image = QImage(8,8,QImage.Format.Format_RGB32); image.fill(0xff008000)
        p.receiver.imageReady.emit(image)
        self.assertEqual(len(self.manager.players), 1)
        self.assertEqual(views.selected(first), views.selected(second))
        self.assertTrue(self.manager.imageUrl('stream'))
        views.remove(first); views.select(second, ''); views.remove(second)
        self.assertEqual(len(self.robot.requests), requests)
        self.assertEqual(p.phase, 'receiving')

    def test_observer_subscribe_and_unsubscribe_preserves_other_receiver(self):
        self.manual()
        self.robot.streams['stream'].update(state='running', run_id='other', ssrc=1234, receivers=1)
        self.controller.control.lease = None
        self.start()
        request = next(m for m in self.robot.requests if m['op'] == 'videostream.subscribe')
        self.assertNotIn('lease_epoch', request['body'])
        self.assertNotIn('settings', request['body'])
        self.manager.unsubscribe('stream')
        wait_until(lambda: not self.manager.pending)
        self.assertEqual(self.robot.streams['stream']['receivers'], 1)
        self.assertEqual(self.robot.streams['stream']['state'], 'running')

    def test_observer_cannot_start_stopped_output(self):
        self.manual(); self.controller.control.lease = None
        self.manager.watch('stream', 0, 'avdec_h264')
        wait_until(lambda: not self.manager.pending)
        self.assertFalse(any(m['op'] == 'videostream.subscribe' for m in self.robot.requests))

    def test_dynamic_name_and_distinct_ports(self):
        self.manual(); self.start(port=5004)
        self.robot.streams['future'] = video_output('future')
        self.manager.refresh(); wait_until(lambda: not self.manager.pending)
        self.manager.watch('future', 5004, 'avdec_h264')
        self.assertNotIn('future', self.manager.players)
        p = self.start('future')
        self.assertNotEqual(p.port, 5004)
        self.assertEqual(len(self.manager.view['active']), 2)

    def test_run_change_clears_image_and_requires_explicit_action(self):
        self.manual(); p = self.start()
        p.receiver.imageReady.emit(QImage(8,8,QImage.Format.Format_RGB32))
        self.manager.inspect_result(dict(p.info, run_id='new'))
        wait_until(lambda: not self.manager.pending)
        self.assertEqual(p.phase, 'stopped')
        self.assertIn('перезапущена', p.error)
        self.assertTrue(p.image.isNull())
        self.assertFalse(self.manager.view['active'])

    def test_receiver_error_unsubscribes(self):
        self.manual(); p = self.start()
        p.receiver.error.emit('test decode failure')
        wait_until(lambda: not self.manager.pending)
        self.assertEqual(p.phase, 'stopped')
        self.assertFalse(self.robot.streams['stream']['subscribed'])

    def test_settings_flat_typed_live_and_fixed(self):
        self.manual()
        self.manager.update('stream', 'sensor_depth', '8')
        wait_until(lambda: not self.manager.pending)
        self.assertEqual(self.robot.streams['stream']['settings']['sensor_depth'], 8)
        self.manager.update('stream', 'fps', '59.94')
        wait_until(lambda: not self.manager.pending)
        self.assertEqual(self.manager.detail('stream')['settings']['fps'], 59.94)
        self.assertFalse(self.manager.editable('camera', 'height'))
        self.start()
        self.assertFalse(self.manager.editable('stream', 'bitrate'))
        self.robot.camera_running = True
        self.manager.refresh(); wait_until(lambda: not self.manager.pending)
        self.start('camera')
        self.assertTrue(self.manager.editable('camera', 'max_fps'))
        self.manager.update('camera', 'max_fps', '29.97')
        wait_until(lambda: not self.manager.pending)
        self.assertEqual(self.robot.streams['camera']['settings']['max_fps'], 29.97)
        self.manager.update('camera', 'max_fps', 100)
        self.assertIn('max_fps', self.manager.error)

    def test_timeout_reconciles_subscription_without_second_subscribe(self):
        self.manual()
        self.robot.drop_once.add('videostream.subscribe')
        self.manager.watch('stream', 0, 'avdec_h264')
        wait_until(lambda: self.robot.streams['stream']['subscribed'])
        context = next(k for k,v in self.manager.pending.items() if v[0] == 'stream')
        self.manager.failed('videostream.subscribe', 'Response timeout (operation outcome unknown)', context)
        wait_until(lambda: self.manager.players['stream'].phase == 'receiving')
        self.assertEqual(len({m['id'] for m in self.robot.requests if m['op']=='videostream.subscribe'}), 1)

    def test_reconnect_refreshes_without_restarting(self):
        self.manual(); self.start()
        before = sum(m['op']=='videostream.subscribe' for m in self.robot.requests)
        self.manager.reset('new-boot')
        wait_until(lambda: not self.manager.pending)
        self.assertTrue(self.manager.names)
        self.assertFalse(self.manager.view['active'])
        self.assertEqual(sum(m['op']=='videostream.subscribe' for m in self.robot.requests), before)

    def test_cancel_pending_subscribe_compensates_after_confirmation(self):
        self.manual()
        self.robot.drop_once.add('videostream.subscribe')
        self.manager.watch('stream', 0, 'avdec_h264')
        wait_until(lambda: self.robot.streams['stream']['subscribed'])
        self.manager.unsubscribe('stream')
        wait_until(lambda: not self.manager.pending and not self.manager.cleanup)
        self.assertFalse(self.robot.streams['stream']['subscribed'])
        self.assertFalse(self.manager.receivers)
        self.assertFalse(self.controller.video_views.entries)

    def test_settings_conflict_refreshes_without_stopping_other_viewers(self):
        self.manual(); self.start()
        self.robot.streams['stream']['receivers'] = 2
        self.robot.streams['stream']['settings']['bitrate'] = 4000000
        self.manager.operation_failed('stream', 'settings_conflict: changed elsewhere')
        wait_until(lambda: not self.manager.pending)
        self.assertEqual(self.manager.detail('stream')['settings']['bitrate'], 4000000)
        self.assertIn('settings_conflict', self.manager.error)
        self.assertFalse(any(m['op']=='videostream.stop' for m in self.robot.requests))
        self.assertEqual(self.manager.players['stream'].phase, 'receiving')

    def test_stop_clears_all_and_new_watch_gets_new_run(self):
        self.manual(); p = self.start()
        previous = p.info['run_id']
        self.robot.streams['stream']['receivers'] = 2
        self.manager.stop('stream')
        wait_until(lambda: not self.manager.pending)
        self.assertEqual(self.robot.streams['stream']['receivers'], 0)
        self.assertEqual(p.phase, 'stopped')
        self.start()
        self.assertNotEqual(p.info['run_id'], previous)

    def test_view_manifest_restores_only_panels(self):
        views = self.controller.video_views
        ident = views.add('stream')
        self.assertTrue(views.save())
        restored = VideoViews(Path(self.tmp.name)/'video-views.json')
        self.assertEqual(restored.entries, [dict(id=ident, stream='')])
        self.assertFalse(self.robot.requests)

    def test_h264_receiver_and_setting_validation(self):
        info = video_output('stream') | dict(rtp_port=5004)
        self.assertIn('appsink name=frames', receiver_description(info, 'avdec_h264', 30))
        for fields in (dict(encoding_name='JPEG'), dict(payload_type=26), dict(clock_rate=100)):
            with self.assertRaises(ValueError): receiver_description(info | fields, 'avdec_h264', 30)
        for value in ('nan', 'inf', '0'):
            with self.assertRaises(ValueError): setting_value(dict(type='float', min=1, max=60), value)
        with self.assertRaises(ValueError): setting_value(dict(type='int', choices=[8,10]), '9')
