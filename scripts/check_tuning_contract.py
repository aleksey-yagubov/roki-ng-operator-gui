"""Actual GUI models -> MessagePack -> supervisor dispatch, mocked hardware.

No sockets or robot actions. Complements, does not replace, Linux/robot tests.
"""
import asyncio
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'roki-ng')]
from PySide6.QtCore import QObject,Signal,QTimer,QCoreApplication
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from operator_gui.vision_tuning import VisionTuning
from operator_gui.field_editor import FieldEditor
from roki_ng.supervisor import Supervisor
from roki_ng.parameters import Parameters
from roki_ng.wire import envelope,pack,unpack,Fault


class Session(QObject):
    response=Signal(str,object,str)
    failed=Signal(str,str,str)
    changed=Signal()
    connected=True
    def __init__(self,server):
        super().__init__();self.server=server;self.largest=0;self.errors=[];self.requests=0
    def request(self,op,body=None,context=''):
        self.requests+=1
        def deliver():
            try:
                data=pack(envelope('request',op,body or {},session=2**63,token=2**63,id=self.requests))
                self.largest=max(self.largest,len(data))
                body_copy=unpack(data)['body']
                result=asyncio.run(self.server.dispatch(None,op,body_copy))
                data=pack(envelope('response',op,{'result':result},session=2**63,token=2**63,id=self.requests))
                self.largest=max(self.largest,len(data))
                self.response.emit(op,unpack(data)['body']['result'],context)
            except Fault as exc:
                self.errors.append(str(exc));self.failed.emit(op,str(exc),context)
        QTimer.singleShot(0,deliver)


class Control:
    def __init__(self,session):self.session=session
    def command(self,op,body,**options):
        self.session.request(op,body|{'lease_epoch':1},options['context']);return True


def wait(predicate):
    deadline=time.monotonic()+4
    while not predicate() and time.monotonic()<deadline:QTest.qWait(1)
    assert predicate(),'Contract timed out'


def main():
    app=QCoreApplication([])
    with tempfile.TemporaryDirectory() as directory:
        server=Supervisor({'state_dir':directory});server.require_control=lambda *args:None
        server.workers={k:SimpleNamespace(call=AsyncMock(return_value={})) for k in ('camera','detection','localisation')}
        session=Session(server);control=Control(session)
        tuning=VisionTuning(session,control,SimpleNamespace(image=QImage()))
        field=FieldEditor(session,control)
        tuning.refresh();wait(lambda:not tuning.busy)
        assert len(tuning.profiles)==6 and 'camera.awb_enabled' in tuning.metas
        tuning.select('white_marking')
        tuning.edit('vision.white_marking.l_min',12);tuning.edit('vision.white_marking.l_max',42)
        tuning.save('lab');wait(lambda:not tuning.drafts)
        assert Parameters(directory).values['vision.white_marking.l_max']==42
        tuning.edit('camera.awb_enabled',True);tuning.save('camera');wait(lambda:not tuning.drafts)
        assert Parameters(directory).values['camera.awb_enabled'] is True
        field.refresh();wait(lambda:not field.busy)
        assert len(field.metas)==19
        field.addMark();field.place(.5,-.3);field.save();wait(lambda:not field.drafts)
        assert Parameters(directory).values['field.mark.00']['x']==.5
        assert not session.errors,session.errors
        print(f'PASS: {session.requests} requests, largest datagram {session.largest}/1400 bytes; hardware mocked')


if __name__=='__main__':main()
