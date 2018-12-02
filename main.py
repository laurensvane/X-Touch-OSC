#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Copyright © 2018, Laurens van Eekelen

XT-Touch OSC is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

XT-Touch OSC is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

This is a bridge between The Behringer X-touch Controller and OSC commands
'''

import struct, argparse, sys, socket, time
import json
from PyQt5 import QtCore, QtWidgets, QtGui
from pythonosc import dispatcher, osc_server, osc_message_builder, udp_client
import pygame.midi

class MidiCommunication(QtCore.QThread):




	def __init__(self,data,cfg):
		super(MidiCommunication, self).__init__()
		self.data = data
		self.cfg = cfg
		self.displayTopState = []
		self.displayBottomState = []
		self.displayColorState = []


		for display in self.cfg['displays']:
			self.displayTopState.append("")
			self.displayBottomState.append("")
			self.displayColorState.append(6)

		self.midiInputHandler = pygame.midi.Input(self.getMidiDeviceByName(2, self.cfg['connection']))
		self.midiOutputHandler = pygame.midi.Output(self.getMidiDeviceByName(3, self.cfg['connection']))
		#self.data.mainWindow.statusBar().showMessage("Midi Connected")

	def getMidiDeviceByName(self, type, name):
		result = -1
		for x in range(0, pygame.midi.get_count()):
			print(pygame.midi.get_device_info(x))
			if(pygame.midi.get_device_info(x)[type]):
				if(name in str(pygame.midi.get_device_info(x)[1])):
					result = x
		return result

	def run(self):
		self.running = True
		while self.running:
			try:
				self.receiveMidi()

			except pygame.midi.MidiException as e:
				logging.info("Midi Error: ", e)

			time.sleep(0.0001)

	def stop(self):
		self.running = False
		#self.midiInputHandler.quit()
		#self.midiOutputHandler.quit()

	def receiveMidi(self):
		if self.midiInputHandler.poll():
			result = self.midiInputHandler.read(1024)
			for r in result:
				self.translateMidi(r) 

	def translateMidi(self,data):
		channel = data[0][1]
		value = data[0][2]*(1.0/127)

		for fader in self.cfg['faders']:
			if fader['midi'] == channel:
				self.data.oscHandler.send_osc(fader['osc'], value)

		for fader in self.cfg['faders_touch']:
			if fader['midi'] == channel:
				self.data.oscHandler.send_osc(fader['osc'], value)	

		for encoder in self.cfg['encoders']:
			if encoder['midi'] == channel:
				if data[0][2]==65:
					value = 1.0
				else:
					value = 0.0
				self.data.oscHandler.send_osc(encoder['osc'], value)

		for encoder in self.cfg['encoders_press']:
			if encoder['midi'] == channel:
				self.data.oscHandler.send_osc(encoder['osc'], value)
		
		for button in self.cfg['buttons']:
			if button['midi'] == channel:
				self.data.oscHandler.send_osc(button['osc'], value)

	def setDisplayTop(self, channel, value):
		self.displayTopState[channel-1] = value
		self.sendDisplay(channel)

	def setDisplayBottom(self, channel, value):
		self.displayBottomState[channel-1] = value
		self.sendDisplay(channel)

	def setDisplayColor(self, channel, value):
		self.displayColorState[channel-1] = value
		self.sendDisplay(channel)

	def sendDisplay(self, channel):
		row1 = self.displayTopState[channel-1][:7]
		row2 = self.displayBottomState[channel-1][:7]
		color = self.displayColorState[channel-1]
		for i in range(len(row1),7):
			row1 = row1+'\x00'
		for i in range(len(row2),7):
			row2 = row2+'\x00'

		#print(row1)
		#print(row2)

		sysex_start = b'\xF0\x00\x20\x32\x15\x4C'
		sysex_channel = bytes(str(channel-1),'utf-8')
		sysex_color = bytes([color]) #b'\x16'
		sysex_data1 = bytes(row1,'utf-8') #\x68\x65\x6c\x6c\x6f\x00\x00' #self.data.getChannelLabel(channel, 0) #'68 65 6c 6c 6f 00 00' 
		sysex_data2 = bytes(row2,'utf-8') #self.data.getChannelLabel(channel, 1) #'77 6f 72 6c 64 00 00' 
		sysex_end = b'\xF7' 
		sysex_message = sysex_start + sysex_channel + sysex_color + sysex_data1 + sysex_data2 + sysex_end
		#sysex_message = b'\xF0\x00\x20\x32\x15\x4C\x03\x16\x68\x65\x6C\x6C\x6F\x00\x00\x77\x6F\x72\x6C\x64\x00\x00\xF7'
		#sysex_message = '\xF0\x7D\x10\x11\x12\x13\xF7'
		#print(sysex_message)
		self.sendMidiSysEx(sysex_message)

	def sendMidiNote(self, note, value):
		self.midiOutputHandler.note_on(note, value, 0)

	def sendMidiCC(self, note, value):
		self.midiOutputHandler.write_short(176, note, value)

	def sendMidiSysEx(self, message):
		self.midiOutputHandler.write_sys_ex(0, message)

class OscHandler(QtCore.QThread):
	def __init__(self,data):
		super(OscHandler, self).__init__()
		self.data = data
		self.dispatcher = dispatcher.Dispatcher()
		self.dispatcher.map("/*", self.receive_osc)
		self.client = udp_client.SimpleUDPClient(data.cfg['general']['server-ip'],int(data.cfg['general']['server-port']))
		self.server = osc_server.ThreadingOSCUDPServer((self.getip(), int(data.cfg['general']['listen-port'])), self.dispatcher)

	def run(self):
		#print("Start OSC server")
		self.server.serve_forever()

	def stop(self):
		self.running = False
		#print("Stopping OSC server")
		self.server.shutdown()
		self.server = None

	def send_osc(self, args, value):
		print(args+" = "+str(value))
		self.client.send_message(args, value)

	def receive_osc(self, args, value):

		for panel in self.data.cfg['panels']:
			for fader in panel['faders']:
				if fader['osc'] == args:
					self.data.midiHandlers[self.data.cfg['panels'].index(panel)].sendMidiCC(fader['midi'], int(value*127))

			for encoder in panel['encoders']:
				if encoder['osc'] == args:
					self.data.midiHandlers[self.data.cfg['panels'].index(panel)].sendMidiCC(encoder['midi'], int(value*127))

			for button in panel['buttons']:
				if button['osc'] == args:
					if value == "off":
						value = 0
					if value == "on":
						value = 127
					if value == "blink":
						value = 64

					self.data.midiHandlers[self.data.cfg['panels'].index(panel)].sendMidiCC(button['midi'], int(value*127))
					self.data.midiHandlers[self.data.cfg['panels'].index(panel)].sendMidiNote(button['midi'], int(value*127))

			for meter in panel['meters']:
				if meter['osc'] == args:
					#print("meter" + str(value))
					self.data.midiHandlers[self.data.cfg['panels'].index(panel)].sendMidiCC(meter['midi'], self.translate_meterValue(value))
			
			for display in panel['displays']:
				if display['osc']+"/top" == args:
						self.data.midiHandlers[self.data.cfg['panels'].index(panel)].setDisplayTop(display['channel'], str(value))
				if display['osc']+"/bottom" == args:
						self.data.midiHandlers[self.data.cfg['panels'].index(panel)].setDisplayBottom(display['channel'], str(value))
				if display['osc']+"/color" == args:
						self.data.midiHandlers[self.data.cfg['panels'].index(panel)].setDisplayColor(display['channel'], int(value))
					
	def getip(self):
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			# doesn't even have to be reachable
			s.connect(('10.255.255.255', 1))
			IP = s.getsockname()[0]
		except:
			IP = '127.0.0.1'
		finally:
			s.close()
		return IP

	def translate_meterValue(self, value):
		result = 0
		if(value > 0.005):
			result = 20
		if(value > 0.015):
			result = 30
		if(value > 0.03):
			result = 50
		if(value > 0.06):
			result = 60
		if(value > 0.12):
			result = 75
		if(value > 0.20):
			result = 90
		if(value > 0.30):
			result = 110
		if(value > 0.60):
			result = 127
		return result

class DataHandler():
	def __init__(self,cfg):
		self.cfg = cfg
		self.reset()

	cfg = None

	midiHandlers = []
	oscHandler = None


	def reset(self):
		pygame.init()
		pygame.midi.init()
		for i in range(0, len(self.cfg['panels'])):
			#print("panel" + str(i))
			new_midiHandler = MidiCommunication(self, self.cfg['panels'][i])
			new_midiHandler.start()
			self.midiHandlers.append(new_midiHandler)

		self.oscHandler = OscHandler(self)
		self.oscHandler.start()
		self.oscHandler.send_osc("/startup", 1.0)

	def exit(self):
		#print("stoppen programma")

		for midiHandler in self.midiHandlers:
			midiHandler.stop()
		pygame.midi.quit()
		pygame.quit()

class StatusWindow(QtWidgets.QMainWindow):
	def __init__(self, data):
		super(StatusWindow, self).__init__()
		self.data = data
		self.initUI()

	def initUI(self):

		central = QtWidgets.QWidget()
		centralLayout = QtWidgets.QVBoxLayout()	
		statusLayout = QtWidgets.QGridLayout()

		self.panelStatus = []

		for panel in self.data.cfg['panels']:
			statusLayout.addWidget(QtWidgets.QLabel("Midi Communication 1: "), 0, 0)
			panelStatus = QtWidgets.QLabel("<font color='red'>unkown</font>")
			self.panelStatus.append(panelStatus)
			statusLayout.addWidget(panelStatus, 0, 1)


		statusLayout.addWidget(QtWidgets.QLabel("OSC Server :"), 2, 0)
		self.oscServerStatus = QtWidgets.QLabel("<font color='red'>unkown</font>")
		statusLayout.addWidget(self.oscServerStatus, 2, 1)

		statusLayout.addWidget(QtWidgets.QLabel("OSC Client :"), 3, 0)
		self.oscClientStatus = QtWidgets.QLabel("<font color='red'>unkown</font>")
		statusLayout.addWidget(self.oscClientStatus, 3, 1)

		centralLayout.addLayout(statusLayout)

		central.setLayout(centralLayout)

		self.setCentralWidget(central)

		## Menu dingen

		editConfig = QtWidgets.QAction('&Edit Configuration', self)
		editConfig.setStatusTip('Edit Configuration')

		saveConfig = QtWidgets.QAction('&Save Configuration', self)
		saveConfig.triggered.connect(lambda: self.cfg.save_dialog(self))

		loadConfig = QtWidgets.QAction('&Load Configuration', self)
		loadConfig.triggered.connect(lambda: self.cfg.load_dialog(self))

		#menubar = self.menuBar()

		#configMenu = menubar.addMenu('&Configuration')
		#configMenu.addAction(editConfig)
		#configMenu.addAction(saveConfig)
		#configMenu.addAction(loadConfig)


		self.setWindowTitle('X-TOUCH-OSC Status')

		timer = QtCore.QTimer(self)
		timer.setSingleShot(False)
		timer.timeout.connect(self.updateLabel)
		timer.start(5000)

	def updateLabel(self):
		#print("timer")
		for midiHandler in self.data.midiHandlers:
			if(midiHandler == None):
				self.panelStatus[self.data.midiHandlers.index(midiHandler)].setText("<font color='grey'>Disabled</font>")
			else:
				self.panelStatus[self.data.midiHandlers.index(midiHandler)].setText("<font color='green'>Active</font>")
		
		if(self.data.oscHandler.server == None):
			self.oscServerStatus.setText("<font color='grey'>Disabled</font>")
		else:
			self.oscServerStatus.setText("<font color='green'>Active</font>")
		if(self.data.oscHandler.client == None):
			self.oscClientStatus.setText("<font color='grey'>Disabled</font>")
		else:
			self.oscClientStatus.setText("<font color='green'>Active</font>")

def main(): 
	a = QtWidgets.QApplication(sys.argv)
	a.setApplicationName("XTE OSC")
	a.setApplicationDisplayName("XTE OSC")

	with open('config.json', 'r') as fp:
		cfg = json.load(fp)
		data = DataHandler(cfg)

		statusWindow = StatusWindow(data)
		statusWindow.show()

	a.lastWindowClosed.connect(data.exit) # make upper right cross work
	sys.exit(a.exec_())
	
if __name__ == '__main__':
	main() 