# 	"$Name:  $";
# 	"$Header:  $";
#=============================================================================
#
# file :        SPM002_DS.py
#
# description : Python source for the SPM002_DS and its commands. 
#                The class is derived from Device. It represents the
#                CORBA servant object which will be accessed from the
#                network. All commands which can be executed on the
#                SPM002_DS are implemented in this file.
#
# project :     TANGO Device Server
#
# $Author:  $
#
# $Revision:  $
#
# $Log:  $
#
# copyleft :    European Synchrotron Radiation Facility
#               BP 220, Grenoble 38043
#               FRANCE
#
#=============================================================================
#  		This file is generated by POGO
# 	(Program Obviously used to Generate tango Object)
#
#         (c) - Software Engineering Group - ESRF
#=============================================================================
#


import PyTango
import sys
import SPM002_control as spm
import threading
import time
import numpy as np
from socket import gethostname
import Queue

		
class SpectrometerCommand:
	def __init__(self, command, data=None):
		self.command = command
		self.data = data
		
#==================================================================
#   SPM002_DS Class Description:
#
#         Control of a Photon control SPM002 spectrometer
#
#==================================================================
# 	Device States Description:
#
#   DevState.ON :       Connected to spectrometer, acquiring spectra
#   DevState.OFF :      Disconnected from spectrometer
#   DevState.FAULT :    Error detected
#   DevState.UNKNOWN :  Communication problem
#   DevState.STANDBY :  Connected to spectrometer, not acquiring
#   DevState.INIT :     Initializing spectrometer. Could take time.
#==================================================================


class SPM002_DS(PyTango.Device_4Impl):

#--------- Add you global variables here --------------------------

#------------------------------------------------------------------
# 	Device constructor
#------------------------------------------------------------------
	def __init__(self, cl, name):
		PyTango.Device_4Impl.__init__(self, cl, name)
		SPM002_DS.init_device(self)

#------------------------------------------------------------------
# 	Device destructor
#------------------------------------------------------------------
	def delete_device(self):
		print "[Device delete_device method] for device", self.get_name()
		self.stopStateThread()
		self.spectrometer.closeDevice()


#------------------------------------------------------------------
# 	Device initialization
#------------------------------------------------------------------
	def init_device(self):
		print "In ", self.get_name(), "::init_device()"		
		self.set_state(PyTango.DevState.UNKNOWN)
		self.get_device_properties(self.get_device_class())
		
		try:
			self.stopStateThread()
			self.spectrometer.closeDevice()
		except Exception, e:
			pass
		
		self.stateThread = threading.Thread()
		threading.Thread.__init__(self.stateThread, target=self.stateHandlerDispatcher)
		
		self.commandQueue = Queue.Queue(100)
		
		self.stateHandlerDict = {PyTango.DevState.ON: self.onHandler,
								PyTango.DevState.STANDBY: self.standbyHandler,
								PyTango.DevState.ALARM: self.alarmHandler,
								PyTango.DevState.FAULT: self.faultHandler,
								PyTango.DevState.INIT: self.initHandler,
								PyTango.DevState.UNKNOWN: self.unknownHandler,
								PyTango.DevState.OFF: self.offHandler}

		self.stopStateThreadFlag = False
		
		self.stateThread.start()
		
		self.hardwareLock = threading.Lock()
		self.stopHardwareThreadFlag = False
# 		self.hardwareThread = threading.Thread()
# 		threading.Thread.__init__(self.hardwareThread, target=self.readHardware)
		# Hardware reading thread
		
# 		self.initThread = threading.Thread()
# 		threading.Thread.__init__(self.initThread, target=self.initSpectrometer)
		# We do the device listing and initialization in a thread since it can take time

#------------------------------------------------------------------
# 	Always excuted hook method
#------------------------------------------------------------------
	def always_executed_hook(self):
		pass


	def stateHandlerDispatcher(self):
		prevState = self.get_state()
		while self.stopStateThreadFlag == False:
			try:
				state = self.get_state()
				self.stateHandlerDict[state](prevState)
				prevState = state
			except KeyError:
				self.stateHandlerDict[PyTango.DevState.UNKNOWN](prevState)
				prevState = state


	def unknownHandler(self, prevState):
		self.info_stream('Entering unknownHandler')
		connectionTimeout = 1.0
		
		self.spectrumData = None
		self.spectrumCenter = 0.0
		self.spectrumFWHM = 0.0
		self.peakEnergy = 0.0

		self.expTime = 200
		self.updateTime = 500
		self.deviceList = []

		while self.get_state() == PyTango.DevState.UNKNOWN:
			self.info_stream('Trying to connect...')
			try:				
				self.spectrometer = spm.SPM002control()
				self.set_state(PyTango.DevState.INIT)
				self.info_stream('... connected')
				break
			
			except Exception, e:
				self.error_stream(''.join(('Could not create spectrometer object.', str(e))))
				self.set_state(PyTango.DevState.UNKNOWN)
				self.set_status(''.join(('Could not create spectrometer object.', str(e))))
				

			time.sleep(connectionTimeout)


	def initHandler(self, prevState):
		self.info_stream('Entering initHandler')
		self.set_state(PyTango.DevState.INIT)
		s_status = 'Starting initialization\n'
		self.set_status(s_status)
		self.info_stream(s_status)
		initTimeout = 1.0  # Retry time interval
		
		exitInitFlag = False  # Flag to see if we can leave the loop
		
		while exitInitFlag == False:
			exitInitFlag = True  # Preset in case nothing goes wrong
			s = 'Populating device list. Could be time consuming.\n'
			s_status = ''.join((s_status, s))
			self.set_status(s_status)
			self.info_stream(s)			
			while self.Serial not in self.spectrometer.serialList: 
				try:

					self.spectrometer.populateDeviceList()
					self.info_stream(str(self.spectrometer.serialList))
					if self.Serial not in self.spectrometer.serialList:
						self.error_stream(''.join(('Device ', str(self.Serial), ' not in list, retrying')))
						time.sleep(initTimeout)
					else:
						s = 'Found device in device list\n'
						s_status = ''.join((s_status, s))
						self.set_status(s_status)
						self.info_stream(s)
						self.deviceList = self.spectrometer.serialList			
						
				except Exception, e:
					self.error_stream(''.join(('Could not populate device list, retrying', str(e))))
				
			try:
				s = ''.join(('Setting device ', str(self.Serial), '\n'))
				s_status = ''.join((s_status, s))
				self.set_status(s_status)
				self.info_stream(s)			
				self.openSpectrometer()
			except Exception, e:
				self.error_stream('Could not open spectrometer')
				exitInitFlag = False
				continue
			try:
				s = 'Retrieving wavelength table\n'
				s_status = ''.join((s_status, s))
				self.set_status(s_status)
				self.info_stream(s)
				self.spectrometer.constructWavelengths()
				self.wavelengths = self.spectrometer.wavelengths
			except Exception, e:
				self.error_stream('Could not construct wavelengths')
				exitInitFlag = False
				continue
			s = 'Setting exposure time\n'
			s_status = ''.join((s_status, s))
			self.set_status(s_status)
			self.info_stream(s)
			try:
				attrs = self.get_device_attr()
				self.expTime = attrs.get_w_attr_by_name('ExposureTime').get_write_value()
				s = ''.join(('Exposure time ', self.expTime, ' ms'))
				self.info_stream(s)
			except Exception, e:
				self.error_stream('Could not retrieve attribute ExposureTime, using default value')
			try:
				self.spectrometer.setExposureTime(int(self.expTime * 1e3))
			except Exception, e:
				exitInitFlag = False
				self.set_status(''.join(('Could not set exposure time', str(e))))
				self.error_stream(''.join(('Could not set exposure time', str(e))))
				continue
	
			try:
				self.updateTime = attrs.get_w_attr_by_name('UpdateTime').get_write_value()
				s = ''.join(('Update time ', self.updateTime, ' ms'))
				self.info_stream(s)
			except Exception, e:
				self.error_stream('Could not retrieve attribute UpdateTime, using default value')

			self.set_status('Connected to spectrometer, not acquiring')
			self.info_stream('Initialization finished.')
			self.set_state(PyTango.DevState.STANDBY)
			time.sleep(5)  # Wait to let other spectrometers populate their device lists


	def standbyHandler(self, prevState):
		self.info_stream('Entering standbyHandler')
		self.set_status('Connected to spectrometer, not acquiring spectra')
		self.openSpectrometer()
		while self.stopStateThreadFlag == False:
			if self.get_state() != PyTango.DevState.STANDBY:
				break
			# Check if any new commands arrived:
			self.checkCommands()
			if self.get_state() != PyTango.DevState.STANDBY:
				break

			try:
				self.expTime = self.spectrometer.getExposureTime() * 1e-3
			except Exception, e:
				self.error_stream('Error reading device')
				self.set_state(PyTango.DevState.FAULT)
			time.sleep(0.5)


	def onHandler(self, prevState):
		self.info_stream('Entering onHandler')
		self.set_status('Connected to spectrometer, acquiring spectra')
		self.openSpectrometer()
		if self.updateTime > self.expTime:
			self.sleepTime = (self.updateTime - self.expTime) * 1e-3
		else:
			self.sleepTime = self.expTime * 1e-3
		s = ''.join(('Sleeptime: ', str(self.sleepTime)))
		self.info_stream(s)
		newSpectrumTimestamp = time.time()
		oldSpectrumTimestamp = time.time()
		self.spectrumData = self.spectrometer.CCD
		nextUpdateTime = time.time()
		while self.stopStateThreadFlag == False:
			if self.get_state() != PyTango.DevState.ON:
				break

			# Check if any new commands arrived:
			self.checkCommands()
			
			# Check if we should break this loop and go to a new state handler:
			if self.get_state() != PyTango.DevState.ON:
				break

			try:
				t = time.time()
				if t > nextUpdateTime:
					self.hardwareLock.acquire()
					self.spectrometer.acquireSpectrum()
					newSpectrum = self.spectrometer.CCD				
					self.hardwareLock.release()
					newSpectrumTimestamp = time.time()
					d = np.abs(newSpectrum - self.spectrumData).sum()
					if d == 0:					
						if newSpectrumTimestamp - oldSpectrumTimestamp > 5: 					
							self.set_state(PyTango.DevState.FAULT)
							self.set_status('Spectrum not updating. Reconnecting.')
							self.error_stream('Spectrum not updating. Reconnecting.')
					else:
						oldSpectrumTimestamp = newSpectrumTimestamp
					self.spectrumData = np.copy(newSpectrum)
					self.calculateSpectrumParameters()
					nextUpdateTime = t + self.sleepTime
				time.sleep(0.01)

			except Exception, e:
				self.set_state(PyTango.DevState.FAULT)
				self.set_status('Error reading hardware.')
				PyTango.Except.throw_exception('Error reading hardware', str(e), 'readHardware thread')


	def alarmHandler(self, prevState):
		pass


	def faultHandler(self, prevState):
		responseAttempts = 0
		maxAttempts = 5
		responseTimeout = 0.5
		self.info_stream('Entering faultHandler.')
		self.set_status('Fault condition detected')
			
		while self.get_state() == PyTango.DevState.FAULT:
			try:
				self.spectrometer.closeDevice()
				self.openSpectrometer()
				
				self.set_state(prevState)
				self.info_stream('Fault condition cleared.')
				break
			except Exception, e:
				self.error_stream(''.join(('In faultHandler: Testing controller response. Returned ', str(e))))
				responseAttempts += 1
			if responseAttempts >= maxAttempts:
				self.set_state(PyTango.DevState.UNKNOWN)
				self.set_status('Could not connect to controller')
				self.error_stream('Giving up fault handling. Going to UNKNOWN state.')
				break
			time.sleep(responseTimeout)


	def offHandler(self, prevState):
		self.info_stream('Entering offHandler')
		try:
			self.spectrometer.closeDevice()
		except Exception, e:
			self.error_stream(''.join(('Could not disconnect from spectrometer, ', str(e))))
				
		self.set_status('Disconnected from spectrometer')
		while self.stopStateThreadFlag == False:
			if self.get_state() != PyTango.DevState.OFF:
				break
			# Check if any new commands arrived:
			self.checkCommands()
			if self.get_state() != PyTango.DevState.OFF:
				break

			time.sleep(0.5)


	def checkCommands(self):
		try:
			cmd = self.commandQueue.get(block=False)
			self.info_stream(str(cmd.command))
			if cmd.command == 'writeExposureTime':
				try:
					self.hardwareLock.acquire()
					self.spectrometer.setExposureTime(int(cmd.data * 1e3))  # expTime is in ms, the spectrometer excpects us
					self.expTime = cmd.data
					self.info_stream(''.join(('New exposure time: ', str(self.expTime))))
				except Exception, e:
					self.set_state(PyTango.DevState.FAULT)
					self.set_status(''.join(('Could not set exposure time', str(e))))
					self.error_stream(''.join(('Could not set exposure time', str(e))))
				finally:
					self.hardwareLock.release()
				if self.updateTime > self.expTime:
					self.sleepTime = (self.updateTime - self.expTime) * 1e-3
				else:
					self.sleepTime = self.expTime * 1e-3
					
			elif cmd.command == 'writeUpdateTime':
				self.updateTime = cmd.data
				if self.updateTime > self.expTime:
					self.sleepTime = (self.updateTime - self.expTime) * 1e-3
				else:
					self.sleepTime = self.expTime * 1e-3


			elif cmd.command == 'on':
				
				self.set_state(PyTango.DevState.ON)
# 				self.startHardwareThread()

			elif cmd.command == 'stop':
				self.set_state(PyTango.DevState.STANDBY)
				
			elif cmd.command == 'off':
				self.set_state(PyTango.DevState.OFF)			

		except Queue.Empty:
			pass

	def setExposure(self):
		pass
		

	def openSpectrometer(self):
		# If the device was closed, we open it again
		if self.spectrometer.deviceHandle == None:
			try:
				self.spectrometer.openDeviceSerial(self.Serial)
			except Exception, e:
				self.error_stream(''.join(('Could not open device ', str(self.Serial), str(e))))
				self.set_state(PyTango.DevState.INIT)
				self.set_status(''.join(('Could not open device ', str(self.Serial))))


	def stopStateThread(self):
		self.info_stream('Stopping thread...')
		self.stopStateThreadFlag = True
		if self.stateThread.isAlive() == True:
			self.info_stream('It was alive.')
			self.stateThread.join(3)
		self.info_stream('Now stopped.')
		self.stopStateThreadFlag = False
		self.set_state(PyTango.DevState.UNKNOWN)


	def calculateSpectrumParameters(self):
		if self.spectrumData != None:
			sp = self.spectrumData
			# Start by median filtering to remove spikes
			m = np.median(np.vstack((sp[6:], sp[5:-1], sp[4:-2], sp[3:-3], sp[2:-4], sp[1:-5], sp[0:-6])), axis=0)
			noiseFloor = np.mean(m[0:10])
			peakInd = m.argmax()
			halfMax = (m[peakInd] + noiseFloor) / 2
			# Detect zero crossings to this half max to determine the FWHM
			halfInd = np.where(np.diff(np.sign(m - halfMax)))[0]
			halfIndReduced = halfInd[np.abs(halfInd - peakInd).argsort()[0:2]]
			# Check where the signal is below 1.2*noiseFloor
 			noiseInd = np.where(sp < 1.2 * noiseFloor)[0]
 			peakDist = abs(noiseInd - peakInd)
 			peakEdge = peakDist.argmin()
 			peakData = sp[noiseInd[peakEdge - 1]:noiseInd[peakEdge + 1]]
 			peakWavelengths = self.wavelengths[noiseInd[peakEdge - 1]:noiseInd[peakEdge + 1]]

 			self.peakEnergy = np.trapz(peakData, peakWavelengths)
			self.spectrumFWHM = np.abs(np.diff(self.wavelengths[halfIndReduced]))
			self.spectrumCenter = self.wavelengths[peakInd]


#------------------------------------------------------------------
# 	Read AcquisitionRate attribute
#------------------------------------------------------------------
	def read_AcquisitionRate(self, attr):
		print "In ", self.get_name(), "::read_AcquisitionRate()"
		
		# 	Add your own code here
		
		attr_AcquisitionRate_read = self.acqTime
		attr.set_value(attr_AcquisitionRate_read)


#------------------------------------------------------------------
# 	Write AcquisitionRate attribute
#------------------------------------------------------------------
	def write_AcquisitionRate(self, attr):
		print "In ", self.get_name(), "::write_AcquisitionRate()"

		data = attr.get_write_value()
		print "Attribute value = ", data

		# 	Add your own code here
		self.acqTime = data


#---- AcquisitionRate attribute State Machine -----------------
	def is_AcquisitionRate_allowed(self, req_type):
		if self.get_state() in [PyTango.DevState.OFF,
		                        PyTango.DevState.UNKNOWN]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True


#------------------------------------------------------------------
# 	Read Attribute Hardware
#------------------------------------------------------------------
	def read_attr_hardware(self, data):
		pass

#==================================================================
#
# 	SPM002_DS read/write attribute methods
#
#==================================================================


#------------------------------------------------------------------
# 	Read ExposureTime attribute
#------------------------------------------------------------------
	def read_ExposureTime(self, attr):
		
		# 	Add your own code here
		
		attr_ExposureTime_read = self.expTime
		attr.set_value(attr_ExposureTime_read)


#------------------------------------------------------------------
# 	Write ExposureTime attribute
#------------------------------------------------------------------
	def write_ExposureTime(self, attr):
		print "In ", self.get_name(), "::write_ExposureTime()"
		data = attr.get_write_value()
		print "Attribute value = ", data

		# 	Add your own code here
		self.commandQueue.put(SpectrometerCommand('writeExposureTime', data))


#------------------------------------------------------------------
# 	Read UpdateTime attribute
#------------------------------------------------------------------
	def read_UpdateTime(self, attr):
		
		# 	Add your own code here
		
		attr_UpdateTime_read = self.updateTime
		attr.set_value(attr_UpdateTime_read)


#------------------------------------------------------------------
# 	Write UpdateTime attribute
#------------------------------------------------------------------
	def write_UpdateTime(self, attr):
		print "In ", self.get_name(), "::write_UpdateTime()"
		data = attr.get_write_value()
		print "Attribute value = ", data

		# 	Add your own code here
		self.updateTime = data
		# If running, restart capture thread with new update time
		if self.get_state() == PyTango.DevState.ON:
			self.stopHardwareThread()
			self.startHardwareThread()


#---- UpdateTime attribute State Machine -----------------
	def is_UpdateTime_allowed(self, req_type):
		if self.get_state() in [PyTango.DevState.OFF,
		                        PyTango.DevState.UNKNOWN]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True


#------------------------------------------------------------------
# 	Read PeakWavelength attribute
#------------------------------------------------------------------
	def read_PeakWavelength(self, attr):
		
		# 	Add your own code here
		
		attr_PeakWavelength_read = self.spectrumCenter
		attr.set_value(attr_PeakWavelength_read)


#---- PeakWavelength attribute State Machine -----------------
	def is_PeakWavelength_allowed(self, req_type):
		if self.get_state() in [PyTango.DevState.OFF,
		                        PyTango.DevState.FAULT,
		                        PyTango.DevState.UNKNOWN,
		                        PyTango.DevState.STANDBY,
		                        PyTango.DevState.INIT]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True


#------------------------------------------------------------------
# 	Read SpectrumWidth attribute
#------------------------------------------------------------------
	def read_SpectrumWidth(self, attr):
		
		# 	Add your own code here
		
		attr_SpectrumWidth_read = self.spectrumFWHM
		attr.set_value(attr_SpectrumWidth_read)


#---- SpectrumWidth attribute State Machine -----------------
	def is_SpectrumWidth_allowed(self, req_type):
		if self.get_state() in [PyTango.DevState.OFF,
		                        PyTango.DevState.FAULT,
		                        PyTango.DevState.UNKNOWN,
		                        PyTango.DevState.STANDBY,
		                        PyTango.DevState.INIT]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True


#------------------------------------------------------------------
# 	Read PeakEnergy attribute
#------------------------------------------------------------------
	def read_PeakEnergy(self, attr):
		print "In ", self.get_name(), "::read_PeakEnergy()"
		
		# 	Add your own code here
		
		attr_PeakEnergy_read = self.peakEnergy
		attr.set_value(attr_PeakEnergy_read)


#---- PeakEnergy attribute State Machine -----------------
	def is_PeakEnergy_allowed(self, req_type):
		if self.get_state() in [PyTango.DevState.OFF,
		                        PyTango.DevState.FAULT,
		                        PyTango.DevState.UNKNOWN,
		                        PyTango.DevState.STANDBY,
		                        PyTango.DevState.INIT]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True


#------------------------------------------------------------------
# 	Read Wavelengths attribute
#------------------------------------------------------------------
	def read_Wavelengths(self, attr):
		# 	Add your own code here
		
		attr_Wavelengths_read = self.wavelengths
		attr.set_value(attr_Wavelengths_read, self.wavelengths.shape[0])


#---- Wavelengths attribute State Machine -----------------
	def is_Wavelengths_allowed(self, req_type):
		if self.get_state() in [PyTango.DevState.OFF,
		                        PyTango.DevState.UNKNOWN]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True


#------------------------------------------------------------------
# 	Read Spectrum attribute
#------------------------------------------------------------------
	def read_Spectrum(self, attr):
		
		# 	Add your own code here
		self.hardwareLock.acquire()
		attr_Spectrum_read = self.spectrometer.CCD
		self.hardwareLock.release()
		attr.set_value(attr_Spectrum_read, attr_Spectrum_read.shape[0])


#---- Spectrum attribute State Machine -----------------
	def is_Spectrum_allowed(self, req_type):
		if self.get_state() in [PyTango.DevState.OFF,
		                        PyTango.DevState.UNKNOWN]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True


#------------------------------------------------------------------
# 	Read DeviceList attribute
#------------------------------------------------------------------
	def read_DeviceList(self, attr):
		
		# 	Add your own code here
		
		attr_DeviceList_read = self.spectrometer.serialList
		attr.set_value(attr_DeviceList_read, attr_DeviceList_read.__len__())


#---- DeviceList attribute State Machine -----------------
	def is_DeviceList_allowed(self, req_type):
		if self.get_state() in [PyTango.DevState.OFF,
		                        PyTango.DevState.UNKNOWN]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True



#==================================================================
#
# 	SPM002_DS command methods
#
#==================================================================

#------------------------------------------------------------------
# 	On command:
#
# 	Description: Connect and start aquiring
#                
#------------------------------------------------------------------
	def On(self):
		print "In ", self.get_name(), "::On()"
		# 	Add your own code here
		self.commandQueue.put(SpectrometerCommand('on'))


#---- On command State Machine -----------------
	def is_On_allowed(self):
		if self.get_state() in [PyTango.DevState.UNKNOWN]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True


#------------------------------------------------------------------
# 	Stop command:
#
# 	Description: Stop acquiring
#                
#------------------------------------------------------------------
	def Stop(self):
		print "In ", self.get_name(), "::Stop()"
		# 	Add your own code here
		self.commandQueue.put(SpectrometerCommand('stop'))


#---- Stop command State Machine -----------------
	def is_Stop_allowed(self):
		if self.get_state() in [PyTango.DevState.OFF,
		                        PyTango.DevState.UNKNOWN]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True


#------------------------------------------------------------------
# 	Off command:
#
# 	Description: Disconnect from spectrometer
#                
#------------------------------------------------------------------
	def Off(self):
		print "In ", self.get_name(), "::Off()"
		self.commandQueue.put(SpectrometerCommand('off'))
		# 	Add your own code here


#---- Off command State Machine -----------------
	def is_Off_allowed(self):
		if self.get_state() in [PyTango.DevState.UNKNOWN]:
			# 	End of Generated Code
			# 	Re-Start of Generated Code
			return False
		return True


#==================================================================
#
# 	SPM002_DSClass class definition
#
#==================================================================
class SPM002_DSClass(PyTango.DeviceClass):

	# 	Class Properties
	class_property_list = {
		}


	# 	Device Properties
	device_property_list = {
		'Serial':
			[PyTango.DevLong,
			"Serial number of the spectrometer",
			[ 70058308 ] ],
		}


	# 	Command definitions
	cmd_list = {
		'On':
			[[PyTango.DevVoid, ""],
			[PyTango.DevVoid, ""]],
		'Stop':
			[[PyTango.DevVoid, ""],
			[PyTango.DevVoid, ""]],
		'Off':
			[[PyTango.DevVoid, ""],
			[PyTango.DevVoid, ""]],
		}


	# 	Attribute definitions
	attr_list = {
		'ExposureTime':
			[[PyTango.DevDouble,
			PyTango.SCALAR,
			PyTango.READ_WRITE],
			{
				'description':"Exposure time in ms",
				'Memorized':"true_without_hard_applied",
			} ],
		'UpdateTime':
			[[PyTango.DevDouble,
			PyTango.SCALAR,
			PyTango.READ_WRITE],
			{
				'description':"Time in ms between acquisitions",
				'Memorized':"true_without_hard_applied",
			} ],
		'PeakWavelength':
			[[PyTango.DevDouble,
			PyTango.SCALAR,
			PyTango.READ],
			{
				'unit':"nm",
			} ],
		'SpectrumWidth':
			[[PyTango.DevDouble,
			PyTango.SCALAR,
			PyTango.READ],
			{
				'unit':"nm",
				'description':"FWHM width of the spectrum at the peak.",
			} ],
		'PeakEnergy':
			[[PyTango.DevFloat,
			PyTango.SCALAR,
			PyTango.READ],
			{
				'description':"Energy inside the main peak",
			} ],
		'Wavelengths':
			[[PyTango.DevDouble,
			PyTango.SPECTRUM,
			PyTango.READ, 3648]],
		'Spectrum':
			[[PyTango.DevDouble,
			PyTango.SPECTRUM,
			PyTango.READ, 3648],
			{
				'description':"Latest spectrum acquired",
			} ],
		'DeviceList':
			[[PyTango.DevLong,
			PyTango.SPECTRUM,
			PyTango.READ, 16]],
		}


#------------------------------------------------------------------
# 	SPM002_DSClass Constructor
#------------------------------------------------------------------
	def __init__(self, name):
		PyTango.DeviceClass.__init__(self, name)
		self.set_type(name);
		print "In SPM002_DSClass  constructor"

#==================================================================
#
# 	SPM002_DS class main method
#
#==================================================================
if __name__ == '__main__':
	try:
		py = PyTango.Util(sys.argv)
		py.add_TgClass(SPM002_DSClass, SPM002_DS, 'SPM002_DS')

		U = PyTango.Util.instance()
		U.server_init()
		U.server_run()

	except PyTango.DevFailed, e:
		print '-------> Received a DevFailed exception:', e
	except Exception, e:
		print '-------> An unforeseen exception occured....', e
