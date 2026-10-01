import time
from types import SimpleNamespace
import unittest

import numpy as np
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage
from operator_gui.lab_preview import rgb_lab
from operator_gui.vision_tuning import VisionTuning
from tests.test_field_editor import Session,Control


class TuningTests(unittest.TestCase):
    def test_detector_can_start_in_game(self):
        self.control.mode = 'GAME'
        self.model.action('detection.start')
        args, kwargs = self.control.commands[-1]
        self.assertEqual(args[0], 'detection.start')
        self.assertFalse(kwargs['manual'])
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.session=Session();self.control=Control()
        image=QImage(80,65,QImage.Format.Format_RGB888);image.fill(0xff208030)
        self.video=SimpleNamespace(image=image,last_image_at=time.monotonic(),backend='runtime',image_serial=7,phase='receiving')
        self.model=VisionTuning(self.session,self.control,SimpleNamespace(players={'stream':self.video}))
        self.model.selectStream('stream')
        self.model.profile='green_field';self.model.profiles=['green_field']
        for axis,lo,hi in [('l',0,100),('a',-128,127),('b',-128,127)]:
            for suffix,value in [('min',lo),('max',hi)]:
                key=f'vision.green_field.{axis}_{suffix}'
                self.model.metas[key]={'type':'int','min':lo,'max':hi,'default':value}
                self.model.values[key]=value

    def test_standard_lab_reference(self):
        values=rgb_lab(np.array([[0,0,0],[255,255,255],[255,0,0]],np.uint8))
        assert np.allclose(values[0],[0,0,0],atol=.01)
        assert np.allclose(values[1],[100,0,0],atol=.03)
        assert np.allclose(values[2],[53.24,80.09,67.20],atol=.05)

    def test_preview_and_eyedropper_are_drafts_only(self):
        self.model.snapshot();assert not self.model.overlay.isNull()
        self.model.pick(.5,.5,8)
        assert len(self.model.drafts)==6 and not self.control.commands
        assert self.model.selected_pixels>0
        self.model.save('lab')
        args,_=self.control.commands[-1]
        assert args[0]=='params.set' and len(args[1]['values'])==6
        assert args[1]['expected_values']==self.model.values

    def test_stale_image_rejected_and_disconnect_clears_preview(self):
        self.video.last_image_at-=4;self.model.snapshot()
        assert self.model.source.isNull()
        self.video.last_image_at=time.monotonic();self.model.snapshot()
        self.session.connected=False;self.model.connection()
        assert self.model.source.isNull() and not self.model.values

    def test_text_transport_error_keeps_draft(self):
        self.model.edit('vision.green_field.l_min',20)
        self.model.failed('params.set','conflict: reload','tuning:save')
        assert self.model.drafts and 'conflict' in self.model.notice

    def test_invalid_click_has_no_effect(self):
        self.model.snapshot();self.model.pick(-.1,.3,8)
        assert not self.model.drafts

    def test_status_poll_does_not_rebuild_slider_catalog(self):
        emitted=[];self.model.catalogChanged.connect(lambda:emitted.append(True))
        self.model.status()
        self.model.response('detection.status',{},'tuning:status')
        assert not self.model.busy and not emitted

    def test_catalog_page_reads_values_in_one_request(self):
        keys=list(self.model.values)
        self.model.response('params.keys',{'items':keys},'tuning:keys:vision.')
        scheduled=self.model.queue
        batches=[item for item in scheduled if item[0]=='params.get']
        assert batches==[('params.get',{'keys':keys},'tuning:load')]
        self.model.queue=[]
        self.model.response('params.get',{'values':{keys[0]:15}},'tuning:load')
        assert self.model.values[keys[0]]==15

    def tearDown(self):
        self.model.shutdown()

    def test_live_preview_consumes_each_frame_once_without_robot_requests(self):
        self.model.live(True)
        first=self.model.serial
        self.model.preview_tick()
        assert self.model.serial==first
        self.video.image_serial+=1
        self.model.preview_tick()
        assert self.model.serial>first and self.model.view['live']
        assert not self.session.requests and not self.control.commands

    def test_live_preview_hides_stale_image_and_recovers(self):
        self.model.live(True)
        self.video.last_image_at-=4;self.model.preview_tick()
        assert self.model.source.isNull() and self.model.lab is None
        self.video.last_image_at=time.monotonic();self.video.image_serial+=1
        self.model.preview_tick()
        assert not self.model.source.isNull()

    def test_snapshot_and_pipette_freeze_live(self):
        self.model.live(True);self.model.snapshot()
        assert not self.model.view['live']
        self.model.live(True);self.model.pick(.5,.5,8)
        assert not self.model.view['live'] and self.model.drafts

    def test_disconnect_stops_live_preview(self):
        self.model.live(True);self.session.connected=False;self.model.connection()
        assert not self.model.view['live'] and self.model.source.isNull()
