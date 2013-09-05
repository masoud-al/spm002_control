# -*- coding:utf-8 -*-
"""
Created on Jun 11, 2012

@author: Laser
"""
from ctypes import *
from struct import *
import numpy as np
import time
import atexit

spmlib = cdll.LoadLibrary("PhotonSpectr.dll")

class SpectrometerError(Exception):
    pass

class SPM002control():
    def __init__(self):
        self.deviceList = []
        self.serialList = []
        self.deviceHandle = None
        self.deviceIndex = None
        self.CCD = np.zeros(3648)
        self.CCD = self.CCD.astype(np.uint16)
        self.CCD_ct = self.CCD.ctypes.data_as(POINTER(c_uint16))

        self.LUT = None
        self.wavelengths = np.zeros(3648)
        
    def populateDeviceList(self):
        indexTmp = None
        if self.deviceHandle != None:
            indexTmp = self.deviceIndex
            self.closeDevice()
        self.deviceList = []
        numDevices = spmlib.PHO_EnumerateDevices()
        for k in range(numDevices):
            index = c_int(k)
            handle = spmlib.PHO_Open(index)
            serial = spmlib.PHO_Getsn(handle)
            self.deviceList.append(handle)
            self.serialList.append(serial)
            spmlib.PHO_Close(handle)
        if indexTmp != None:
            self.openDevice(indexTmp)
            
    def openDevice(self, index):
        if self.deviceHandle != None:
            self.closeDevice()
        self.deviceHandle = spmlib.PHO_Open(c_int(index))
        self.deviceIndex = index
            
    def closeDevice(self):
        if self.deviceHandle != None:
            result = spmlib.PHO_Close(c_int(self.deviceIndex))
            if result != 0:
                raise SpectrometerError(''.join(('Could not close device, returned ', str(result))))
            self.deviceIndex = None
            
if __name__ == '__main__':
    spm = SPM002control()    
#    spm.populateDeviceList()
#    spm.openDevice(1)  
