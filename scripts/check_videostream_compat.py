"""GUI contract check against a separately started --simulate supervisor.

Uses ReceiverStub: verifies control/data protocol, not RTP decoding.
Never point this test at the hardware service.
"""
import sys,argparse,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication
from operator_gui.controller import Controller
from tests.test_operator import wait_until
from tests.test_video import ReceiverStub,SETTINGS
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--robot',default='127.0.0.1')
parser.add_argument('--port',type=int,default=18093)
a=parser.parse_args()
if a.port==8093:parser.error('Refusing the hardware service port; use a separate simulated supervisor')
app=QCoreApplication([])
patcher=patch('operator_gui.video.Receiver',ReceiverStub)
patcher.start()
state=tempfile.TemporaryDirectory()
c=Controller(a.robot,a.port,Path(state.name))
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
 v=c.streams
 v.refresh();wait_until(lambda:not v.pending)
 assert len(v.sources)==3,v.sources
 v.create(SETTINGS);wait_until(lambda:bool(v.last_created) and not v.pending)
 ident=v.last_created
 assert not v.players
 v.connectStream(ident,5004,'jpegdec',True)
 wait_until(lambda:ident in v.players and v.players[ident].phase=='receiving',8000)
 p=v.players[ident]
 assert p.info['attached'] and p.info['destination'][1]==5004
 before=p.info['run_id']
 view=c.video_views.add(ident);c.video_views.remove(view)
 assert p.phase=='receiving'
 c.control.release();wait_until(lambda:not c.control.owns and not c.control.pending)
 v.inspect(ident);wait_until(lambda:not v.pending);assert p.info['attached']
 v.detach(ident);wait_until(lambda:p.phase=='stopped' and not v.pending)
 c.control.acquire();wait_until(lambda:c.control.owns and not c.control.pending)
 v.connectStream(ident,5004,'jpegdec',True);wait_until(lambda:p.phase=='receiving',8000)
 assert p.info['run_id']!=before
 c.camera.refresh();wait_until(lambda:not c.camera.pending,10000)
 assert len(c.camera.keys)==6,c.camera.notice
 c.camera.edit('camera.exposure_us',7000)
 c.camera.apply(False);wait_until(lambda:not c.control.pending)
 assert c.camera.drafts['camera.exposure_us']==7000
 c.camera.apply(True);wait_until(lambda:not c.control.pending)
 assert c.camera.values['camera.exposure_us']==7000 and not c.camera.drafts
 print('PASS real simulated supervisor: catalogs, receive-before-start, lease release, detach, restart run_id, ISP apply/save',flush=True)
finally:
 c.shutdown()
 patcher.stop()
 state.cleanup()
