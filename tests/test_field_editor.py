import unittest
from PySide6.QtCore import QCoreApplication,QObject,Signal
from operator_gui.field_editor import FieldEditor
from operator_gui.control import scalar


class Session(QObject):
    response=Signal(str,object,str)
    failed=Signal(str,object,str)
    changed=Signal()
    connected=True
    def __init__(self):super().__init__();self.requests=[]
    def request(self,*args):self.requests.append(args)


class Control:
    def __init__(self):self.commands=[]
    def command(self,*args,**kwargs):self.commands.append((args,kwargs));return True


META={'key':'field.mark.00','type':'object','default':{'x':0.,'y':0.,'enabled':False},
      'fields':{'x':[-10.,10.],'y':[-10.,10.],'enabled':'bool'}}


class FieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.session=Session();self.control=Control();self.editor=FieldEditor(self.session,self.control)
        self.editor.metas[META['key']]=META
        self.editor.values[META['key']]=dict(META['default'])
        self.editor.select(META['key'])

    def test_drag_is_draft_and_roundtrips_on_ack(self):
        self.editor.place(.71,-.22)
        assert not self.control.commands
        assert self.editor.values[META['key']]['x']==0
        self.editor.save()
        args,kw=self.control.commands[-1]
        assert args[0]=='params.set' and args[1]['value']['x']==.71
        self.editor.response('params.set',args[1],kw['context'])
        assert not self.editor.drafts
        assert self.editor.values[META['key']]['y']==-.22

    def test_reset_does_not_write_robot(self):
        self.editor.place(1,2);self.editor.defaults()
        assert self.editor.view['draft']==META['default']
        assert not self.control.commands

    def test_invalid_number_and_disconnect(self):
        with self.assertRaises(ValueError):scalar(META,{'x':'nan','y':1,'enabled':False})
        self.editor.place(1,2);self.session.connected=False;self.editor.connection()
        assert not self.editor.values and not self.editor.drafts

    def test_empty_catalog_still_reads_side(self):
        self.editor.response('params.keys',{'items':[],'next_offset':None},'field:keys')
        assert self.session.requests[-1][:2]==('params.get',{'key':'match.own_goal'})

    def test_read_failure_preserves_draft(self):
        self.editor.place(1,2)
        self.editor.failed('params.set',{'message':'disk full'},'field:save:field.mark.00')
        assert self.editor.drafts and 'disk full' in self.editor.notice
