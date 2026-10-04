"""Field draft UI over the existing params transport; no independent storage."""
from copy import deepcopy

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer

from .control import scalar


class FieldEditor(QObject):
    changed=Signal()

    def __init__(self,session,control,parent=None):
        super().__init__(parent)
        self.session,self.control=session,control
        self.values={};self.metas={};self.drafts={}
        self.selected='field.geometry';self.pending=[];self.notice='Загрузите карту с робота.'
        self.busy=False
        self.save_queue=[]
        session.response.connect(self.response)
        session.failed.connect(self.failed)
        session.changed.connect(self.connection)

    @Property('QVariantMap',notify=changed)
    def view(self):
        own=self.values.get('match.own_goal')
        colours=[self.values.get(f'field.goal.{i}',{}).get('colour','unknown') for i in range(2)]
        return dict(ownColour=colours[own] if own in (0,1) else '',
                    ownColourReady=set(colours)=={'yellow','blue'} and not self.drafts and not self.busy,
                    values=self.values|self.drafts,selected=self.selected,
                    meta=self.metas.get(self.selected,{}),
                    draft=self.drafts.get(self.selected,self.values.get(self.selected,{})),
                    dirty=self.selected in self.drafts,notice=self.notice,busy=self.busy,
                    available=bool(self.metas),keys=list(self.values),draftCount=len(self.drafts))

    @Slot()
    def connection(self):
        if not self.session.connected:
            self.busy=False;self.pending=[];self.values={};self.metas={};self.drafts={}
            self.save_queue=[]
            self.notice='Нет соединения. Загрузите профиль после подключения.'
            self.changed.emit()

    @Slot()
    def refresh(self):
        if not self.session.connected or self.busy:return
        if self.drafts:
            self.notice='Сохраните или отмените черновики перед загрузкой.';self.changed.emit();return
        self.busy=True;self.values={};self.metas={};self.pending=[]
        self.session.request('params.keys',{'prefix':'field.','limit':8},'field:keys')
        self.changed.emit()

    def next(self):
        if self.pending:
            op,key=self.pending.pop(0)
            self.session.request(op,{'key':key},'field:load')
        else:
            self.busy=False;self.notice='Загружено. Изменения карты действуют со следующего запуска локализации.'
        self.changed.emit()

    def response(self,op,result,context):
        if context=='field:keys':
            for key in result['items']:
                self.pending.extend([('params.describe',key),('params.get',key)])
            cursor=result.get('next_offset')
            if cursor is not None:
                self.session.request('params.keys',{'prefix':'field.','offset':cursor,'limit':8},context)
            else:
                self.pending.append(('params.get','match.own_goal'));self.next()
        elif context=='field:load':
            key=result['key']
            if op=='params.describe':self.metas[key]=result
            else:self.values[key]=result['value']
            self.next()
        elif context.startswith('field:save:'):
            key=result['key'];self.values[key]=result['value'];self.drafts.pop(key,None)
            self.notice='Сохранено на роботе. Применится при следующем запуске локализации.'
            self.changed.emit()
        elif context.startswith('field:template-save:'):
            key=result['key'];self.values[key]=result['value'];self.drafts.pop(key,None)
            self.changed.emit()
            QTimer.singleShot(0,self.saveNext)

    def failed(self,op,error,context):
        if context.startswith('field:'):
            self.busy=False;self.pending=[]
            self.save_queue=[]
            self.notice=str(error.get('message',error) if isinstance(error,dict) else error)
            if context.startswith('field:template-save:'):
                self.notice+=' Часть карты могла сохраниться; оставшиеся черновики сохранены в GUI. Не запускайте игру до завершения карты.'
            self.changed.emit()

    @Slot(str)
    def select(self,key):
        if key in self.metas:self.selected=key;self.changed.emit()

    @Slot('QVariant')
    def edit(self,value):
        if self.busy:return
        try:
            self.drafts[self.selected]=scalar(self.metas[self.selected],value)
            self.notice='Черновик. Робот пока использует сохранённую карту.'
        except (ValueError,KeyError,TypeError) as exc:self.notice=str(exc)
        self.changed.emit()

    @Slot()
    def defaults(self):
        if self.busy:return
        if self.selected in self.metas:
            self.drafts[self.selected]=deepcopy(self.metas[self.selected]['default'])
            self.changed.emit()

    @Slot()
    def discard(self):
        if self.busy:return
        self.drafts.pop(self.selected,None);self.changed.emit()

    @Slot()
    def save(self):
        if self.busy:return
        if self.selected not in self.drafts:return
        self.control.command('params.set',{'key':self.selected,'value':self.drafts[self.selected],
            'expected_value':self.values[self.selected]},
            manual=False,job=False,context='field:save:'+self.selected)

    @Slot(int)
    def ownGoal(self,index):
        if index not in (0,1) or 'match.own_goal' not in self.values:return
        self.control.command('params.set',{'key':'match.own_goal','value':index,
            'expected_value':self.values['match.own_goal']},
            manual=False,job=False,context='field:save:match.own_goal')

    @Slot(str)
    def ownColour(self,colour):
        if not self.view['ownColourReady']:
            self.notice='Сначала сохраните карту с одними жёлтыми и одними синими воротами.'
            self.changed.emit();return
        for index in (0,1):
            if self.values[f'field.goal.{index}']['colour']==colour:
                self.ownGoal(index);return

    @Slot(float,float)
    def place(self,x,y):
        value=deepcopy(self.drafts.get(self.selected,self.values.get(self.selected,{})))
        if not isinstance(value,dict) or 'x' not in value:return
        value.update(x=round(x,3),y=round(y,3))
        self.edit(value)

    @Slot()
    def addMark(self):
        if self.busy:return
        for key,value in (self.values|self.drafts).items():
            if key.startswith('field.mark.') and not value['enabled']:
                self.selected=key
                value=deepcopy(self.metas[key]['default']);value['enabled']=True
                self.edit(value);return
        self.notice='Нет свободного места: максимум 16 дополнительных меток.';self.changed.emit()

    @Slot()
    def removeMark(self):
        if self.busy:return
        if self.selected.startswith('field.mark.'):
            value=deepcopy(self.drafts.get(self.selected,self.values[self.selected]))
            value['enabled']=False;self.edit(value)

    @Slot()
    def competitionTemplate(self):
        if self.busy:return
        if self.drafts:
            self.notice='Сохраните или отмените текущие черновики перед выбором шаблона.'
            self.changed.emit();return
        from .field_templates import competition_field
        try:
            draft=competition_field(self.values)
            # Validate everything before replacing any draft.
            draft={k:scalar(self.metas[k],v) for k,v in draft.items()}
        except (KeyError,ValueError,TypeError):
            self.notice='Сначала полностью загрузите карту с робота.'
            self.changed.emit();return
        self.drafts={k:v for k,v in draft.items() if v!=self.values[k]}
        self.selected='field.geometry'
        self.notice=('Черновик 3,40 × 2,40 м: 6 точек Ø5 см, 3 палочки 15,5 см, '
                     'вратарские площадки. Проверьте толщину краски и ворота; '
                     'сохранение заменит прежние метки. Робот пока не изменён.')
        self.changed.emit()

    @Slot()
    def discardAll(self):
        if self.busy:return
        self.drafts={};self.notice='Черновики отменены. На роботе ничего не изменено.'
        self.changed.emit()

    @Slot()
    def saveAll(self):
        if self.busy or not self.drafts:return
        self.save_queue=list(self.drafts)
        self.busy=True
        self.notice='Сохранение карты по объектам. Не запускайте локализацию/игру до завершения.'
        self.changed.emit();self.saveNext()

    def saveNext(self):
        if not self.busy:return
        if not self.save_queue:
            self.busy=False
            self.notice='Вся карта сохранена. Перезапустите локализацию для применения.'
            self.changed.emit();return
        key=self.save_queue.pop(0)
        if not self.control.command('params.set',{'key':key,'value':deepcopy(self.drafts[key]),
                                    'expected_value':self.values[key]},manual=False,job=False,
                                    context='field:template-save:'+key):
            self.busy=False;self.save_queue=[]
            self.notice='Сохранение остановлено. Несохранённые черновики оставлены; проверьте управление.'
            self.changed.emit()
