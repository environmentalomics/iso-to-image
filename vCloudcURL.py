#!/usr/bin/env python3
# encoding: UTF-8
__author__ = 'tbooth'

""" This is loosely based on vCloudHTTP.py by Charlie L. but I want to:
    1) Use pyCURL because it lets me report progress of uploads.
    2) Have an actual connection object, rather than a bunch of static
       methods and an auth string that gets passed around the functions.
"""

import sys
from os.path import getsize
import pycurl
from io import BytesIO # This needs Py3!
from traceback import print_exc
import xml.etree.ElementTree as ET
from itertools import *
from time import sleep, time
try:
    from getpass import getpass
except ImportError:
    #We'll do without it.
    pass

import logging
L = logging.getLogger(__name__)

# TODO - do I need the SIGPIPE stuff?
def ignore_sigpipe():
    from signal import signal, SIGPIPE, SIG_DFL
    signal(SIGPIPE, SIG_DFL)

#TODO - work out exactly what the versions 1.5 and 5.5 signify and where this
# should actually be saved.
_magic_header = "Accept:application/*+xml;version=5.5"
_auth_header = "x-vcloud-authorization"

class vCloudcURL(object):

    def __init__(self, url, version='1.5'):
        #URL and version should not be changed once the object has been created.
        self.url = url
        self.session_url = url + "/api/session"
        self.version = version
        self.auth = None

    def disconnect(self):
        #Do disconnection
        # TODO - disconnect on destructor

        # TODO - get this properly.  For now assume the disconnect URL is the
        # session url with the final 's' removed.
        url_to_delete = self.session_url[0:-1]

        if self.auth is None:
            L.warning("There is no VCloud session to disconnect.")
        else:
            L.debug("Disconnecting from %s" % url_to_delete)
            c1 = _get_curl_handle(url_to_delete, 'DELETE', extra_headers = self.auth)

            h1, _ = _curl_perform(c1)

            #Look for "HTTP/1.1 204 No Content" in the result
            if h1['_code'] == "204" :
                L.info("Disconnected OK")
                self.auth = None
                self.org = None
            else :
                L.info("Disconnect failed with status " + h1['_'])

    #Gets the appropriate login URL by asking the server about it
    def _get_login_url(self):

        c1 = _get_curl_handle("%s/api/versions" % self.url)
        h1, r1 = _curl_perform_xml(c1)

        #Validate version
        version_seen = r1.find('.//{http://www.vmware.com/vcloud/versions}Version').text
        if version_seen != self.version :
            raise vCloudException("Version seen is not " + _version_supported, 200)

        return r1.find('.//{http://www.vmware.com/vcloud/versions}LoginUrl').text

    def check_server(self):
        try:
            self._get_login_url()
        except:
            return False
        return True

    def connect(self, org, username, password):
        #Connect to the server and obtain the 'auth' token.
        L.info("Starting session on %s." % self.url)
        self.session_url = self._get_login_url()

        L.debug("Starting session on %s." % self.session_url)

        c2 = _get_curl_handle(self.session_url, 'POST')
        #Does this work with a colon in the password??  Yes!
        c2.setopt(pycurl.USERPWD, '%s@%s:%s' % (username, org, password))
#         L.info("Setting userpwd to %s@%s:%s" % (username, org, password))

        h2, r2 = _curl_perform_xml(c2)

        if(h2['_code'] == "401"):
            raise NoConnectionException("Session auth failed - probably bad username/password")
#             clear_the_password(self.sess_url, self.sess_org, self.sess_user)
        elif(h2['_code'] != "200"):
#             L.warning(repr(h2) + repr(r2))
            raise vCloudException("Session auth failed with unexpected status " + h2['_'], int(h2['_code']))

        self.auth = [ "%s : %s" % (_auth_header, h2[_auth_header]) ]
        self.org = org

        #Returns the resulting XML as an ElementTree
        return r2

    def _check_connected(self):
        if self.auth is None:
            raise NoConnectionException("There is no active vCloud connection.")

    # Basic fetch.  Returns XML.
    def httpGET(self, url):
        self._check_connected()

        req = _get_curl_handle(url, extra_headers = self.auth)

        ( h, resultXML ) = _curl_perform_xml(req)

        #GETs always should return a 200 result
        if(h['_code'] != "200"):
            raise vCloudException("GET failed with unexpected status " + h['_'], int(h['_code']))

        return resultXML

    # Post might be sending some data or maybe just pushing a button
    def httpPOST(self, url, content_type = None, xml = None):
        self._check_connected()

        if xml and not content_type :
            content_type = 'text/xml'

        if xml and xml.__class__ != bytes:
            xml = xml.encode('utf8')

        extra_headers = []
        if content_type:
            extra_headers.append("Content-Type: %s" % content_type)

        req = _get_curl_handle(url, 'POST',
                extra_headers = self.auth + extra_headers)

        ( h, resultXML ) = _curl_perform_xml(req, xml)

        #Any 20x response is OK
        if(not h['_code'].startswith("20")):
            raise vCloudException("POST failed with unexpected status " + h['_'], int(h['_code']))

        return resultXML

    def httpPUT(self, url, content_type, data):
        self._check_connected()

        #Like POST but we also regard status 100 as success.  Also I'm not encoding the data here
        #but I need to work out what's really up with that.
        #And finally I don't expect any XML back

        req = _get_curl_handle(url, 'PUT',
                extra_headers = self.auth + [ "Content-Type: %s" % content_type ])

        ( h, _ ) = _curl_perform(req, data)

        if(not h['_code'].startswith("20") and not h['_code'] == "100"):
            raise vCloudException("PUT failed with unexpected status " + h['_'], int(h['_code']))



    def httpDELETE(self, url):
        self._check_connected()

        req = _get_curl_handle(url, 'DELETE', extra_headers = self.auth)

        headers, _  = _curl_perform(req)

        #Expectected response is 204 No Content or 202 Accepted
        if(not headers['_code'].startswith("20")):
            raise vCloudException("DELETE failed with unexpected status " + h['_'], int(h['_code']))

        #Nothing to return

    def httpUPLOAD(self, url, filename, filesize=-1, progress_to=None):
        #Uploads a file from disk and shows progress, normally on STDOUT.
        #Standard Python exceptions will be thrown if the file cannot be read.
        #If the file is not a regular file you should supply the correct size.

        c8 = _get_curl_handle(url, 'PUT', extra_headers = self.auth )

        if(filesize < 0):
            #How big is the file?
            filesize = getsize(filename)

        c8.setopt(pycurl.INFILESIZE_LARGE, filesize)
        c8.setopt(pycurl.TIMEOUT, 0) # Otherwise it times out mid upload.

        #I think this is how you stream upload from a file.
        c8.setopt(pycurl.UPLOAD, 1)
        c8.setopt(pycurl.READFUNCTION, open(filename, "br").read)

        # The VMWare doc advises that I should start the upload in a separate thread then
        # poll for how many bytes have been uploaded.  Or can I just get CURL to tell me?
        # http://pycurl.sourceforge.net/doc/callbacks.html suggests I can
        progressor = ProgressDisplay(print_to=progress_to)
        c8.setopt(pycurl.NOPROGRESS, 0)
        c8.setopt(pycurl.PROGRESSFUNCTION, progressor.my_progress)
        # Note that XFERINFOFUNCTION is supposedly the newer way to do this.  Maybe worth
        # a try later.

        L.info("Transferring %s" % filename)

        h, _ = _curl_perform(c8)

        # What do we expect to see in the response?  I guess a 20x of some sort.
        # It seems 100 Continue is also OK
        if not (h['_code'].startswith("20") or h['_code'] == '100' ):
            raise vCloudException("Upload failed with unexpected status " + h['_'], int(h['_code']))

        #Need at least a newline after last print
        L.info(" Transfer done")

        return progressor.bytes_transferred

# An exception for general errors
class vCloudException(Exception):

    def __init__(self, message, code = -1) :
        super().__init__(message)
        self.code = code

# An exception for trying to do anything on an unconnected connection
class NoConnectionException(Exception):
    pass

# A class used by cURL to store header data from a response.
class HeaderCollector:

    def __init__(self) :
        self.headers = {}

    def append_line(self, line) :
        #HTTP headers should always be in this format
        if line.decode :
            line = line.decode('iso-8859-1')

        #Save the HTTP... line as header "_"
        if '_' not in self.headers and line.startswith("HTTP/") :
            self.headers['_'] = line.strip()
            self.headers['_code'] = self.headers['_'].split()[1]
        #Simply ignoring multi-line headers
        elif ':' in line:
            name, value = line.split(':', 1)
            self.headers[name.strip().lower()] = value.strip()

    def clear(self) :
        self.__init__()

# A class used by cURL to show transfer progress
class ProgressDisplay:
    def __init__(self, print_to) :
        self.minperiod = 500
        self.lastupdate = 0
        self.done = False
        self.print_to = print_to
        self.bytes_transferred = 0

    def my_progress(self, download_t, download_d, upload_t, upload_d):
        self.bytes_transferred = upload_d
        if self.print_to is None:
            return 0

        #Libcurl calls this function quite rapidly.  I want to limit updates
        #to one every .5 seconds
        if self.minperiod > 0:
            timenowms = int(time() * 1000)
            if not self.done and upload_d == upload_t:
                #In this case, update even if within minperiod
                self.done = True
            elif timenowms < ( self.lastupdate + self.minperiod ):
                return 0
            self.lastupdate = timenowms

        if upload_t == 0:
            print("\rInitialising upload.", end='', flush=True, file=self.print_to)
        else:
            print("\r  %i of  %i bytes transferred (%.1f%%)" %
                      (upload_d,
                              upload_t,             upload_d / upload_t * 100 ),
                  end='', flush=True, file=self.print_to)

        return 0


#Utility functions to help me with cURL
def _get_curl_handle(url, method = 'GET', extra_headers = None) :
    # See https://github.com/pycurl/pycurl/blob/master/examples/xmlrpc_curl.py
    c = pycurl.Curl()
    c.fp = None
    c.setopt(pycurl.FOLLOWLOCATION, 1)
    c.setopt(pycurl.MAXREDIRS, 5)
    c.setopt(pycurl.CONNECTTIMEOUT, 30)
    c.setopt(pycurl.TIMEOUT, 300)
    c.setopt(pycurl.NOSIGNAL, 1)

    # For the current systems we don't expect to be able to validate HTTPS certs
    # For production, add the certs and re-enable authentication
    c.setopt(pycurl.SSL_VERIFYPEER, 0)
    c.setopt(pycurl.SSL_VERIFYHOST, 0)

    # _magic_header wards off error 406 Not Acceptable
    c.setopt(pycurl.HTTPHEADER, [_magic_header] + ( extra_headers or [] ) )

    c.setopt(pycurl.URL, url)
    #Only for debugging.
    c.saved_URL = url

    method = method.upper()
    if method == 'GET' :
        pass
    elif method == 'PUT' or method == 'POST' :
        c.setopt(pycurl.CUSTOMREQUEST, method) # really??
    else :
        c.setopt(pycurl.CUSTOMREQUEST, method)
        if method == 'HEAD' or method == 'DELETE' :
            c.setopt(pycurl.NOBODY, 1)

    return c

def _curl_perform(c, postdata = None) :
    b = BytesIO()
    c.setopt(pycurl.WRITEFUNCTION, b.write)

    h = HeaderCollector()
    c.setopt(pycurl.HEADERFUNCTION, h.append_line)

    #Extract URL just in case we need it to report an error properly.
    #url = re.search("://(.*)", c.saved_URL).group(1)

    #For syncronous posting of a string.  The caller should have set
    #the method to PUT or POST and set the Content-Type header
    #and dealt with the encoding  of postdata
    if postdata :
        #assert(postdata.__class__ == bytes)
        c.setopt(pycurl.POST, 1)
        c.setopt(pycurl.POSTFIELDS, postdata)
        L.info("Posting to %s:" % c.saved_URL  )
        L.debug(postdata)

    #print("DEBUG - about to make cURL call")
    c.perform()
    #print("DEBUG - call finished")

    # Get response headers as a simple dict
    return (h.headers, b.getvalue(), )

#Convenience version that returns XML
def _curl_perform_xml(c, postdata = None) :
#     except pycurl.error, v:
#         raise xmlrpclib.ProtocolError(url, v[0], v[1], None)
    (h, b) = _curl_perform(c, postdata)

    response_as_xml = None
    if b.strip() :
        response_as_xml = ET.fromstring(b)

    return (h, response_as_xml, )

