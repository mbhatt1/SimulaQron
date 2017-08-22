#
# Copyright (c) 2017, Stephanie Wehner
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. All advertising materials mentioning features or use of this software
#    must display the following acknowledgement:
#    This product includes software developed by Stephanie Wehner, QuTech.
# 4. Neither the name of the QuTech organization nor the
#    names of its contributors may be used to endorse or promote products
#    derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER ''AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import socket, struct, os, sys, logging

from SimulaQron.general.hostConfig import *
from SimulaQron.cqc.backend.cqcHeader import *

class CQCConnection:
	_appIDs=[]
	def __init__(self,name,cqcFile=None,appID=0):
		"""
		Initialize a connection to the cqc server with the name given as input.
		A path to a configure file for the cqc network can be given,
		if it's not given the config file '$NETSIM/config/cqcNodes.cfg' will be used.
		"""

		# Host name
		self.name=name

		# Which appID
		if appID in self._appIDs:
			raise ValueError("appID={} is already in use".format(appID))
		self._appID=appID
		self._appIDs.append(self._appID)

		# Buffer received data
		self.buf=None

		# This file defines the network of CQC servers interfacing to virtual quantum nodes
		if cqcFile==None:
			self.cqcFile = os.environ.get('NETSIM') + "/config/cqcNodes.cfg"

		# Read configuration files for the cqc network
		cqcNet = networkConfig(self.cqcFile)

		# Host data
		if self.name in cqcNet.hostDict:
			myHost = cqcNet.hostDict[self.name]
		else:
			logging.error("The name '%s' is not in the cqc network.",name)

		#Get IP of correct form
		myIP=socket.inet_ntoa(struct.pack("!L",myHost.ip))

		#Connect to cqc server and run protocol
		self._s=None
		try:
			self._s=socket.socket(socket.AF_INET,socket.SOCK_STREAM,0)
		except socket.error:
			logging.error("Could not connect to cqc server: %s",name)
		try:
			self._s.connect((myIP,myHost.port))
		except socket.error:
			self._s.close()
			logging.error("Could not connect to cqc server: %s",name)

	def __str__(self):
		return "Socket to cqc server '{}'".format(self.name)

	def get_appID(self):
		return self._appID

	def close(self):
		"""
		Closes the connection.
		"""
		self._s.close()
		self._appIDs.remove(self._appID)

	def sendSimple(self,tp):
		"""
		Sends a simple message to the cqc server, for example a HELLO message if tp=CQC_TP_HELLO.
		"""
		hdr=CQCHeader()
		hdr.setVals(CQC_VERSION,tp,self._appID,0)
		msg=hdr.pack()
		self._s.send(msg)

	def sendCommand(self,qID,command):
		"""
		Sends a simple message and command message to the cqc server.
		"""
		#Send Header
		hdr=CQCHeader()
		hdr.setVals(CQC_VERSION,CQC_TP_COMMAND,self._appID,CQC_CMD_HDR_LENGTH)
		msg=hdr.pack()
		self._s.send(msg)

		#Send Command
		cmd_hdr=CQCCmdHeader()
		cmd_hdr.setVals(qID,command,0,0,0) #IS NOTIFY BLOCK AND ACTION IMPLEMENTED?
		cmd_msg=cmd_hdr.pack()
		self._s.send(cmd_msg)

	def sendCmdXtra(self,qID,command,xtra_qID=0,step=0,remote_app_ID=0,remote_node=0,remote_port=0,cmd_length=0):
		"""
		Sends a simple message, command message and xtra message to the cqc server.
		"""
		#Send Header
		hdr=CQCHeader()
		hdr.setVals(CQC_VERSION,CQC_TP_COMMAND,self._appID,CQC_CMD_HDR_LENGTH+CQC_CMD_XTRA_LENGTH)
		msg=hdr.pack()
		self._s.send(msg)

		#Send Command
		cmd_hdr=CQCCmdHeader()
		cmd_hdr.setVals(qID,command,0,0,0) #IS NOTIFY BLOCK AND ACTION IMPLEMENTED?
		cmd_msg=cmd_hdr.pack()
		self._s.send(cmd_msg)

		#Send Xtra
		xtra_hdr=CQCXtraHeader()
		xtra_hdr.setVals(xtra_qID,step,remote_app_ID,remote_node,remote_port,cmd_length)
		xtra_msg=xtra_hdr.pack()
		self._s.send(xtra_msg)

	def receive(self,maxsize=128): # WHAT IS GOOD SIZE?
		"""
		Receive the whole message from cqc server.
		Returns (CQCHeader,None) or (CQCHeader,CQCNotifyHeader) depending on the type of message.
		Maxsize is the max size of message.
		"""

		#Initilize buffer and check
		gotCQCHeader=False

		for _ in range(10):

			# Receive data
			data=self._s.recv(maxsize)

			# Read whatever we received into a buffer
			if self.buf:
				self.buf+=data
			else:
				self.buf=data

			# If we don't have the CQC header yet, try and read it in full.
			if not gotCQCHeader:
				if len(self.buf) < CQC_HDR_LENGTH:
					# Not enough data for CQC header, return and wait for the rest
					continue

				# Got enough data for the CQC Header so read it in
				gotCQCHeader = True;
				rawHeader = self.buf[0:CQC_HDR_LENGTH]
				currHeader = CQCHeader(rawHeader);

				# Remove the header from the buffer
				self.buf = self.buf[CQC_HDR_LENGTH:len(self.buf)]

				# logging.debug("CQC %s: Read CQC Header: %s", self.name, self.currHeader.printable())
			# Check whether we already received all the data
			if len(self.buf) < currHeader.length:
				# Still waiting for data
				# logging.debug("CQC %s: Incomplete data. Waiting.", self.name)
				continue
			else:
				break

		# We got all the data, read notify if there is any
		if currHeader.length==0:
			return (currHeader,None)
		try:
			rawNotifyHeader=self.buf[:CQC_NOTIFY_LENGTH]
			notifyHeader=CQCNotifyHeader(rawNotifyHeader)
			return (currHeader,notifyHeader)
		except struct.error as err:
			print(err)

class qubit:
	"""
	A qubit.
	"""
	_next_qID=0
	def __init__(self,cqc,wait_for_return=True):
		"""
		Initializes the qubit. The cqc connection must be given.
		If wait_for_return is true, the return message is printed before the method finishes.
		"""
		self._cqc=cqc

		# Which qID
		self._qID=self._next_qID
		self._next_qID+=1

		# Create new qubit at the cqc server
		self._cqc.sendCommand(self._qID,CQC_CMD_NEW)
		if wait_for_return:
			message=self._cqc.receive()
			print_return_msg(message)
	def __str__(self):
		return "Qubit at the node {}".format(self._cqc.name)

	def apply_I(self,wait_for_return=True):
		"""
		Performs an identity gate on the qubit.
		If wait_for_return is true, the return message is printed before the method finishes.
		"""
		self._cqc.sendCommand(self._qID,CQC_CMD_I)
		if wait_for_return:
			message=self._cqc.receive()
			print_return_msg(message)

	def apply_X(self,wait_for_return=True):
		"""
		Performs a X on the qubit.
		If wait_for_return is true, the return message is printed before the method finishes.
		"""
		self._cqc.sendCommand(self._qID,CQC_CMD_X)
		if wait_for_return:
			message=self._cqc.receive()
			print_return_msg(message)

	def apply_Y(self,wait_for_return=True):
		"""
		Performs a Y on the qubit.
		If wait_for_return is true, the return message is printed before the method finishes.
		"""
		self._cqc.sendCommand(self._qID,CQC_CMD_Y)
		if wait_for_return:
			message=self._cqc.receive()
			print_return_msg(message)

	def apply_Z(self,wait_for_return=True):
		"""
		Performs a Z on the qubit.
		If wait_for_return is true, the return message is printed before the method finishes.
		"""
		self._cqc.sendCommand(self._qID,CQC_CMD_Z)
		if wait_for_return:
			message=self._cqc.receive()
			print_return_msg(message)

	def apply_T(self,wait_for_return=True):
		"""
		Performs a T gate on the qubit.
		If wait_for_return is true, the return message is printed before the method finishes.
		"""
		self._cqc.sendCommand(self._qID,CQC_CMD_T)
		if wait_for_return:
			message=self._cqc.receive()
			print_return_msg(message)

	def apply_H(self,wait_for_return=True):
		"""
		Performs a Hadamard on the qubit.
		If wait_for_return is true, the return message is printed before the method finishes.
		"""
		self._cqc.sendCommand(self._qID,CQC_CMD_H)
		if wait_for_return:
			message=self._cqc.receive()
			print_return_msg(message)

	def apply_rot_X(self,step,wait_for_return=True):
		"""
		Applies rotation around the x-axis with the angle of 2*pi/256*step radians.
		If wait_for_return is true, the return message is printed before the method finishes.
		"""
		self._cqc.sendCmdXtra(self._qID,CQC_CMD_ROT_X,step=step)
		if wait_for_return:
			message=self._cqc.receive()
			print_return_msg(message)

	def measure(self):
		"""
		Measures the qubit in the standard basis and returns the measurement outcome.
		If now MEASOUT message is received, None is returned.
		"""
		self._cqc.sendCommand(self._qID,CQC_CMD_MEASURE)

		#Return measurement outcome
		message=self._cqc.receive()
		notifyHdr=message[1]
		return notifyHdr.outcome

def print_return_msg(message):
	"""
	Prints messsage returned by the receive method of CQCConnection.
	"""
	for hdr in message:
		try:
			print(hdr.printable())
		except AttributeError:
			pass