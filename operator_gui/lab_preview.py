"""CIELAB/D65 preview of a decoded RGB image, not raw robot detection."""
import numpy as np
from PySide6.QtGui import QImage


def rgb_lab(rgb):
    rgb=np.asarray(rgb,dtype=np.float32)/255.
    linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    xyz=linear @ np.array([[.4124564,.3575761,.1804375],
        [.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]],np.float32).T
    xyz/=np.array([.95047,1.,1.08883],np.float32)
    f=np.where(xyz>(6/29)**3,np.cbrt(xyz),xyz/(3*(6/29)**2)+4/29)
    return np.stack((116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])),axis=-1)


def pixels(image):
    image=image.convertToFormat(QImage.Format.Format_RGB888)
    return np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3).copy()


def overlay(rgb,lab,values):
    low=[values[k+'_min'] for k in ('l','a','b')];high=[values[k+'_max'] for k in ('l','a','b')]
    mask=np.all((lab>=low)&(lab<=high),axis=-1)
    result=(rgb.astype(np.float32)*.35).astype(np.uint8)
    result[mask]=(rgb[mask]*.4+np.array([255,40,190])*.6).astype(np.uint8)
    h,w=mask.shape
    return QImage(result.data,w,h,w*3,QImage.Format.Format_RGB888).copy(),int(mask.sum())
