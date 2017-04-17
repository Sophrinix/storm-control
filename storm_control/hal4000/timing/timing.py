#!/usr/bin/env python
"""
Provides the (software) time base for a film.

Hazen 04/17
"""

from PyQt5 import QtCore

import storm_control.sc_library.parameters as params

import storm_control.hal4000.film.filmSettings as filmSettings
import storm_control.hal4000.halLib.halFunctionality as halFunctionality
import storm_control.hal4000.halLib.halMessage as halMessage
import storm_control.hal4000.halLib.halModule as halModule


class TimingFunctionality(halFunctionality.HalFunctionality):
    """
    This is tied to the appropriate camera/feed so that it emits a newFrame
    signal whenever the camera/feed does the same.
    """
    newFrame = QtCore.pyqtSignal(int)
    stopped = QtCore.pyqtSignal()

    def __init__(self, time_base = None, **kwds):
        super().__init__(**kwds)
        """
        time_base is a string containing the name of a feed.
        """
        self.cam_fn = None
        self.time_base = time_base

    def connectCameraFunctionality(self, camera_functionality):
        assert self.cam_fn is None
        assert (camera_functionality.getCameraName() == self.time_base)
        
        self.cam_fn = camera_functionality
        self.cam_fn.newFrame.connect(self.handleNewFrame)
        self.cam_fn.stopped.connect(self.handleStopped)

    def disconnectCameraFunctionality(self):
        self.cam_fn.newFrame.disconnect(self.handleNewFrame)
        self.cam_fn.stopped.disconnect(self.handleStopped)

    def getFPS(self):
        return self.cam_fn.getParameter("fps")
        
    def getTimeBase(self):
        return self.time_base
    
    def handleNewFrame(self, frame):
        self.newFrame.emit(frame.frame_number)

    def handleStopped(self):
        self.stopped.emit()


class Timing(halModule.HalModule):
    """
    (Software) timing for a film.

    Modules such as illumination that need to do something on every
    frame of a film are expected to time themselves using the timing
    functionality provided by this module.
    """
    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)
        self.timing_functionality = None

        self.parameters = params.StormXMLObject()

        self.parameters.add(params.ParameterSetString(description = "Feed to use a time base when filming",
                                                      name = "time_base",
                                                      value = "",
                                                      allowed = [""]))

        default_time_base = module_params.get("parameters").get("time_base")
        self.setAllowed([default_time_base])
        self.parameters.setv("time_base", default_time_base)

        # The timing to use for the film.
        halMessage.addMessage("film timing",
                              validator = {"data" : {"camera" : [True, str],
                                                     "film settings" : [True, filmSettings.FilmSettings],
                                                     "functionality" : [True, TimingFunctionality]},
                                           "resp" : None})

    def handleResponse(self, message, response):
        if message.isType("get camera functionality"):
            self.timing_functionality.connectCameraFunctionality(response.getData()["functionality"])
        
    def processMessage(self, message):

        if message.isType("configure1"):

            # Broadcast initial parameters.
            self.newMessage.emit(halMessage.HalMessage(source = self,
                                                       m_type = "initial parameters",
                                                       data = {"parameters" : self.parameters}))

        elif message.isType("feed names"):
            cur_time_base = self.parameters.get("time_base")
            self.parameters.getp("time_base").setAllowed(message.getData()["feed names"])
            self.parameters.setv("time_base", cur_time_base)

        elif message.isType("new parameters"):
            #
            # FIXME: The problem is that we won't know the allowed set of feed names until
            #        feeds.feeds sends the 'feed names' message. Using the old allowed
            #        might cause a problem as the new time base might not exist in the
            #        old allowed. For now we are just setting allowed to be whatever the
            #        time_base parameter value is. Then at 'feed names' we check that
            #        that the parameter is valid. If it is not valid this will break HAL
            #        at an unexpected point, the error should have been detected in
            #        'new parameters'. Also the editor won't work because the version of the
            #        parameter that it has only allows one value. Somehow we need to know
            #        the valid feed names at the new parameter stage..
            #
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"old parameters" : self.parameters.copy()}))
            p = message.getData()["parameters"].get(self.module_name)
            self.setAllowed([p.get("time_base")])
            self.parameters.setv("time_base", p.get("time_base"))
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"new parameters" : self.parameters}))

        elif message.isType("start film"):
            self.timing_functionality = TimingFunctionality(time_base = self.parameters.get("time_base"))
            self.newMessage.emit(halMessage.HalMessage(source = self,
                                                       m_type = "get camera functionality",
                                                       data = {"camera" : self.timing_functionality.getTimeBase()}))

            #
            # This could be a race? The self.timing_functionality won't do anything until we get
            # a response to the 'get camera functionality' request. Hopefully the camera(s) won't
            # have started by then.
            #
            # I think this will be okay because we force a sync before sending 'start camera' and
            # these messages should both be in the queue ahead of the 'start camera' message.
            #
            self.newMessage.emit(halMessage.HalMessage(source = self,
                                                       m_type = "film timing",
                                                       data = {"camera" : self.timing_functionality.getTimeBase(),
                                                               "film settings" : message.getData()["film settings"],
                                                               "functionality" : self.timing_functionality}))
            
        elif message.isType("stop film"):
            self.timing_functionality.disconnectCameraFunctionality()
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"parameters" : self.parameters.copy()}))

    def setAllowed(self, allowed):
        self.parameters.getp("time_base").setAllowed(allowed)
