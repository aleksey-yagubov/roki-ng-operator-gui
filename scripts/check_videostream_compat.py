"""GUI contract check against a separately started --simulate supervisor.

Uses ReceiverStub: verifies control/data protocol, not RTP decoding.
Never point this test at the hardware service.
"""
import sys,argparse
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication
from operator_gui.controller import Controller
from tests.test_operator import wait_until
from tests.test_video import ReceiverStub,Item,SETTINGS
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--robot',default='127.0.0.1')
parser.add_argument('--port',type=int,default=18093)
a=parser.parse_args()
if a.port==8093:parser.error('Refusing the hardware service port; use a separate simulated supervisor')
app=QCoreApplication([])
with patch('operator_gui.video.Receiver',ReceiverStub):
 c=Controller(a.robot,a.port,Path('/tmp/roki-oct-client-state'))
try:
 c.transport.connect_to(a.robot,a.port)
 wait_until(lambda:c.transport.connected,8000)
 states=[]
 c.transport.response.connect(lambda op,result,context: states.append(result) if context=='simulation-check' else None)
 c.transport.request('data.snapshot',{'topic':'motion.state'},'simulation-check')
 wait_until(lambda:bool(states))
 assert states[-1]['data']['simulated'], 'This test requires --simulate'
 c.control.acquire();wait_until(lambda:c.control.owns and not c.control.pending)
 c.control.enterManual();wait_until(lambda:c.control.mode=='MANUAL' and not c.control.pending)
 v=c.video;v.item=Item()
 v.getCatalogs();wait_until(lambda:not v.catalog_pending)
 assert len(v.sources)==3,v.sources
 v.start(SETTINGS);wait_until(lambda:v.phase=='running',8000)
 ident=v.info['stream_id'];assert v.info['attached'] and v.info['destination'][1]==5004
 before=v.info['run_id'];v.closeWindow();assert v.phase=='running'
 c.control.release();wait_until(lambda:not c.control.owns and not c.control.pending)
 v.refresh();wait_until(lambda:not v.pending);assert v.info['attached']
 v.stop();wait_until(lambda:not v.info and not v.pending)
 v.getCatalogs();wait_until(lambda:not v.catalog_pending)
 assert any(s['stream_id']==ident and s['state']=='stopped' for s in v.streams),v.streams
 c.control.acquire();wait_until(lambda:c.control.owns and not c.control.pending)
 v.restartStream(ident,5004,SETTINGS['decoder']);wait_until(lambda:v.phase=='running',8000)
 assert v.info['run_id']!=before
 c.vision_tuning.refresh();wait_until(lambda:not c.vision_tuning.busy,10000)
 assert len(c.vision_tuning.keys('camera'))==6,c.vision_tuning.notice
 c.vision_tuning.edit('camera.exposure_us',7000)
 c.vision_tuning.applyCamera();wait_until(lambda:not c.control.pending)
 assert c.vision_tuning.drafts['camera.exposure_us']==7000
 c.vision_tuning.save('camera');wait_until(lambda:not c.control.pending)
 assert c.vision_tuning.values['camera.exposure_us']==7000 and not c.vision_tuning.drafts
 print('PASS real simulated supervisor: catalogs, receive-before-start, lease release, detach, restart run_id, ISP apply/save',flush=True)
finally:c.shutdown()
