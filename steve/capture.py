#!/usr/bin/python
#
## @file
#
# Handles telling the acquisition program to get
# a picture & converts the captured image into a
# QPixmap.
#
# Hazen 02/13
#

import math
import numpy
import time

from PyQt4 import QtCore, QtGui

# Debugging
import sc_library.hdebug as hdebug

# Communication with the acquisition software
import sc_library.tcpClient as tcpClient
import sc_library.tcpMessage as tcpMessage

# Reading DAX files
import sc_library.daxspereader as daxspereader

import coord

## StageMessage
#
# Creates stage messages for communication via TCPClient.
#
# @param stagex The stage x coordinate.
# @param stagey The stage y coordinate.
#
def stageMessage(stagex, stagey):  
    return tcpMessage.TCPMessage(message_type = "Move Stage",
                                 message_data = {"stage_x":stagex,
                                                 "stage_y":stagey})


## Image
#
# Image class for temporary storage of image data.
#
class Image():

    ## __init__
    #
    # @param data The image data (a numpy array).
    # @param size [image width, image height, number of frames].
    # @param display_scale [image value that equals 0, image value that equals 255].
    # @param location [stage x, stage y].
    # @param params The HAL xml file that was used to acquire the image.
    #
    def __init__(self, data, size, display_scale, location, params):
        self.data = data
        self.height = size[0]
        self.image_min = display_scale[0]
        self.image_max = display_scale[1]
        self.parameters_file = params
        self.width = size[1]

        self.x_um = location[0]
        self.y_um = location[1]

        # Calculate location in pixels.
        a_point = coord.Point(self.x_um, self.y_um, "um")
        self.x_pix = a_point.x_pix
        self.y_pix = a_point.y_pix

    ## __repr__
    #
    def __repr__(self):
        return hdebug.objectToString(self, "capture.Image", ["height", "width", "x_um", "y_um"])

## Capture
#
# Handles capturing images from HAL. Instructions to HAL about how
# to take the image are sent by TCP/IP. Once the image is acquired
# it is read from the disc (and not communicated directly back to
# this program).
#
# The TCP/IP connection is made and broken for each request (take a
# movie or move to a position). This is done for user convenience
# because when the connection is active some features of HAL, such 
# as movie acquisition, are locked out.
#
class Capture(QtCore.QObject):
    captureComplete = QtCore.pyqtSignal(object)
    disconnected = QtCore.pyqtSignal()

    ## __init__
    #
    # @param parameters A parameters xml object.
    #
    @hdebug.debug
    def __init__(self, parameters):
        QtCore.QObject.__init__(self)
        self.busy = True
        self.curr_x = 0.0
        self.curr_y = 0.0
        self.dax = None
        self.directory = parameters.directory
        self.goto = False
        self.filename = parameters.image_filename
        self.flip_horizontal = parameters.flip_horizontal
        self.flip_vertical = parameters.flip_vertical
        self.movies_remaining = 0
        self.transpose = parameters.transpose

        self.tcp_client = tcpClient.TCPClient()
        self.tcp_client.comLostConnection.connect(self.handleDisconnect)
        self.tcp_client.messageReceived.connect(self.handleMessageReceived)
        self.connected = False

    ## captureDone
    #
    # This is called when we get the (movie) completion method from HAL. It
    # attempts to find the image that HAL just took on the disk, creates a
    # Image object and emits the captureComplete signal.
    #
    # @param a_string Not used.
    #
    @hdebug.debug
    def captureDone(self):
        print "captureDone"

        # determine filename
        filename = self.directory + self.filename + ".dax"

        # load image
        self.loadImage(filename)

    ## captureStart
    #
    # Called to take a image at stagex, stagey. This tells HAL to move,
    # then starts a timer. When the timer fires the image is taken. The
    # delay time of the timer depends on the distance of the move.
    #
    # @param stagex The x position to take the image at.
    # @param stagey The y position to take the image at.
    #
    # @return True/False if starting capture was successful.
    #
    @hdebug.debug
    def captureStart(self, stagex, stagey):
        if self.busy:
            print "captureStart: busy"
        else:
            print "captureStart:", stagex, stagey
            if not self.tcp_client.isConnected():
                self.commConnect(True)

            if self.tcp_client.isConnected():
                message = stageMessage(stagex, stagey)
                message.addData("captureStart", True)
                self.tcp_client.sendMessage(message)
                self.busy = True
                return True
            else:
                print "captureStart: not connected"
                return False

    ## commConnect
    #
    # Initiate communication with HAL.
    #
    # @param set_directory (Optional) Tell HAL to change it's working directory, default is False.
    #
    @hdebug.debug
    def commConnect(self, set_directory = False):
        self.tcp_client.startCommunication()
        if self.tcp_client.isConnected() and set_directory:
            message = tcpMessage.TCPMessage(message_type = "Set Directory",
                                            message_data = {"directory" : self.directory})
            self.tcp_client.sendMessage(message)

    ## commDisconnect
    #
    # Stop communication with HAL.
    #
    @hdebug.debug
    def commDisconnect(self):
        self.busy = False
        self.tcp_client.stopCommunication()

    ## gotoPosition
    #
    # Called to move to stagex, stagey.
    #
    # @param stagex The x position to move to.
    # @param stagey The y position to move to.
    #
    @hdebug.debug
    def gotoPosition(self, stagex, stagey):
        if self.busy:
            print "gotoPosition: busy"
        
        else:
            print "gotoPosition:", stagex, stagey

            if not self.tcp_client.isConnected():
                self.commConnect()

            if self.tcp_client.isConnected():
                self.busy = True
                self.tcp_client.sendMessage(stageMessage(stagex, stagey))
            else:
                print "gotoPosition: not connected"

    ## handleDisconnect
    #
    # Called when HAL disconnects.
    #
    @hdebug.debug
    def handleDisconnect(self):
        self.busy = False

    ## handleMessageReceived
    #
    # Handles the messageReceived signal from the TCPClient.
    #
    # @param message A TCPMessage object.
    #
    @hdebug.debug
    def handleMessageReceived(self, message):
        if not (message.getData("captureStart") == None):
            new_message = tcpMessage.TCPMessage(message_type = "Take Movie",
                                                message_data = {"name" : self.filename,
                                                                "length" : 1,
                                                                "movie" : True})
            self.tcp_client.sendMessage(new_message)
        elif not (message.getData("directory") == None):
            pass
        elif not (message.getData("movie") == None):
            self.captureDone()
        else:
            self.busy = False

    ## loadImage
    #
    # Load a dax image. This is called by captureDone to
    # load the image. It is also called directly by Steve
    # to load images chosen by the user.
    #
    @hdebug.debug
    def loadImage(self, filename):
        self.busy = False
        success = False

        # Deals with a file system race condition?
        # Or is it a acquisition software problem?
        time.sleep(0.05)
        tries = 0
        while (not success) and (tries < 4):
            try:
                self.dax = daxspereader.DaxReader(filename, verbose = 1)
                frame = self.dax.loadAFrame(0)
                self.dax.closeFilePtr()
                success = True
            except:
                print "Failed to load:", filename
                frame = None
                time.sleep(0.05)
            tries += 1

        if type(frame) == type(numpy.array([])):
            if self.flip_horizontal:
                frame = numpy.fliplr(frame)
            if self.flip_vertical:
                frame = numpy.flipud(frame)
            if self.transpose:
                frame = numpy.transpose(frame)
            image = Image(frame,
                          self.dax.filmSize(),
                          self.dax.filmScale(),
                          self.dax.filmLocation(),
                          self.dax.filmParameters())

            self.captureComplete.emit(image)
    
    ## setDirectory
    #
    # Sets self.directory to directory.
    #
    # @param directory The new working directory (as a string).
    #
    @hdebug.debug
    def setDirectory(self, directory):
        self.directory = directory

    ## shutDown
    #
    # Close the TCP/IP connection, if it is still open.
    #
    @hdebug.debug
    def shutDown(self):
        if self.tcp_client.isConnected():
            self.commDisconnect()

#
# The MIT License
#
# Copyright (c) 2013 Zhuang Lab, Harvard University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
