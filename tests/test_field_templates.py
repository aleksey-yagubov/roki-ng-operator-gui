from copy import deepcopy
import math
import unittest

from PySide6.QtCore import QCoreApplication

from operator_gui.field_editor import FieldEditor
from operator_gui.field_templates import competition_field
from tests.test_field_editor import Session,Control


def values():
    p={'field.geometry':dict(length=3.35,width=2.35,carpet_length=4.,carpet_width=3.,
                            circle_diameter=.5,circle_measured=False,paint_width=.02)}
    for i in range(2):
        p[f'field.goal.{i}']=dict(x=(-1 if i==0 else 1)*1.675,y=0.,width=1.,height=.6,
                                colour='yellow' if i==0 else 'blue',measured=True)
    for i in range(16):
        p[f'field.mark.{i:02d}']=dict(enabled=False,kind='cross',x=0.,y=0.,size=.1,
                                    size2=.1,angle=0.,width=.02)
    return p


class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.session=Session();self.control=Control();self.editor=FieldEditor(self.session,self.control)
        self.editor.values=values()
        for key,value in self.editor.values.items():
            fields={k:'bool' if isinstance(v,bool) else
                    ['yellow','blue','white','unknown'] if k=='colour' else
                    ['cross','line','disk','ring'] if k=='kind' else [-10,15]
                    for k,v in value.items()}
            self.editor.metas[key]=dict(type='object',fields=fields,default=deepcopy(value))

    def test_geometry_centres_and_sizes_match_supplied_scheme(self):
        old=values();before=deepcopy(old)
        old['field.mark.15']['enabled']=True
        template=competition_field(old)
        assert template['field.geometry']['length']==3.4
        assert template['field.geometry']['width']==2.4
        assert template['field.geometry']['circle_diameter']==.9
        assert template['field.geometry']['paint_width']==.05
        disks=[m for k,m in template.items() if k.startswith('field.mark.') and m['enabled'] and m['kind']=='disk']
        assert len(disks)==6
        assert {(m['x'],m['y']) for m in disks}=={(x,y) for x in (-.75,.75) for y in (-.65,0,.65)}
        assert all(m['size']==.05 for m in disks)
        ticks=[template[f'field.mark.{i:02d}'] for i in (6,7,8)]
        assert [m['y'] for m in ticks]==[-.76,0,.76]
        assert all(m['x']==0 and m['angle']==0 and m['size']==.155 for m in ticks)
        assert not template['field.mark.15']['enabled']
        assert old['field.geometry']==before['field.geometry']
        assert old['field.mark.15']['enabled']  # Source map was not mutated.
        for i in range(2):
            goal=template[f'field.goal.{i}']
            assert goal['height']==.6 and goal['colour']==old[f'field.goal.{i}']['colour']
            assert abs(goal['x'])==1.7 and goal['width']==1.
        assert template['field.mark.09']['x']==-1.41
        assert template['field.mark.09']['size']==1.195
        assert template['field.mark.09']['angle']==math.pi/2
        for i,sign in ((9,-1),(12,1)):
            front=template[f'field.mark.{i:02d}']
            for j,y in ((i+1,-.5975),(i+2,.5975)):
                side=template[f'field.mark.{j:02d}']
                assert side['y']==y and side['size']==.29 and side['width']==.05
                assert abs(side['x']-sign*.145-front['x'])<1e-12
                assert abs(side['x']+sign*.145-sign*1.7)<1e-12

    def test_template_only_creates_drafts_and_discard_does_not_send(self):
        old=deepcopy(self.editor.values)
        self.editor.competitionTemplate()
        assert not self.session.requests and not self.control.commands
        assert self.editor.values==old
        assert self.editor.drafts and self.editor.view['draftCount']>=15
        self.editor.discardAll()
        assert not self.editor.drafts and self.editor.values==old

    def test_save_is_serial_and_uses_compare_and_set(self):
        self.editor.competitionTemplate()
        expected=deepcopy(self.editor.values|self.editor.drafts)
        self.editor.saveAll()
        count=0
        while self.editor.busy:
            assert len(self.control.commands)==count+1
            args,options=self.control.commands[count];op,body=args
            assert op=='params.set' and body['expected_value']==self.editor.values[body['key']]
            self.editor.response(op,body,options['context'])
            count+=1
            self.app.processEvents()
        assert self.editor.values==expected and not self.editor.drafts

    def test_failure_keeps_remaining_drafts_and_does_not_continue_writing(self):
        self.editor.competitionTemplate();self.editor.saveAll()
        args,options=self.control.commands[0]
        self.editor.failed('params.set',{'message':'conflict'},options['context'])
        self.app.processEvents()
        assert not self.editor.busy and self.editor.drafts
        assert len(self.control.commands)==1

    def test_existing_draft_is_not_silently_overwritten_by_template(self):
        self.editor.selected='field.geometry'
        self.editor.edit(self.editor.values['field.geometry']|{'length':3.1})
        before=deepcopy(self.editor.drafts)
        self.editor.competitionTemplate()
        assert self.editor.drafts==before
