#!/usr/bin/env python3
# I have now got packer to make .ova files from .iso files.
# And I think I can get the right VMWare tools installed onto the images with the
# right options set.  Good.

# After disabling IPV6 and disabling password-based log-in and re-jigging the .ovf file
# I should be able to transmit the image to VCloud using this procedure:

# pubs.vmware.com/vcd-51/index.jsp?topic=%2Fcom.vmware.vcloud.api.doc_51%2FGUID-67949F56-5AF3-4B70-8B8B-07E18849A598.html

# Otherwise I have to use the Flash client plugin and it's nasty.  This script will eventually be useful
# to other people at RAL, but for now I just want to upload the test image: centos6-stemcell.ovf

# Note that this does not power on the VM.  It uploads it to the catalogue to make a template.

# Note on connections made to the API:
#  1 = Check version and get login URL
#  2 = Log in
#  3 = Find VDC
#  4 = Get upload URL
#  5 = Init upload (by sending uploadVappTemplate)
#  6 = Put OVF (to URL from template)

import sys
import pycurl
from io import BytesIO # This needs Py3!
from traceback import print_exc
# import xml.etree.ElementTree as ET
import lxml.etree as ET
from getpass import getpass
from itertools import *
from time import sleep, time

# Ignore SIGPIPE, as per PycURL docs
try:
    import signal
    from signal import SIGPIPE, SIG_IGN
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
except ImportError:
    pass

# Password manager helper, using the keyring module
def get_the_password(url, org, user):

    kp = None
    try :
        import keyring
        kp = keyring.get_password(url + " " + org, user)
    except :
        pass

    if kp is not None :
        return kp

    np = getpass("Enter password for %s@%s: " % (user, org))

    try :
        keyring.set_password(url + " " + org, user, np)
    except :
        pass

    return np

def clear_the_password(url, org, user):

    try :
        import keyring
        keyring.delete_password(url + " " + org, user)
    except :
        pass


# Globals:

ovf = 'centos6-stemcell'
ovf_file = ovf + '.ovf'
ovf_description = "Test upload by uploader.py"

#Changed this to the EOS URL, when I can log in again.
# sess_user = 'tbooth'
# sess_org = 'un-managed_tenancy_test_org'
# sess_pass = get_the_password(sess_url, sess_org, sess_user)
sess_url = 'https://vcloud-test.example.com'
sess_user = 'tbooth'
sess_org = 'test_org'
sess_pass = get_the_password(sess_url, sess_org, sess_user)

_version_supported = "1.5"
_xml_ns = "http://www.vmware.com/vcloud/v%s" % _version_supported
_magic_header = "Accept:application/*+xml;version=5.5"
_auth_header = "x-vcloud-authorization"

def main() :
    # Get manifest
    manifest = make_manifest()

    #DEBUGGING XSLT
    ovf_handle = open(ovf_file, encoding="utf-8")
    print(munge_ovf_data(ovf_handle))
    sys.exit(1)

    # Init connection
    sess, orgurl = init_session()
    try:
        # POST request to start upload - this creates the VAppTemplate which is the main entity we need
        # to work with.
        print("Init upload starting at " + orgurl)
        vt = init_upload(sess, orgurl)
        # PUT the URL
        put_ovf(sess, vt)
        # Poll for further upload URLS, modify vt
        poll_for_new(sess, vt)
        # Put all the other files (.vmdk and .mf)
        # TODO - this could be implemented with a callback once I neaten up the code and make an
        # object
        put_files(sess, vt)
        #  Verify that status goes to 8
        verify_upload_finished(sess, vt)
        # Did that actually work?
        print("Finished!")
    except Exception as e:
        print("Something went wrong, eh?")
        print_exc()

    #Always disconnect.
    disconnect(sess)

def make_manifest() :
    # At some point I'd want to make this on the fly by generating SHA1
    # checksums, but for now I'll just read the contents of the .mf file
    mf = None
    try :
        mf = open(ovf + '.mf').read()
    except Exception:
        pass # TODO - something else

    return mf

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
    c.setopt(pycurl.SSL_VERIFYPEER, 0)
    c.setopt(pycurl.SSL_VERIFYHOST, 0)

    # _magic_header wards off error 406 Not Acceptable
    c.setopt(pycurl.HTTPHEADER, [_magic_header] + ( extra_headers or [] ) )

    c.setopt(pycurl.URL, url)
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

# A class just used in the function below.
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

    #To access the data just look at hc.headers directly


def _curl_perform(c, postdata = None) :
    b = BytesIO()
    c.setopt(pycurl.WRITEFUNCTION, b.write)

    h = HeaderCollector()
    c.setopt(pycurl.HEADERFUNCTION, h.append_line)

    #Extract URL just in case we need it to report an error properly.
    #url = re.search("://(.*)", c.getopt(pycurl.URL)).group(1)

    #For syncronous posting of a string.  The caller should have set
    #the method to PUT or POST and set the Content-Type header
    if postdata :
        c.setopt(pycurl.POST, 1)
        c.setopt(pycurl.POSTFIELDS, postdata.encode("UTF-8"))
        print("Posting to %s:" % c.saved_URL  )
        print(postdata)

    #print("DEBUG - about to make cURL call")
    c.perform()
    #print("DEBUG - call finished")

#     except pycurl.error, v:
#         raise xmlrpclib.ProtocolError(url, v[0], v[1], None)
    response = b.getvalue()

    response_as_xml = None
    if response.strip() :
        response_as_xml = ET.fromstring(response)

    # Get response headers as dict

    return (h.headers , response_as_xml, )

def init_session() :
    print("Starting session on %s." % sess_url)
    # Here I connect to the system as per Charlie's scripts
    # First, get the versions page from the API:
    c1 = _get_curl_handle("%s/api/versions" % sess_url)
    h1, r1 = _curl_perform(c1)

    #Validate version
    version_seen = r1.find('.//{http://www.vmware.com/vcloud/versions}Version').text
    if version_seen != _version_supported :
        raise Exception("Version seen is not " + _version_supported)

    #ET.dump(r1)
    loginurl = r1.find('.//{http://www.vmware.com/vcloud/versions}LoginUrl').text
    print("Logging in via " + loginurl)

    c2 = _get_curl_handle(loginurl, 'POST')
    #Does this work with a colon in the password??  Yes!
    c2.setopt(pycurl.USERPWD, '%s@%s:%s' % (sess_user, sess_org, sess_pass))

    h2, r2 = _curl_perform(c2)

    if(h2['_'].split()[1] == "401"):
        raise Exception("Session auth failed - probably bad username/password")
        clear_the_password(sess_url, sess_org, sess_user)
    elif(h2['_'].split()[1] != "200"):
        raise Exception("Session auth failed with unexpected status " + h2['_'])

    #print("Logged in")

    #Find the session auth header
    auth_header = "%s : %s" % (_auth_header, h2[_auth_header])

    #Extract the element that looks like:
    '''
    <Link rel="down" type="application/vnd.vmware.vcloud.org+xml"
          name="un-managed_tenancy_test_org"
          href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/6483ae7d-2307-4856-a1c9-109751545b4c"/>
    '''
    orgurl = None
    for l in r2.findall('.//{%s}Link' % _xml_ns) :
        if ( l.attrib.get('name') == sess_org and
             l.attrib.get('type') == "application/vnd.vmware.vcloud.org+xml" ) :
            orgurl = l.attrib.get('href')

    #Really this should be wrapped in an object and I should just save this in a session variable
    return ([auth_header], orgurl)

def init_upload(sess, orgurl) :
    #sess is just a session header list suitable to pass to _curl_perform
    #orgurl is the URL I need to follow to get into the menus
    #this will initiate the upload to the point where I can upload the OVF
    if not orgurl :
        raise Exception("No link provided for ORG top level menu")

    print("Now connected to %s" % orgurl)

    c3 = _get_curl_handle(orgurl, 'GET', sess)
    h3, r3 = _curl_perform(c3)

    #ET.dump(r3)

    # Here we look for the VDC link, identified by type="application/vnd.vmware.vcloud.vdc+xml"
    # For now, this looks for a single VDC, but in real life you need to pick one by name.
    vdcs = [ l for l in r3.findall('.//{%s}Link' % _xml_ns)
             if l.attrib.get('type') == 'application/vnd.vmware.vcloud.vdc+xml' ]
    if len(vdcs) != 1 :
        raise Exception("Expected to find one VDC, but found %i" % len(vdcs))

    #Now based on this href I could infer the action/uploadVAppTemplate link but I'll drill down to
    #it instead.
    #I'm not sure just now if the vdcurl is synonymous with the "target catalogue" but we shall see.
    vdcurl = vdcs[0].attrib.get('href')
    c4 = _get_curl_handle(vdcurl, 'GET', sess)
    h4, r4 = _curl_perform(c4)

    uploadlink = [ l for l in r4.findall('.//{%s}Link' % _xml_ns)
                   if l.attrib.get('type') == 'application/vnd.vmware.vcloud.uploadVAppTemplateParams+xml' ]
    if len(uploadlink) != 1 :
        raise Exception("expected to see one upload link, but found %i" % len(uploadlink))

    uploadurl = uploadlink[0].attrib.get('href')

    # Bad request on POST below could mean an upload is still running.  Can I DELETE it?
    # Or undeploy it?  Or what?  Uploading with a new name starts a new request.
    # Yes - looks like I can DELETE it.

    print("Starting upload of params XML to %s" % uploadurl)

    #So now I need to Create an "UploadVAppTemplateParams element that specifies a name for the template."
    # Call it "aatest filename"
    template_name = "aatest %s" % ovf
    uploadparams = ( '''
        <?xml version="1.0" encoding="UTF-8"?>
        <UploadVAppTemplateParams
            name="%s"
            xmlns="%s"
            manifestRequired="%s"
            xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1">
            <Description>%s</Description>
        </UploadVAppTemplateParams>
    ''' % ( template_name, _xml_ns, "false", ovf_description ) ).lstrip()

    # And POST it to the URL with the right Content-Type header
    ctheader = "Content-Type: application/vnd.vmware.vcloud.uploadVAppTemplateParams+xml"

    c5 =  _get_curl_handle(uploadurl, 'POST', sess + [ctheader])

    h5, r5 = _curl_perform(c5, uploadparams)

    # A duplicate upload, ie. same name as previous, causes a "400 Bad Request" response
    # Partial uploads don't seem expire.  Look to see if the template is there.  I could re-use it but
    # easier to flush and reload, I think.
    stat5 = h5['_'].split()[1]
    if(stat5 == "400"):
        existing_templates = list_existing_templates(sess, vdcurl)
        if template_name in existing_templates:
            remove_existing_template(sess, existing_templates[template_name])
            # This is silly as I remove it but then complain it is still there.  FIXME.

            raise Exception("POST of UploadVAppTemplateParams resulted in 400 error.\n" +
                            "Template %s already existed with URL %s" % (template_name, existing_templates[template_name]) )
        else:
            raise Exception("POST of UploadVAppTemplateParams resulted in 400 error.\n" +
                            "but there does not seem to be an existing template with that name?!?")
    elif(stat5 != "201"):
        raise Exception("POST of UploadVAppTemplateParams failed with unexpected status " + h5['_'])

    # I can discover the href of the new template
    # (eg. href="https://vcloud.example.com/api/vAppTemplate/vappTemplate-268" )
    print("New template assigned as %s" % r5.attrib.get('href'))

    #template_name = r5.attrib.get("href").split("/")[-1]

    # Now I need to find the File element which has name="*.ovf" and extract the href attribute
    # from the Link sub-element.  Got it?  There should only be one Link per File.
    # Do I actually need to check if rel="upload:default" ??
    putlinks = { f.attrib['name']:l.attrib['href']
                 for f in r5.findall(".//{%s}File" % _xml_ns)
                 for l in f if l.tag == "{%s}Link" % _xml_ns
                               and l.attrib.get('rel') == 'upload:default'
               }

    print(putlinks)

    putlink = [ href for name, href in putlinks.items() if name.endswith('.ovf') ][0]

    # Build a vt1 dict that has the relevant info in it
    return { 'ovf_put_url'   : putlink,
             'template_href' : r5.attrib.get('href'),
             'template_id'   : r5.attrib.get('id') }

def put_ovf(sess, vt) :

    # Read the entire .ovf file, which should be in UTF-8
    ovf_data = open(ovf_file, encoding="utf-8").read()

    # TODO - remove the 'goldMaster="true"' flag from the OVF.
    # Actually, I want to be able to munge OVF from VirtualBox so there is plenty to do here:
    ovf_data = munge_ovf_data(ovf_data)

    # This one is a PUT request.
    c6 = _get_curl_handle(vt['ovf_put_url'], 'PUT', sess + [ "Content-Type: text/xml" ])
    h6, r6 = _curl_perform(c6, ovf_data)

    # This time we expect a 200, but it seems a "100 Continue" is also good.
    stat6 = h6['_'].split()[1]
    if(stat6 != "200" and stat6 != "100"):
        raise Exception("PUT of OVF failed with unexpected status " + h6['_'])

    # Done, easy.

def munge_ovf_data(ovf_handle) :
    # Deploy XSLT.  Needs you to be using the lxml version of ETree as the Python builtin
    # version doesn't have XSLT.

    # Just now this turns off the goldMaster flag but ultimately I want to munge VirtualBox
    # XSLT into VMWare XSLT.

    my_xslt = '''
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1"
                xmlns:vcloud="%s">

    <xsl:output encoding="UTF-8"/>

    <!-- Standard XSLT identity transformation -->
    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
    </xsl:template>

    <!-- Specific change for goldMaster -->
    <xsl:template match="vcloud:CustomizationSection">
        <xsl:copy>
            <xsl:attribute name="goldMaster">false</xsl:attribute>
            <xsl:apply-templates select="@ovf:required|node()" />
        </xsl:copy>
    </xsl:template>
</xsl:stylesheet>
'''.lstrip() % _xml_ns;

    transform = ET.XSLT(ET.fromstring(my_xslt))

    dom = ET.parse(ovf_handle)
    newdom = transform(dom)

    return str(ET.tostring(newdom, pretty_print=True), encoding="UTF-8")

def gen_timeouts():
    #Return periods to wait for 2 minutes
    return [1,1,1,3,3,3,3,5,5,5,10,10,10,10,10,10,10,10,10,0]

def poll_for_new(sess, vt) :

    # vt.template_href can be read repeatedly to see if:
    #   ovfDescriptorUploaded attribute has a value of true
    #   the number of File elements is > 1
    # or
    #   the status attribute has a value != 0 indicates an error

    putlinks = {}
    gotem = 0
    for n in gen_timeouts():

        c7 = _get_curl_handle(vt['template_href'], 'GET', sess)
        h7, r7 = _curl_perform(c7)

        if(h7['_']).split()[1] != "200":
            raise Exception("GET of template failed with unexpected status " + h2['_'])

        # Error??
        if r7.attrib['status'] != '0' :
            for elem in (r7.findall(".//{%s}Task/*" % _xml_ns)):
                ET.dump(elem)
            raise Exception( "bad status %s" % r7.attrib['status'] )

        # This again - should probably abstract it out.  Can you tell I'm a Perl coder??
        putlinks = { f.attrib['name']: ( l.attrib['href'], int(f.attrib.get('size','-1')), int(f.attrib.get('bytesTransferred',"0")) )
                     for f in r7.findall(".//{%s}File" % _xml_ns)
                     for l in f if l.tag == "{%s}Link" % _xml_ns
                                   and l.attrib.get('rel') == 'upload:default'
                   }

        if r7.attrib['ovfDescriptorUploaded'] == "true" and len(putlinks) > 1 :
            # Could verify bytesTransferred = size for the OVF?
            print("Got descriptors ready for upload...")
            for e in r7.findall(".//{%s}File" % _xml_ns):
                ET.dump(e)
            break
        else:
            if(n):
                print("Waiting for vCloud to be ready to accept the upload.")
                sleep(n)
    else:
        raise Exception("Timeout waiting for VAppTemplate to be populated.")

    #OK, we got em.
    vt['put_links'] = putlinks

def verify_upload_finished(sess, vt):
    # This will be a bit like poll_for_new
    wait_time = 0

    for n in gen_timeouts():

        c9 = _get_curl_handle(vt['template_href'], 'GET', sess)
        h9, r9 = _curl_perform(c7)

        if(h7['_']).split()[1] != "200":
            raise Exception("GET of template failed with unexpected status " + h2['_'])

        # Wait for status to be 8
        if r9.attrib['status'] == '8' :
            break
        else:
            print("Template status is %s; waiting some more." % r9.attrib['status'])
            sleep(n)
            wait_time = wait_time + n
    else:
        # Ran to end of loop
        for elem in r7.findall(".//{%s}Task/*" % _xml_ns):
            ET.dump(elem)
        raise Exception("timeout")

def put_files(sess, vt):
    # So the vt dict has put_links = { filename : ( href, size, transferred ) }
    # and for each I need to upload a file of that size.

    # I do like this Python syntax
    for filename, ( href, size, transferred ) in vt['put_links'].items() :

        #Don't re-upload the descriptor.ovf
        if size == transferred:
            print("Skipping already transferred %s." % filename)
            continue

        # Also note the VMDK in the .OVA archive had a .000000000 extension which I needed to remove.
        # I'd imagine that for large disks this might be split to multiple files and I should combine
        # them for upload.  Anyway, no matter.

        print("Uploading %s" % filename)

        # Not sure if we need the session header here?  Or a content type header?
        # We do need the content-length header, but I think this is best set implicitly
        c8 = _get_curl_handle(href, 'PUT', sess )

        #Set Content-Length
        if(size < 0):
            #TODO - this should be supplied by VC, or else calculate size of file
            raise Exception("File size unknown for %s." % filename)
        c8.setopt(pycurl.INFILESIZE_LARGE, size)

        #I think this is how you stream upload from a file.
        c8.setopt(pycurl.UPLOAD, 1)
        c8.setopt(pycurl.READFUNCTION, open(filename, "br").read)

        # The VMWare doc advises that I should start the upload in a separate thread then
        # poll for how many bytes have been uploaded.  Or can I just get CURL to tell me?
        # http://pycurl.sourceforge.net/doc/callbacks.html suggests I can
        c8.setopt(pycurl.NOPROGRESS, 0)
        c8.setopt(pycurl.PROGRESSFUNCTION, my_progress)

        # Note that XFERINFOFUNCTION is supposedly the newer way to do this.  Maybe worth
        # a try later.

        print("Transferring %s" % filename)

        h8, r8 = _curl_perform(c8)

        #Need at least a newline after last print
        print(" - DONE")


def my_progress(download_t, download_d, upload_t, upload_d):

    #So libCURL will decide when I should report progress.  I just need to print a
    #progress report.  Not sure how frequently this is called??
    if upload_t == 0:
        # Could print "initilising upload" once?
        #print("%i of  %i bytes transferred" % (upload_d, upload_t), flush=True)
        pass
    else:
        print("\r  %i of  %i bytes transferred (%.1f%%)" %
                  (upload_d,
                          upload_t,             upload_d / upload_t * 100 ),
              end='', flush=True)

    return 0

# TODO - I want to be able to abort partial uploads.  How?  I think I tried deleting the OVF,
# and that didn't work, but there are various options.  Really I'd like to be able to list uploads
# in progress and abort them.
# In the XML retrieved from r4 the entries in the catalogue show up as "ResourceEntity" nodes.
# In the vCloud Director they show up under vApp Templates in Catalogs->My Organisation's Catalogs
# and the status is "Failed to create".  I assume I can find this by fetching and inspecting each
# template (for status = -1) but I won't bother for now, see below.
def list_existing_templates(sess, vdcurl):
    #First retrieve the VDC XML to get the ResourceEntity list
    c101 = _get_curl_handle(vdcurl, 'GET', sess)
    h101, r101 = _curl_perform(c101)

    #ET.dump(r101)
    resource_entities = [ l for l in r101.findall('.//{%s}ResourceEntity' % _xml_ns)
                          if l.attrib.get('type') == "application/vnd.vmware.vcloud.vAppTemplate+xml" ]

    return { re.attrib['name'] : re.attrib['href'] for re in resource_entities }

# How to remove a template?  As a first try, just retrieve the XML and look at it...
# It looks like the rel="remove" link should be the same as the template link, so I should
# just be able to delete it.  Yes, that works for status "-1" (= no OVF) but what about status 0??
def remove_existing_template(sess, template_url):
    c102 = _get_curl_handle(template_url, 'GET', sess)
    h102, r102 = _curl_perform(c102)

    #ET.dump(r102)
    if r102.attrib['status'] == '-1':
        c103 = _get_curl_handle(template_url, 'DELETE', sess)
        h103, _ = _curl_perform(c103)

        #Look for "HTTP/1.1 204 No Content" in the result
        if h103['_'] == "HTTP/1.1 202 Accepted" :
            print("Deleted %s OK" % template_url)
            return True
        else :
            print("Delete failed: %s" %  h103['_'])
    elif r102.attrib['status'] == '0':
        # In status 0 the XML contains a rel="task:cancel" link, so I guess I need to prod that to cancel
        # the upload.  As far as I can see, this aborts the whole thing and I don't need the subsequent DELETE
        cancel_link = [ l for l in r102.findall('.//{%s}Link' % _xml_ns)
                        if l.attrib.get('rel') == "task:cancel" ][0].attrib['href']

        c104 = _get_curl_handle(cancel_link, 'POST', sess)
        h104, r104 = _curl_perform(c104)

        print("Attempting to abort a partial upload:")
        if h104['_'] == "HTTP/1.1 204 No Content" :
            print("Yes, that seemed to work.  Will take about 10 seconds to actually abort.")
            sleep(5)
        else:
            print("Cancel failed: %s" % h104['_'])
    else:
        print("Will not delete template in status %s." % r102.attrib['status'])

    return False



def disconnect(sess) :

    c1 = _get_curl_handle("%s/api/session" % sess_url, 'DELETE', sess)

    h1, _ = _curl_perform(c1)

    #Look for "HTTP/1.1 204 No Content" in the result
    if h1['_'] == "HTTP/1.1 204 No Content" :
        print("Disconnected OK")
    else :
        print("Disconnect failed")

def foo():
    for n in chain([1,1,1,3,3,3,3,5,5,5], repeat(10,9)):
        sleep(n)
        print(n)

# def put_files() :
    # This is the tricky bit.  With libcurl, how do I monitor and display progress?
    # 1) Do an async upload with libcurl?
    # 2) Upload in another thread and monitor progress by asking VMWare?
    # 3) Use chunked upload?
    # See http://curl.haxx.se/libcurl/c/libcurl-multi.html
#     pass

if __name__ == '__main__':
    main()
