"""LAB tuning from an explicitly selected shared receiver; no camera ownership."""
import time

from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer,Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from .control import scalar


class TuningImages(QQuickImageProvider):
    def __init__(self,model):super().__init__(QQuickImageProvider.ImageType.Image);self.model=model
    def requestImage(self,ident,size,requested_size):
        image=self.model.overlay if ident.startswith('mask') else self.model.source
        size.setWidth(image.width());size.setHeight(image.height());return image


class VisionTuning(QObject):
    changed=Signal()
    catalogChanged=Signal()
    def __init__(self,session,control,streams,parent=None):
        super().__init__(parent)
        self.session,self.control,self.streams=session,control,streams
        self.preview_stream=''
        self.metas={};self.values={};self.drafts={};self.profiles=[];self.profile=''
        self.queue=[];self.busy=False;self.notice='Загрузите настройки с робота.'
        self.catalog_dirty=False
        self.detector={};self.source=QImage();self.overlay=QImage()
        self.detector_mode='colour'
        self.lab=self.rgb=None;self.serial=0;self.selected_pixels=0;self.source_label='Нет снимка'
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.status)
        self.preview_timer=QTimer(self);self.preview_timer.setInterval(200);self.preview_timer.timeout.connect(self.preview_tick)
        self.preview_frame=None
        session.response.connect(self.response);session.failed.connect(self.failed);session.changed.connect(self.connection)

    def keys(self,scope):
        prefix='vision.'+self.profile+'.'
        return [k for k in self.metas if k.startswith(prefix)]

    def rows(self,scope):
        return [dict(key=k,meta=self.metas[k],value=self.drafts.get(k,self.values.get(k))) for k in self.keys(scope)]

    @Property('QStringList',notify=catalogChanged)
    def labKeys(self):return self.keys('lab')

    @Property('QVariantMap',notify=changed)
    def view(self):
        return dict(profiles=self.profiles,profile=self.profile,labRows=self.rows('lab'),
            busy=self.busy,notice=self.notice,previewStream=self.preview_stream,detector=self.detector,detectorMode=self.detector_mode,
            serial=self.serial,hasImage=not self.source.isNull(),pixels=self.selected_pixels,sourceLabel=self.source_label,
            live=self.preview_timer.isActive(),dirty=bool(self.drafts),watching=self.timer.isActive(),metas=self.metas,values=self.values|self.drafts)

    @Slot()
    def connection(self):
        if not self.session.connected:
            self.preview_timer.stop();self.preview_frame=None
            self.timer.stop();self.queue=[];self.busy=False;self.metas={};self.values={};self.drafts={}
            self.profiles=[];self.profile='';self.preview_stream='';self.detector={}
            self.source=QImage();self.overlay=QImage();self.lab=self.rgb=None;self.serial+=1
            self.notice='Нет соединения. Перечитайте настройки после подключения.';self.catalogChanged.emit();self.changed.emit()

    def next(self):
        if self.queue:
            self.busy=True;op,args,context=self.queue.pop(0);self.session.request(op,args,context)
        else:
            self.busy=False
            if self.catalog_dirty:self.catalog_dirty=False;self.catalogChanged.emit()
        self.changed.emit()

    @Slot()
    def refresh(self):
        if self.busy or not self.session.connected:return
        if self.drafts:self.notice='Сохраните или отмените черновик перед загрузкой.';self.changed.emit();return
        self.metas={};self.values={}
        self.catalog_dirty=True
        self.queue=[('detection.list',{},'tuning:profiles')]
        for prefix in ('vision.',):
            self.queue.append(('params.keys',{'prefix':prefix,'limit':8},'tuning:keys:'+prefix))
        self.next()

    @Slot()
    def status(self):
        if self.busy or not self.session.connected:return
        self.queue=[('detection.status',{},'tuning:status')];self.next()

    @Slot(bool)
    def watch(self,enabled):
        if enabled and self.session.connected:self.timer.start();self.status()
        else:self.timer.stop()
        self.changed.emit()

    def response(self,op,result,context):
        if not context.startswith('tuning:'):return
        if context=='tuning:profiles':
            self.profiles=result['profiles']
            if self.profile not in self.profiles:self.profile=self.profiles[0] if self.profiles else ''
        elif context.startswith('tuning:keys:'):
            prefix=context.split(':',2)[2]
            requests=[]
            for key in result['items']:
                requests.append(('params.describe',{'key':key},'tuning:load'))
            if result['items']:
                requests.append(('params.get',{'keys':result['items']},'tuning:load'))
            if result.get('next_offset') is not None:
                requests.append(('params.keys',{'prefix':prefix,'offset':result['next_offset'],'limit':8},context))
            self.queue=requests+self.queue
        elif context=='tuning:load':
            if op=='params.describe':self.metas[result['key']]=result
            elif 'values' in result:self.values.update(result['values'])
            else:self.values[result['key']]=result['value']
        elif context=='tuning:save':
            self.values.update(result['values'])
            for key in result['values']:self.drafts.pop(key,None)
            self.notice='Настройки сохранены на роботе.';self.recompute();self.changed.emit();return
        elif context=='tuning:status':
            self.detector=result
        elif context=='tuning:action':
            self.detector=result
            if op=='detection.start':
                self.timer.start()
                self.notice='Проверка запущена. В «Стримах» обновите список и смотрите detection. Используются сохранённые параметры.'
            else:
                self.notice='Проверка остановлена; камера и игровое зрение не отключаются.'
            self.changed.emit();return
        self.next()

    def failed(self,op,error,context):
        if context.startswith('tuning:'):
            self.notice=str(error.get('message',error) if isinstance(error,dict) else error)
            self.busy=False;self.queue=[];self.catalogChanged.emit();self.changed.emit()

    @Slot(str)
    def select(self,profile):
        if profile in self.profiles:self.profile=profile;self.recompute();self.catalogChanged.emit();self.changed.emit()

    @Slot(str,'QVariant')
    def edit(self,key,value):
        try:self.drafts[key]=scalar(self.metas[key],value);self.recompute()
        except (KeyError,ValueError,TypeError) as exc:self.notice=str(exc)
        self.changed.emit()

    @Slot(str)
    def defaults(self,scope):
        for key in self.keys(scope):self.drafts[key]=self.metas[key]['default']
        self.recompute();self.changed.emit()

    @Slot()
    def discard(self):self.drafts={};self.recompute();self.changed.emit()

    @Slot(str)
    def save(self,scope):
        if self.busy:return
        keys=[k for k in self.keys(scope) if k in self.drafts]
        if not keys:return
        self.control.command('params.set',{'values':{k:self.drafts[k] for k in keys},
            'expected_values':{k:self.values[k] for k in keys}},manual=False,job=False,context='tuning:save')

    @Slot(str)
    def selectDetector(self,mode):
        if mode in ('colour','ball'):
            self.detector_mode=mode;self.changed.emit()

    @Slot(str)
    def action(self,op):
        if op not in ('detection.start','detection.stop'):return
        if op=='detection.start' and self.detector_mode=='colour' and self.profile not in self.profiles:
            self.notice='Сначала загрузите настройки и выберите цветовой фильтр.';self.changed.emit();return
        args=({'mode':self.detector_mode,'profile':self.profile} if self.detector_mode=='colour'
              else {'mode':'ball'}) if op=='detection.start' else {}
        if op=='detection.start' and self.detector_mode=='ball' and self.control.mode=='GAME':
            self.notice='Остановите игру перед отдельной диагностикой мяча.';self.changed.emit();return
        sent=self.control.command(op,args,manual=op.endswith('.start') and self.control.mode != 'GAME',job=False,context='tuning:action')
        if not sent:
            self.notice=self.control.error;self.changed.emit()

    @Slot(bool)
    def live(self,enabled):
        if enabled and self.session.connected:
            self.preview_timer.start()
            self.preview_frame=None
            self.preview_tick()
        else:
            self.preview_timer.stop()
        self.changed.emit()

    @Slot(str)
    def selectStream(self,ident):
        self.live(False)
        self.preview_stream=ident
        self.source=QImage();self.overlay=QImage();self.lab=self.rgb=None;self.serial+=1
        self.source_label='Выберите кадр из принимаемого стрима.'
        self.changed.emit()

    @property
    def video(self):
        player=self.streams.players.get(self.preview_stream)
        return player if player and player.phase=='receiving' else None

    def preview_tick(self):
        fresh=time.monotonic()-getattr(self.video,'last_image_at',0)<=3
        if self.video is None or not fresh or self.video.image.isNull():
            if not self.source.isNull():
                self.source=QImage();self.overlay=QImage();self.lab=self.rgb=None;self.serial+=1
                self.source_label='Нет свежего видео — live-маска скрыта.'
                self.preview_frame=None;self.changed.emit()
            return
        if self.busy or self.preview_frame==self.video.image_serial:return
        self.capture_snapshot()

    @Slot()
    def snapshot(self):
        self.live(False)
        self.capture_snapshot()

    def capture_snapshot(self):
        if self.preview_stream in ('detection','localisation'):
            self.notice='Для пипетки выберите исходное видео camera, а не размеченный диагностический поток.'
            self.changed.emit();return
        required=[f'vision.{self.profile}.{axis}_{suffix}' for axis in ('l','a','b') for suffix in ('min','max')]
        if self.busy or any(k not in self.values for k in required):
            self.notice='Сначала загрузите настройки и выберите цветовой фильтр.';self.changed.emit();return
        if self.video is None or self.video.image.isNull() or time.monotonic()-getattr(self.video,'last_image_at',0)>3:
            self.notice='Нет свежего QImage. Запросите видео в панели «Стримы» и выберите активный приёмник.';self.changed.emit();return
        from .lab_preview import pixels,rgb_lab
        self.source=self.video.image.scaled(640,520,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        self.rgb=pixels(self.source);self.lab=rgb_lab(self.rgb)
        self.preview_frame=self.video.image_serial
        self.source_label=f'Кадр декодированного {self.video.backend}, локальный №{self.video.image_serial}; не UnicamSequence'
        self.recompute();self.changed.emit()

    def recompute(self):
        if self.lab is None:return
        from .lab_preview import overlay
        prefix='vision.'+self.profile+'.';all_values=self.values|self.drafts
        values={key[len(prefix):]:value for key,value in all_values.items() if key.startswith(prefix)}
        if any(k not in values for k in ('l_min','l_max','a_min','a_max','b_min','b_max')):return
        if any(values[k+'_min']>values[k+'_max'] for k in ('l','a','b')):
            self.notice='Нижняя граница не должна превышать верхнюю.';return
        self.overlay,self.selected_pixels=overlay(self.rgb,self.lab,values);self.serial+=1

    @Slot(float,float,int)
    def pick(self,u,v,tolerance):
        if self.lab is None or not (0<=u<1 and 0<=v<1) or not 0<=tolerance<=30:return
        self.live(False)
        import numpy as np
        h,w=self.lab.shape[:2];x,y=int(u*w),int(v*h)
        patch=self.lab[max(0,y-3):min(h,y+4),max(0,x-3):min(w,x+4)].reshape(-1,3)
        for i,axis in enumerate(('l','a','b')):
            for suffix,quantile,sign in [('min',10,-1),('max',90,1)]:
                key=f'vision.{self.profile}.{axis}_{suffix}'
                if key not in self.metas:return
                m=self.metas[key];value=round(float(np.percentile(patch[:,i],quantile)))+sign*tolerance
                self.drafts[key]=max(m['min'],min(m['max'],value))
        self.notice='Пипетка создала черновик по области 7×7; проверьте маску перед сохранением.'
        self.recompute();self.changed.emit()

    def shutdown(self):
        self.timer.stop()
        self.preview_timer.stop()
