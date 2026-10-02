"""GUI contract check against a local, isolated --simulate supervisor.

Uses ReceiverStub: verifies control/data protocol, not RTP decoding.
Never point this test at the hardware service.
"""
import sys,argparse,tempfile,socket,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication
from operator_gui.controller import Controller
from tests.test_operator import wait_until
from tests.test_video import ReceiverStub
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-dir',type=Path,default=Path(__file__).resolve().parents[2]/'roki-ng')
a=parser.parse_args()
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
 probe.bind(('127.0.0.1',0))
 port=probe.getsockname()[1]
app=QCoreApplication([])
patcher=patch('operator_gui.video.Receiver',ReceiverStub)
patcher.start()
state=tempfile.TemporaryDirectory()
log=tempfile.TemporaryFile(mode='w+')
process=subprocess.Popen([sys.executable,'-m','roki_ng','--simulate','--skip-bootstrap',
 '--host','127.0.0.1','--port',str(port),'--state-dir',state.name],
 cwd=a.runtime_dir,stdout=log,stderr=subprocess.STDOUT)
c=Controller('127.0.0.1',port,Path(state.name))
try:
 c.transport.connect_to('127.0.0.1',port)
 wait_until(lambda:c.transport.connected,8000)
 states=[]
 c.transport.response.connect(lambda op,result,context: states.append(result) if context=='simulation-check' else None)
 c.transport.request('data.snapshot',{'topic':'motion.state'},'simulation-check')
 wait_until(lambda:bool(states))
 assert states[-1]['data']['simulated'], 'This test requires --simulate'
 wait_until(lambda:c.control.mode=='IDLE',10000)
 c.control.acquire();wait_until(lambda:c.control.owns and not c.control.pending)
 c.control.enterManual();wait_until(lambda:c.control.mode=='MANUAL' and not c.control.pending)
 v=c.streams
 v.refresh();wait_until(lambda:not v.pending)
 assert len(v.names)==3,v.names
 ident='stream'
 assert not v.players
 v.watch(ident,0,'avdec_h264')
 wait_until(lambda:ident in v.players and v.players[ident].phase=='receiving',8000)
 p=v.players[ident]
 assert p.info['subscribed'] and p.port>0
 before=p.info['run_id']
 view=c.video_views.add(ident);c.video_views.remove(view)
 assert p.phase=='receiving'
 c.control.release();wait_until(lambda:not c.control.owns and not c.control.pending)
 v.inspect(ident);wait_until(lambda:not v.pending);assert p.info['subscribed']
 v.unsubscribe(ident);wait_until(lambda:p.phase=='stopped' and not v.pending)
 c.control.acquire();wait_until(lambda:c.control.owns and not c.control.pending)
 v.watch(ident,0,'avdec_h264');wait_until(lambda:p.phase=='receiving',8000)
 assert p.info['run_id']!=before
 c.camera.refresh();wait_until(lambda:not c.camera.pending,10000)
 assert len(c.camera.keys)==6,c.camera.notice
 c.camera.edit('camera.exposure_us',7000)
 c.camera.apply(False);wait_until(lambda:not c.control.pending)
 assert c.camera.drafts['camera.exposure_us']==7000
 c.camera.apply(True);wait_until(lambda:not c.control.pending)
 assert c.camera.values['camera.exposure_us']==7000 and not c.camera.drafts
 print('PASS real simulated supervisor: named outputs, receiver-before-subscribe, lease release, unsubscribe, restart run_id, ISP apply/save',flush=True)
finally:
 c.shutdown()
 process.terminate()
 try: process.wait(timeout=8)
 except subprocess.TimeoutExpired:
  process.kill();process.wait()
 log.seek(0)
 if sys.exc_info()[0]: print(log.read())
 log.close()
 patcher.stop()
 state.cleanup()
