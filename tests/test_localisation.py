import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QObject, Signal
from operator_gui.localisation import Localisation
from operator_gui.data_sources import DataSources


class Session(QObject):
    response=Signal(str,object,str)
    failed=Signal(str,str,str)
    changed=Signal()
    welcomed=Signal(object)
    connected=True
    def __init__(self):
        super().__init__();self.requests=[]
    def request(self,*args):self.requests.append(args)


class Control:
    mode='MANUAL'
    error='Нет управления'
    def __init__(self):self.commands=[];self.allow=True
    def command(self,*args,**kw):self.commands.append((args,kw));return self.allow


class LocalisationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])
    def setUp(self):
        self.session=Session();self.control=Control()
        self.sources=DataSources(self.session)
        self.model=Localisation(self.session,self.control,self.sources)
    def tearDown(self):
        self.model.shutdown()
        self.sources.shutdown()
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
    def test_status_requests_do_not_accumulate_and_barrier_releases(self):
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
        self.assertIn('панели «Камера»', self.model.view['notice'])
        self.assertFalse(self.control.commands)

    def test_capability_check_only_requests_one_status(self):
        self.session.response.emit('system.capabilities', {'localisation': {}}, 'localisation:capabilities')
        self.assertFalse(self.model.view['watching'])
        self.assertTrue(self.model.pending)
        self.model.refresh()
        self.assertEqual(len(self.session.requests), 1)
        self.assertFalse(hasattr(self.model, 'timer'))

    def subscribe(self):
        self.model.watch(True)
        self.session.response.emit('data.subscribe', {'subscription_id':'localisation.state', 'rate_hz':2}, 'localisation.state')

    def test_explicit_shared_datastream_without_catalog_or_control(self):
        self.model.watch(True)
        self.model.watch(True)
        self.assertEqual(self.session.requests, [
            ('data.subscribe', {'topic':'localisation.state','rate_hz':2}, 'localisation.state')])
        self.assertTrue(self.model.view['subscriptionPending'])
        self.session.response.emit('data.subscribe', {'subscription_id':'localisation.state', 'rate_hz':2}, 'localisation.state')
        self.model.watch(True)
        self.assertEqual(len(self.session.requests), 1)
        self.assertTrue(self.model.view['subscribed'])
        self.assertFalse(self.control.commands)
        self.sources.unsubscribe_topic('localisation.state')
        self.session.response.emit('data.unsubscribe', {}, 'localisation.state')
        self.assertFalse(self.model.view['watching'])

    def test_samples_update_pose_and_account_for_heartbeat_age(self):
        self.subscribe()
        sample = dict(topic='localisation.state', sequence=1, valid=False, age_ms=500,
                      data=dict(running=True, age_ms=100, result=dict(candidate=[1.,2.,0.], valid=True)))
        self.sources.notification(sample)
        self.assertEqual(self.model.view['pose'], [1.,2.,0.])
        self.assertFalse(self.model.view['result']['valid'])
        self.assertGreaterEqual(self.model.view['ageMs'], 600)
        self.sources.notification(dict(sample, data=dict(running=False)))
        self.assertEqual(self.model.view['pose'], [1.,2.,0.], 'Old sequence must be ignored')
        self.sources.notification(dict(sample, sequence=2, age_ms=1500))
        self.assertFalse(self.model.view['fresh'])
        self.assertEqual(self.model.view['pose'], [])
        self.assertEqual(len(self.session.requests), 1, 'Samples must not issue status requests')

    def test_subscription_failure_can_be_retried(self):
        self.model.watch(True)
        self.session.failed.emit('data.subscribe', 'not_found', 'localisation.state')
        self.assertFalse(self.model.view['watching'])
        self.assertIn('not_found', self.model.view['notice'])
        self.model.watch(True)
        self.assertEqual(len(self.session.requests), 2)

    def test_disconnect_does_not_automatically_restore_localisation_subscription(self):
        self.subscribe()
        self.session.connected=False
        self.session.changed.emit()
        self.assertFalse(self.model.view['watching'])
        self.session.connected=True
        self.session.changed.emit()
        self.assertEqual(len(self.session.requests), 1)

    def test_unknown_age_does_not_show_pose_as_fresh(self):
        self.subscribe()
        for age in (None, -1, float('nan'), '10'):
            self.model.sample('localisation.state', dict(age_ms=age, data=dict(
                running=True, age_ms=10, result=dict(candidate=[1.,2.,0.]))))
            self.assertFalse(self.model.view['fresh'])

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

    def test_old_pose_remains_display_only_when_stale(self):
        with patch('operator_gui.localisation.time.monotonic', return_value=100.):
            self.result()
        with patch('operator_gui.localisation.time.monotonic', return_value=102.):
            view = self.model.view
            self.assertEqual(view['pose'], [])
            self.assertEqual(view['lastPose'], [1., .2, .4])
            self.assertEqual(view['lastPoseAgeMs'], 2010)
            self.assertFalse(view['fresh'])

    def test_bad_candidates_never_replace_last_usable_pose(self):
        self.result()
        for state in ({'fit_state':'weak'}, {'fit_state':'ambiguous'},
                      {'fit_state':'rejected', 'reason':'motion_discontinuity'}):
            self.result(result={'candidate':[5., 4., 3.], **state})
            self.assertEqual(self.model.view['pose'], [])
            self.assertEqual(self.model.view['questionablePose'], [5., 4., 3.])
            self.assertEqual(self.model.view['lastPose'], [1., .2, .4])

    def test_missing_and_nonfinite_coordinates_are_not_drawn(self):
        for pose in (None, [], [float('inf'), 0, 0]):
            self.result(result={'candidate':pose, 'fit_state':'rejected'})
            self.assertEqual(self.model.view['questionablePose'], [])

    def test_insufficient_observations_is_explicit_and_keeps_last_pose(self):
        self.model.checked = self.model.available = True
        self.result()
        self.result(result={'candidate':None, 'reason':'insufficient_observations', 'lines':2})
        self.assertIn('insufficient_observations', self.model.view['status'])
        self.assertIn('отрезков 2', self.model.view['resultSummary'])
        self.assertEqual(self.model.view['lastPose'], [1., .2, .4])
        self.assertEqual(self.model.view['questionablePose'], [])

    def test_new_capture_or_map_and_disconnect_clear_cached_pose(self):
        for key in ('capture_id', 'configuration_id', 'geometry'):
            self.result(**{key:'old'})
            self.result(result=None, **{key:'new'})
            self.assertEqual(self.model.view['lastPose'], [])
        self.result()
        self.session.connected = False
        self.session.changed.emit()
        self.assertEqual(self.model.view['lastPose'], [])

    def test_unknown_age_and_stale_bad_candidates_are_not_current(self):
        self.result(age_ms=None)
        self.assertEqual(self.model.view['lastPose'], [])
        self.result(age_ms=2000, result={'candidate':[1.,2.,0.], 'fit_state':'weak'})
        self.assertEqual(self.model.view['questionablePose'], [])
