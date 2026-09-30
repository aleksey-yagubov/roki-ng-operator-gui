import time
import unittest
from PySide6.QtCore import QCoreApplication, QObject, Signal
from operator_gui.localisation import Localisation


class Session(QObject):
    response=Signal(str,object,str)
    failed=Signal(str,str,str)
    changed=Signal()
    connected=True
    def __init__(self):
        super().__init__();self.requests=[]
    def request(self,*args):self.requests.append(args)


class Control:
    error='Нет управления'
    def __init__(self):self.commands=[];self.allow=True
    def command(self,*args,**kw):self.commands.append((args,kw));return self.allow


class LocalisationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])
    def setUp(self):
        self.session=Session();self.control=Control()
        self.model=Localisation(self.session,self.control)
    def tearDown(self):self.model.shutdown()
    def result(self,**kw):
        state=dict(running=True,age_ms=10,result={'valid':False,'candidate':[1.,.2,.4]})
        state.update(kw)
        self.session.response.emit('localisation.status',state,'localisation:status')
    def test_rejected_goal_candidates_explain_missing_boxes(self):
        self.result(result={'goal_rejected':4,'fit_state':'ambiguous','ambiguous':True})
        self.assertIn('без подтверждения ворот: 4',self.model.view['problems'])
        self.assertEqual(self.model.view['pose'],[])

    def test_no_implicit_start_or_requests(self):
        self.assertFalse(self.session.requests)
        self.assertFalse(self.control.commands)
    def test_capabilities_gate_and_radians(self):
        self.model.start(0,0,90)
        self.assertFalse(self.control.commands)
        self.session.response.emit('system.capabilities',{'localisation':{'mode':'diagnostic_only'}},'localisation:capabilities')
        self.model.start(1,2,90)
        self.assertAlmostEqual(self.control.commands[-1][0][1]['prior'][2],1.57079632679)
    def test_stale_and_disconnected_candidates_are_hidden(self):
        self.result();self.assertEqual(len(self.model.view['pose']),3)
        self.model.received=time.monotonic()-2
        self.assertEqual(self.model.view['pose'],[])
        self.result();self.session.connected=False;self.session.changed.emit()
        self.assertEqual(self.model.view['pose'],[])
    def test_null_fault_stopped_nonfinite_are_hidden(self):
        for kw in ({'running':False},{'error':'worker died'},{'result':None},
                   {'result':{'candidate':[float('nan'),0,0]}}):
            self.result(**kw);self.assertEqual(self.model.view['pose'],[])
    def test_poll_does_not_accumulate_and_barrier_releases(self):
        self.model.available=True
        self.model.refresh();self.model.refresh()
        self.assertEqual(len(self.session.requests),1)
        self.model.barrier();self.model.refresh()
        self.assertEqual(len(self.session.requests),2)
    def test_rejected_command_visible(self):
        self.control.allow=False;self.model.available=True
        self.model.start(0,0,0)
        self.assertEqual(self.model.view['notice'],'Нет управления')
    def test_stop_does_not_require_manual(self):
        self.model.stop()
        self.assertFalse(self.control.commands[-1][1]['manual'])

    def test_capability_failure_message_survives_heartbeat(self):
        self.model.connection()
        self.session.response.emit('system.capabilities',{},'localisation:capabilities')
        self.session.changed.emit()
        self.assertIn('не поддерживает',self.model.view['notice'])

    def test_check_is_visible_bounded_and_unsupported_is_not_stopped(self):
        self.model.check();self.model.check()
        self.assertTrue(self.model.view['checking'])
        self.assertEqual(len(self.session.requests),1)
        self.assertIn('Проверяю',self.model.view['status'])
        self.session.response.emit('system.capabilities',{},'localisation:capabilities')
        self.assertFalse(self.model.view['checking'])
        self.assertIn('Нужно обновить',self.model.view['status'])

    def test_failed_check_can_be_retried(self):
        self.model.check()
        self.session.failed.emit('system.capabilities','timeout','localisation:capabilities')
        self.assertFalse(self.model.view['checking'])
        self.assertIn('timeout',self.model.view['notice'])
        self.model.check()
        self.assertEqual(len(self.session.requests),2)

    def test_success_remains_visible_after_status_response(self):
        self.model.check()
        self.session.response.emit('system.capabilities', {'localisation': {'mode': 'diagnostic_only'}}, 'localisation:capabilities')
        self.session.response.emit('localisation.status', {'running': False, 'error': None}, 'localisation:status')
        self.assertIn('Проверка успешна', self.model.view['notice'])
        self.assertIn('доступна', self.model.view['status'])
        self.assertIn('Камера + IMU', self.model.view['notice'])
        self.assertFalse(self.control.commands)

    def test_capability_check_starts_bounded_status_updates(self):
        self.session.response.emit('system.capabilities', {'localisation': {}}, 'localisation:capabilities')
        self.assertTrue(self.model.view['watching'])
        self.assertTrue(self.model.pending)
        self.model.refresh()
        self.assertEqual(len(self.session.requests), 1)
        self.model.watch(False)
        self.assertFalse(self.model.view['watching'])

    def test_ambiguous_pose_is_not_reported_as_localised(self):
        self.model.checked=self.model.available=True
        self.result(result={'candidate':[1.,0.,0.], 'ambiguous':True})
        self.assertIn('неоднозначно', self.model.view['status'])

    def test_camera_start_waits_for_completion_without_more_retries(self):
        from operator_gui.transport import Transport
        from unittest.mock import patch
        t=Transport(); failures=[]
        t.failed.connect(lambda *args: failures.append(args))
        t.pending[1]=dict(op='camera.start',context='',attempts=5,deadline=1.25,expires=20.)
        with patch('operator_gui.transport.time.monotonic', return_value=2.):
            t._tick()
        self.assertFalse(failures)
        self.assertEqual(t.pending[1]['attempts'],5)
        with patch('operator_gui.transport.time.monotonic', return_value=21.):
            t._tick()
        self.assertEqual(len(failures),1)
        self.assertFalse(t.pending)

    def test_unresolved_or_rejected_pose_never_jumps_on_map(self):
        for state in ({'ambiguous':True}, {'fit_state':'weak'}, {'fit_state':'rejected','reason':'motion_discontinuity'}):
            self.result(result={'candidate':[1.,1.,3.], **state})
            self.assertEqual(self.model.view['pose'],[])
