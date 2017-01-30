#!/usr/bin/env python
"""

Heuristically programmed ALgorithmic STORM setup control.

This module handles setup, clean up and message passing
between the various sub-modules that define the 
behavior. Each of these modules must be a sub-class of
the HalModule class in halLib.halModule. Setup specific
configuration is provided by a 'XX_config.xml' file
examples of which can be found in the xml folder.

In addition this module handles drag/drops and
the film notes QTextEdit.

Jeff 03/14
Hazen 01/17

"""

from collections import deque
import importlib
import os

from PyQt5 import QtCore, QtGui, QtWidgets

import storm_control.sc_library.halExceptions as halExceptions
import storm_control.sc_library.hdebug as hdebug
import storm_control.sc_library.hgit as hgit
import storm_control.sc_library.parameters as params

import storm_control.hal4000.halLib.halMessage as halMessage
import storm_control.hal4000.halLib.halMessageBox as halMessageBox
import storm_control.hal4000.halLib.halModule as halModule
import storm_control.hal4000.qtWidgets.qtAppIcon as qtAppIcon


#
# Main window controller.
#
class HalController(halModule.HalModule):
    """
    HAL main window controller.

    This sends the following message:
    'close event'
    'new directory'
    'new parameters file'
    'new shutters file'
    """
    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)
        self.view.guiMessage.connect(self.handleGuiMessage)

    def cleanUp(self, qt_settings):
        self.view.cleanUp(qt_settings)

    def handleGuiMessage(self, message):
        """
        This just passes through the messages from the GUI.
        """
        self.newMessage.emit(message)

    def processMessage(self, message):
        super().processMessage(message)
        if (message.level == 1):
            if (message.m_type == "setup name"):
                self.view.setTitle(message.data)

            elif (message.m_type == "new directory"):
                self.view.setFilmDirectory(message.data)

            elif (message.m_type == "start"):
                self.view.show()

                    
class Classic(HalController):
    """
    The 'classic' main window controller.
    """
    def __init__(self, **kwds):
        self.view = ClassicView(**kwds)
        super().__init__(**kwds)
        
              
class Detached(HalController):
    """
    The 'detached' main window controller.
    """
    def __init__(self, **kwds):
        self.view = DetachedView(**kwds)        
        super().__init__(**kwds)


#
# Main window View.
#
class HalView(QtWidgets.QMainWindow):
    """
    HAL main window view.
    """
    guiMessage = QtCore.pyqtSignal(object)

    def __init__(self, module_name = "", module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)

        if self.classic_view:
            import storm_control.hal4000.qtdesigner.hal4000_ui as hal4000Ui
        else:
            import storm_control.hal4000.qtdesigner.hal4000_detached_ui as hal4000Ui
        self.ui = hal4000Ui.Ui_MainWindow()
        self.ui.setupUi(self)

        self.close_now = False
        self.close_timer = QtCore.QTimer(self)
        self.film_directory = ""
        self.module_name = module_name
                
        # Set icon.
        self.setWindowIcon(qtAppIcon.QAppIcon())

        # Configure based on saved settings.
        self.move(qt_settings.value(self.module_name + ".pos", self.pos()))
        self.resize(qt_settings.value(self.module_name + ".size", self.size()))
        self.xml_directory = str(qt_settings.value(self.module_name + ".xml_directory", ""))
        
        # ui signals
        self.ui.actionDirectory.triggered.connect(self.handleDirectory)
        self.ui.actionSettings.triggered.connect(self.handleSettings)
        self.ui.actionShutter.triggered.connect(self.handleShutters)
        self.ui.actionQuit.triggered.connect(self.handleQuit)

        # Configure close timer.
        self.close_timer.setInterval(5)
        self.close_timer.timeout.connect(self.handleCloseTimer)
        self.close_timer.setSingleShot(True)
        
    def cleanUp(self, qt_settings):
        """
        Save GUI settings and close.
        """
        qt_settings.setValue(self.module_name + ".pos", self.pos())
        qt_settings.setValue(self.module_name + ".main", self.size())
        qt_settings.setValue(self.module_name + ".xml_directory", self.xml_directory)

        self.close()

    def closeEvent(self, event):
        #
        # This is a little fiddly. Basically the problem is that we'll get event
        # if the user clicks on the X in the upper right corner of the window.
        # In that case we don't want to close right away as core needs some
        # time to clean up the modules. However we also get this event when
        # we call close() and at that point we do want to close.
        #
        # We use a timer with a small delay because without it it appeared
        # that this method was getting called twice with same event object when
        # we clicked on the X, and this meant that you had to click the X
        # twice.
        #
        if not self.close_now:
            event.ignore()
            self.close_timer.start()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
            
    def dropEvent(self, event):

        # Get filename(s)
        filenames = []
        for url in event.mimeData().urls():
            filenames.append(str(url.toLocalFile()))

        # Send message(s) with filenames.
        for filename in sorted(filenames):
            [file_type, error_text] = params.fileType(filename)
            if (file_type == "parameters"):
                self.guiMessage.emit(halMessage.HalMessage(source = self,
                                                           m_type = "new parameters file",
                                                           data = filename))
            elif (file_type == "shutters"):
                self.guiMessage.emit(halMessage.HalMessage(source = self,
                                                           m_type = "new shutters file",
                                                           data = filename))
            else:
                if error_text:
                    halMessageBox.halMessageBox("XML file parsing error " + error_text)
                else:
                    halMessageBox.halMessageBox("File type not recognized")

    def handleCloseTimer(self):
        self.guiMessage.emit(halMessage.HalMessage(source = self,
                                                   m_type = "close event",
                                                   sync = True))
            
    def handleDirectory(self, boolean):
        new_directory = QtWidgets.QFileDialog.getExistingDirectory(self, 
                                                                   "New Directory",
                                                                   self.film_directory,
                                                                   QtWidgets.QFileDialog.ShowDirsOnly)
        #
        # FIXME: Why do we have the existence check? Is it possible to get a directory that does not exist?
        #
        if new_directory and os.path.exists(new_directory):
            self.film_directory = new_directory
            self.guiMessage.emit(halMessage.HalMessage(source = self,
                                                       m_type = "new directory",
                                                       data = self.film_directory))

    def handleSettings(self, boolean):
        parameters_filename = QtWidgets.QFileDialog.getOpenFileName(self,
                                                                    "New Settings",
                                                                    self.xml_directory, 
                                                                    "*.xml")[0]
        if parameters_filename:
            self.xml_directory = os.path.dirname(parameters_filename)
            self.guiMessage.emit(halMessage.HalMessage(source = self,
                                                       m_type = "new parameters file",
                                                       data = parameters_filename))

    def handleShutters(self, boolean):
        shutters_filename = QtWidgets.QFileDialog.getOpenFileName(self, 
                                                                  "New Shutter Sequence", 
                                                                  self.xml_directory, 
                                                                  "*.xml")[0]
        if shutters_filename:
            self.xml_directory = os.path.dirname(shutters_filename)
            self.guiMessage.emit(halMessage.HalMessage(source = self,
                                                       m_type = "new shutters file",
                                                       data = shutters_filename))

    def handleQuit(self, boolean):
        self.close_now = True
        self.guiMessage.emit(halMessage.HalMessage(source = self,
                                                   m_type = "close event",
                                                   sync = True))

    def setFilmDirectory(self, film_directory):
        self.film_directory = film_directory

    def setTitle(self, title):
        if (hgit.getBranch().lower() != "master"):
            title += " (" + hgit.getBranch() + ")"
        self.setWindowTitle(title)
        
        
class ClassicView(HalView):
    """
    The 'classic' main window view.
    """
    def __init__(self, **kwds):
        self.classic_view = True
        super().__init__(**kwds)


class DetachedView(HalView):
    """
    The 'detached' main window view. This includes a record
    button that this view has to handle.
    """
    def __init__(self, **kwds):
        self.classic_view = False
        super().__init__(**kwds)


#
# The core..
#
class HalCore(QtCore.QObject):
    """
    The core of it all. It sets everything else up, handles 
    the message passing and tears everything down.

    This sends the following messages:
    'configure'
    'new directory'
    'new parameters file'
    'setup name'
    'start'
    """
    def __init__(self, config = None, parameters_file_name = None, **kwds):
        super().__init__(**kwds)

        self.modules = []
        self.module_name = "core"
        self.qt_settings = QtCore.QSettings("storm-control", "hal4000" + config.get("setup_name").lower())
        self.queued_messages = deque()
        self.sent_messages = []
        self.sync_timer = QtCore.QTimer(self)

        self.sync_timer.setInterval(50)
        self.sync_timer.timeout.connect(self.handleMessage)
        self.sync_timer.setSingleShot(True)

        # Load all the modules.
        for module_name in config.get("modules").getAttrs():
            module_params = config.get("modules").get(module_name)
            a_module = importlib.import_module("storm_control.hal4000." + module_params.get("module_name"))
            a_class = getattr(a_module, module_params.get("class_name"))
            self.modules.append(a_class(module_name = module_name,
                                        module_params = module_params,
                                        qt_settings = self.qt_settings))

        # Connect signals.
        for module in self.modules:
            module.newFrame.connect(self.handleFrame)
            module.newMessage.connect(self.handleMessage)

        # Broadcast setup name.
        self.handleMessage(halMessage.HalMessage(source = self,
                                                 m_type = "setup name",
                                                 data = config.get("setup_name")))

        # Broadcast starting directory.
        self.handleMessage(halMessage.HalMessage(source = self,
                                                 m_type = "new directory",
                                                 data = config.get("directory")))
        
        # Tell modules to finish configuration
        #
        # FIXME: Do we need this? Or can we roll it into 'start'
        #
        self.handleMessage(halMessage.HalMessage(source = self,
                                                 m_type = "configure",
                                                 data = {"directory" : config.get("directory"),
                                                         "setup_name" : config.get("setup_name")}))

        # Tell the modules to start.
        self.handleMessage(halMessage.HalMessage(source = self,
                                                 m_type = "start",
                                                 sync = True))

        # Initial parameters (if any).
        if parameters_file_name is not None:
            self.handleMessage(halMessage.HalMessage(source = self,
                                                     m_type = "new parameters file",
                                                     data = parameters_file_name))
                                                     
            
    def cleanup(self):
        print(" Dave? What are you doing Dave?")
        print("  ...")
        for module in self.modules:
            module.cleanUp(self.qt_settings)

    def handleFrame(self, new_frame):
        """
        I was split on whether or not these should also just be messages.
        However, since there will likely be a lot of them I decided they 
        should be handled separately.
        """
        for module in self.modules:
            module.handleFrame(new_frame)
            
    def handleMessage(self, message = None):

        # Remove all the messages that have already been
        # handled from the list of sent messages.
        for sent_message in self.sent_messages:
            if (sent_message.ref_count == 0):
                self.sent_messages.remove(sent_message)
                sent_message.finalize()

                # Notify the sender if errors occured while processing the message.
                if sent_message.hasErrors():
                    sent_message.getSource().messageError(sent_message.getErrors())

                # Notify the sender of any responses to the message.
                if sent_message.hasResponses():
                    sent_message.getSource().messageResponse(sent_message.getResponses())
                
        # Add this message to the queue.
        if message is not None:
            if not message.m_type in halMessage.valid_messages:
                raise halExceptions.HalException("Invalid message type '" + message.m_type + "' received from " + message.getSourceName())
            self.queued_messages.append(message)

        # Process the next message.
        if (len(self.queued_messages) > 0):
            cur_message = self.queued_messages.popleft()
            print(cur_message.source.module_name, cur_message.m_type, cur_message.ref_count)

            #
            # If this message requested synchronization and there are
            # pending messages then push it back into the queue and wait.
            #
            if cur_message.sync and (len(self.sent_messages) > 0):
                self.queued_messages.appendleft(cur_message)
                self.sync_timer.start()
            
            #
            # Otherwise process the message.
            #
            else:
                # Check for "closeEvent" message from the main window.
                if (cur_message.getSourceName() == "hal") and (cur_message.m_type == "close event"):
                    self.cleanup()

                # Otherwise send the message.
                else:
                    self.sent_messages.append(cur_message)
                    for module in self.modules:
                        cur_message.ref_count += 1
                        module.handleMessage(cur_message)

                    # Process any remaining messages.
                    #
                    # Maybe use a timer here so that there is time to
                    # do something else between the messages?
                    #
                    if (len(self.queued_messages) > 0):
                        self.handleMessage()


    
if (__name__ == "__main__"):

    # Use both so that we can pass sys.argv to QApplication.
    import argparse
    import sys

    # Get command line arguments..
    parser = argparse.ArgumentParser(description = 'STORM microscope control software')
    parser.add_argument('config', type=str, help = "The name of the configuration file to use.")

    args = parser.parse_args()

    # FIXME: Should allow an (optional) initial setup file name.
    
    # Start..
    app = QtWidgets.QApplication(sys.argv)

    # Set default font size for linux.
    if (sys.platform == "linux2"):
        font = QtGui.QFont()
        font.setPointSize(8)
        app.setFont(font)

    # Splash Screen.
    pixmap = QtGui.QPixmap("splash.png")
    splash = QtWidgets.QSplashScreen(pixmap)
    splash.show()
    app.processEvents()

    # Load configuration.
    config = params.config(args.config)

    # Start logger.
    hdebug.startLogging(config.get("directory") + "logs/", "hal4000")
    
    # Setup HAL and all of the modules.
    hal = HalCore(config)

    # Hide splash screen and start.
    splash.hide()
    #hal.show()

    app.exec_()


#
# The MIT License
#
# Copyright (c) 2017 Zhuang Lab, Harvard University
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