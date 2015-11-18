#!/Users/mnicolls/Documents/Work/Madrigal/bin/python

import sys, os, traceback
import cgi
import time



class radarToGeodeticService:
    """radarToGeodeticService is web service that allows access to the madrigal._Madrec.radarToGeodetic method.
    
    Like all my python cgi scripts, radarToGeodeticService has the following structure:  the entire cgi is
    contained in one class, with a main function at the end which serves simply to call the __init__
    function of the class.  This __init__ function is responsible for calling all other class methods.
    It is made up of a single try block, with the purpose of reporting all exceptions in well-formatted
    text to both the user and the administrator. The __init__ function first makes sure the pythonlib
    can be found.  It then calls setScriptState to validate the the cgi arguments, which are simply the
    arguments for the isprint command.

    If any uncaught exception is thrown, its caught by the __init__ try block.  If its an MadrigalError,
    additional information is available.  The catch blocks attempt to display the error message on the screen
    by backing out of of large number of possible tags, which might prevent its display (in any case, the error
    message will always be available in the page source.  The formatted error message is also sent to the email
    address given in the siteTab.txt metadata file.

    This script is not meant to be used directly by a user, and thus is named Service.  It is meant to be used by
    scripting languages such as Matlab that want to call getInstruments via the web

    Input cgi arguments::

        slatgd  - radar geodetic latitude
        
        slon - radar longitude

        saltgd - radar geodetic altitude
        
        az - a comma-separated list of radar azimuth in degrees (0 = north)
        
        el - a comma-separated list of radar elevation in degrees 

        range - a comma-separated list of radar range in km


    Returns comma-delimited data, one line for point in lists:

        1. geodetic latitude of point

        2. longitude of point

        3. geodetic altitude of point


    If error, returns error description


    Change history:

    Written by "Bill Rideout":mailto:wrideout@haystack.mit.edu  Oct. 10, 2005

    $Id: radarToGeodeticService.py,v 1.3 2008/07/25 18:55:28 brideout Exp $
    """

    # constants
    __scriptName = 'radarToGeodeticService'
    

    def __init__(self):
        """__init__ run the entire radarToGeodeticService script.  All other functions are private and called by __init__.

        Inputs: None
        
        Returns: void

        Affects: Ouputs radarToGeodetic data as a service.

        Exceptions: None.
        """


        # catch any exception, and write an appropriate message to user and to admin
        try:

            # check if pythonlibpath env variable exists
            # written 'PYTHON' + 'LIBPATH' to stop automatic replacement during setup
            temp = os.environ.get('PYTHON' + 'LIBPATH')
            if temp != None:
                    sys.path.append(temp)
		    
            # append path madroot/lib (needed only if python not installed by setup)
            sys.path.append('/Users/mnicolls/Documents/Work/Madrigal/lib/python')

            # prepare to handle MadrigalError
            import madrigal.admin
	    
        except ImportError:
	    
	    # Fatal error - madpy library not found
            print "Content-Type: text/html"
            print
            print "Unable to import the madrigal python library - please alert the sys admin!"
            sys.exit(0)
	    
        try:

            # set flag as to whether script headers have been written
            self.scriptHeaders = 0

            self.setScriptState()

            # output list on end points
            self.radarToGeodetic()

            

        except madrigal.admin.MadrigalError, e:
            # handle a MadrigalError

                
            errStr = 'Error occurred in script ' + self.__scriptName + '.'

            
            err = traceback.format_exception(sys.exc_info()[0],
                                             sys.exc_info()[1],
                                             sys.exc_info()[2])

            for errItem in err:
                errStr = errStr + '\n' + str(errItem)

        
            # add info about called form:
            if self.madForm != None:
                errStr = errStr + 'Form elements\n'
                for key in self.madForm.keys():
                    errStr = errStr + '\n' + str(key)
                    errStr = errStr + ' = ' + str(self.madForm.getvalue(key))

            if self.scriptHeaders == 0: # not yet printed
                print "Content-Type: text/plain"
                print
                
            print errStr

            self.admin = madrigal.admin.MadrigalNotify()
            self.admin.sendAlert('\n' + errStr,
                                 'Error running ' + self.__scriptName)


            print 'Your system administrator has been notified.'

        except SystemExit:
            sys.exit(0)

        except:
            # handle a normal error
            
                
            errStr = 'Error occurred in script ' + self.__scriptName + '.'

            
            err = traceback.format_exception(sys.exc_info()[0],
                                             sys.exc_info()[1],
                                             sys.exc_info()[2])

            for errItem in err:
                errStr = errStr + '\n' + str(errItem)

        
            # add info about called form:
            if self.madForm != None:
                errStr = errStr + 'Form elements\n'
                for key in self.madForm.keys():
                    errStr = errStr + '\n' + str(key)
                    errStr = errStr + ' = ' + str(self.madForm.getvalue(key))

            if self.scriptHeaders == 0: # not yet printed
                print "Content-Type: text/plain"
                print
                
            print errStr

            self.admin = madrigal.admin.MadrigalNotify()
            self.admin.sendAlert('\n' + errStr,
                                 'Error running ' + self.__scriptName)


            print 'Your system administrator has been notified.'

        # end __init__
        

    def setScriptState(self):

        print "Content-Type: text/plain\n"
        sys.stdout.flush()
	
        #create a form object
        self.madForm = cgi.FieldStorage()

        if not self.madForm.has_key('slatgd'):

            print 'This cgi script was called without the proper arguments.\n'

            sys.exit(0)
            
        else:
            self.slatgd = float(self.madForm.getvalue('slatgd'))
            self.slon = float(self.madForm.getvalue('slon'))
            self.saltgd = float(self.madForm.getvalue('saltgd'))
            
            az = self.madForm.getvalue('az')
            self.az = []
            items = az.split(',')
            for item in items:
                self.az.append(float(item))

            el = self.madForm.getvalue('el')
            self.el = []
            items = el.split(',')
            for item in items:
                self.el.append(float(item))

            thisRange = self.madForm.getvalue('range')
            self.range = []
            items = thisRange.split(',')
            for item in items:
                self.range.append(float(item))
            
            # check that all three input lists have the same length
            if len(self.az) != len(self.el) or len(self.az) != len(self.range):
                raise 'length of three comman-delimited input lists must be equal'


	
    def radarToGeodetic(self):

        import madrigal._Madrec

        for i in range(len(self.az)):
            result = madrigal._Madrec.radarToGeodetic(self.slatgd,
                                                      self.slon,
                                                      self.saltgd,
                                                      self.az[i],
                                                      self.el[i],
                                                      self.range[i])
            if result[0] < 1.1e-38 and result[0] > 0.9e-38:
                print 'missing,missing,missing'
            else:
                print '%f,%f,%f' % (result[0], result[1], result[2])
        
            

if __name__ == '__main__':

    # Script madLogin
    # This script only calls the init function of the class radarToGeodeticService
    # All work is done by the init function
    radarToGeodeticService()
