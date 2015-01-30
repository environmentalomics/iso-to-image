#!/usr/bin/env python3
# I have now got packer to make .ova files from .iso files.
# And I think I can get the right VMWare tools installed onto the images with the
# right options set.  Good.

# After disabling IPV6 and disabling password-based log-in and re-jigging the .ovf file
# I should be able to transmit the image to VCloud using this procedure:

# pubs.vmware.com/vcd-51/index.jsp?topic=%2Fcom.vmware.vcloud.api.doc_51%2FGUID-67949F56-5AF3-4B70-8B8B-07E18849A598.html

# Otherwise I have to use the Flash client plugin and it's nasty.  This script will eventually be useful
# to other people at RAL, but for now I just want to upload the test image: centos6-stemcell.ovf or my
# minimal Ubuntu OVF.

# Note that this does not power on the VM.  It uploads it to the catalogue to make a template.  If the
# template is deployed by CloudHands I get a final "activation" hook script that I can run.

# Note on connections made to the API:
#  1 = Check version and get login URL
#  2 = Log in
#  3 = Find VDC
#  4 = Get upload URL
#  5 = Init upload (by sending uploadVappTemplate)
#  6 = Put OVF (to URL from template)

# This is v2 with the networking stuff split off into vCloudcURL.py which I've tried to
# write in such a way that I could make a non-cURL implementation.

# If I want to deal with .ova files directly then I'll need a little re-architecting as we need to
# upload the files as they are found in the OVA tarball not the order we see them in the XML.

import sys
import re
from io import BytesIO # This needs Py3!
from traceback import print_exc
import xml.etree.ElementTree as ET
# import lxml.etree as ET
from getpass import getpass
from itertools import *
from time import sleep, time
import argparse

from vCloudcURL import NoConnectionException, vCloudException, vCloudcURL as vCloud
from vCloudNS import ns

import logging
L = logging.getLogger(__name__)
log_level = logging.DEBUG

# Password manager helper, using the keyring module.  Not sure where this belongs - here or in a helper
# module?
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

ovf_name = 'centos6-stemcell' # This always gets overridden anyway.
ovf_file = ovf_name + '.ovf'
ovf_description = "Test upload by uploader2.py"
template_prefix = 'test'
template_name = ''

#Changed this to the EOS URL, when I can log in again.
sess_url = 'https://vcloud.ceda.ac.uk'
sess_user = 'tbooth'
sess_org = 'eoscloud-U'
# Don't try to invoke the password helper yet - only if main() actually runs.
sess_pass = None

# Really, no, this should not be hard-coded!!
network_name = 'eoscloud-U-NERCvSE'

# A flag
noop_munge = False

# sess_url = 'https://vjasmin-vcloud-test.jc.rl.ac.uk'
# sess_user = 'tbooth'
# sess_org = 'un-managed_tenancy_test_org'
# sess_pass = get_the_password(sess_url, sess_org, sess_user)

_version_supported = "1.5"
# Now defined in vCloudNS module -
#_xml_ns = "http://www.vmware.com/vcloud/v1.5"

def main() :

    # TODO - process command-line args.
    process_args()

    # Get manifest file.
    manifest = make_manifest()

    # Init connection
    sess, orgurl = init_session()
    try:
        # POST request to start upload - this creates the VAppTemplate which is the main entity we need
        # to work with.
        L.info("Init upload starting at " + orgurl)
        vt = init_upload(sess, orgurl)
        # PUT the URL
        put_ovf(sess, vt)
        # Poll for further upload URLS and upload them
        poll_for_uploads(sess, vt)
        upload_files(sess, vt)
        #  Verify that status goes to 8
        verify_upload_finished(sess, vt)
        # Did that actually work?
        L.info("Finished!")
    except Exception as e:
        print("Something went wrong, eh?")
        print_exc()

    #Always disconnect.
    sess.disconnect()

def make_manifest() :
    # At some point I'd want to make this on the fly by generating SHA1
    # checksums, but for now I'll just read the contents of the .mf file
    mf = None
    try :
        mf = open(ovf_name + '.mf').read()
    except Exception:
        pass # TODO - something else

    return mf

def process_args() :

    #Stuffing the args into globals seems simplest.
    global ovf_name, ovf_file, ovf_description, template_prefix, template_name
    global sess_url, sess_user, sess_org, sess_pass
    global noop_munge

    parser = argparse.ArgumentParser(description='OVF file uploader')
#     parser.add_argument('ovf_name', metavar='N', type=str, nargs='1', help='OVF to upload')
    parser.add_argument('ovf_name', metavar='OVF_NAME', type=str, help='OVF to upload')
    parser.add_argument('--sess_url', help='default: %s' % sess_url)
    parser.add_argument('--sess_org', help='default: %s' % sess_org)
    parser.add_argument('--sess_user', help='default: %s' % sess_user)
    parser.add_argument('--sess_pass', help='default: try keyring or else prompt')

#     parser.add_argument('--ovf_name', help='default: %s' % ovf_name)
    parser.add_argument('--ovf_file', help='default: <ovf_name>.ovf')
    parser.add_argument('--ovf_description', help='default: %s' % ovf_description)
    parser.add_argument('--prefix', help='default: %s' % template_prefix)

    parser.add_argument('--munge', help='default: %s' % str(not noop_munge), action='store_true')

    args = parser.parse_args()

    #OVF name must be supplied.  I'll guess if it is really ovf_name or ovf_file that
    #has been given here.
    if args.ovf_name.lower().endswith('.ovf'):
        ovf_file = args.ovf_name
        ovf_name = args.ovf_name[:-4]
    else:
        ovf_name = args.ovf_name
        ovf_file = args.ovf_file or ovf_name + '.ovf'

    #FIXME - this is a silly restriction.
    if '/' in ovf_file:
        raise Exception("OVF file needs to be in the current working directory.")

    if args.sess_url : sess_url = args.sess_url
    if args.sess_org : sess_org = args.sess_org
    if args.sess_user :
        sess_user = args.sess_user
        sess_pass = None
    if args.sess_pass : sess_pass = args.sess_pass

    if args.ovf_description : ovf_description = args.ovf_description
    if args.prefix : template_prefix = args.prefix

    noop_munge = True
    if args.munge : noop_munge = False

    template_name = ("%s-%s" % (template_prefix, ovf_name)).lstrip('-')


def init_session() :

    session = vCloud(sess_url, _version_supported)

    _sess_pass = sess_pass
    if _sess_pass is None:
        _sess_pass = get_the_password(sess_url, sess_org, sess_user)

    try:
        top_menu = session.connect(sess_org, sess_user, _sess_pass)
    except NoConnectionException:
        #Assume bad password here.
        clear_the_password(self.sess_url, self.sess_org, self.sess_user)

    #Extract the element that looks like:
    '''
    <Link rel="down" type="application/vnd.vmware.vcloud.org+xml"
          name="un-managed_tenancy_test_org"
          href="https://vjasmin-vcloud-test.jc.rl.ac.uk/api/org/6483ae7d-2307-4856-a1c9-109751545b4c"/>
    '''
    orgurl = None
    for l in top_menu.findall('.//{%s}Link' % ns.vc) :
        if ( l.attrib.get('name') == sess_org and
             l.attrib.get('type') == "application/vnd.vmware.vcloud.org+xml" ) :
            orgurl = l.attrib.get('href')

    if not orgurl :
        session.disconnect()
        ET.dump(top_menu)
        raise Exception("No link provided for %s top level menu" % sess_org)

    #Return both the connection handle and the starting URL.
    return (session, orgurl)

def init_upload(sess, orgurl) :
    #sess is a logged-in session
    #orgurl is the URL I need to follow to get into the menus
    #this will initiate the upload to the point where I can upload the OVF

    L.info("Initiating upload at %s" % orgurl)

    r3 = sess.httpGET(orgurl)

    #ET.dump(r3)

    # Here we look for the VDC link, identified by type="application/vnd.vmware.vcloud.vdc+xml"
    # For now, this looks for a single VDC, but in real life you need to pick one by name.
    vdcs = [ l for l in r3.findall('.//{%s}Link' % ns.vc)
             if l.attrib.get('type') == 'application/vnd.vmware.vcloud.vdc+xml' ]
    if len(vdcs) != 1 :
        raise Exception("Expected to find one VDC, but found %i" % len(vdcs))

    #Now based on this href I could infer the action/uploadVAppTemplate link but I'll drill down to
    #it instead.
    #I'm not sure just now if the vdcurl is synonymous with the "target catalogue" but we shall see.
    vdcurl = vdcs[0].attrib.get('href')

    r4 = sess.httpGET(vdcurl)

    uploadlink = [ l for l in r4.findall('.//{%s}Link' % ns.vc)
                   if l.attrib.get('type') == 'application/vnd.vmware.vcloud.uploadVAppTemplateParams+xml' ]
    if len(uploadlink) != 1 :
        ET.dump(r4)
        raise Exception("expected to see one upload link, but found %i" % len(uploadlink))

    uploadurl = uploadlink[0].attrib.get('href')

    # Bad request on POST below could mean an upload is still running.  Can I DELETE it?
    # Or undeploy it?  Or what?  Uploading with a new name starts a new request.
    # Yes - looks like I can DELETE it.

    print("Starting upload of params XML to %s" % uploadurl)

    #So now I need to Create an "UploadVAppTemplateParams element that specifies a name for the template."
    # Call it "aatest filename"
    uploadparams = ( '''
        <?xml version="1.0" encoding="UTF-8"?>
        <UploadVAppTemplateParams
            name="%s"
            xmlns="%s"
            manifestRequired="%s"
            xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1">
            <Description>%s</Description>
        </UploadVAppTemplateParams>
    ''' % ( template_name, ns.vc, "false", ovf_description ) ).lstrip()

    # And POST it to the URL with the right Content-Type header
    ctype = "application/vnd.vmware.vcloud.uploadVAppTemplateParams+xml"

    r5 = None
    scrub_existing = False
    try:
        r5 = sess.httpPOST(uploadurl, ctype, uploadparams)
    except vCloudException as e:
        scrub_existing = True
        if e.code != 400:
            #No, I can't handle this.
            raise Exception("POST of UploadVAppTemplateParams failed with unexpected status %i" % e.code)

    #This is ugly.  Catch the exception, then climb out of the handler, then generate another
    #exception.  What should I really be doing here?
    if scrub_existing:
        # A duplicate upload, ie. same name as previous, causes a "400 Bad Request" response
        # These partial uploads don't expire.  Look to see if the template is there.  I could re-use it but
        # easier to flush it and reload, I think.
        existing_templates = list_existing_templates(sess, vdcurl)
        if template_name in existing_templates:
            remove_existing_template(sess, existing_templates[template_name])
            # This is silly as I remove it but then quit anyway.  But I don't want to retry until the
            # template is actually gone.

            raise Exception(("Template %s already existed with URL %s.\n" +
                             "It has been removed, but you need to wait a few seconds before trying again.")
                                % (template_name, existing_templates[template_name]) )
        else:
            raise Exception("POST of UploadVAppTemplateParams resulted in 400 error.\n" +
                            "but there does not seem to be an existing template with that name?!?")

    # I can discover the href of the new template
    # (eg. href="https://vcloud.example.com/api/vAppTemplate/vappTemplate-268" )
    print("New template assigned as %s" % r5.attrib.get('href'))

    #template_name = r5.attrib.get("href").split("/")[-1]

    # Now I need to find the File element which has name="*.ovf" and extract the href attribute
    # from the Link sub-element.  Got it?  There should only be one Link per File.
    # Do I actually need to check if rel="upload:default" ??
    putlinks = { f.attrib['name']:l.attrib['href']
                 for f in r5.findall(".//{%s}File" % ns.vc)
                 for l in f if l.tag == "{%s}Link" % ns.vc
                               and l.attrib.get('rel') == 'upload:default'
               }

    L.info("Found these links in the VT:\n%r" % putlinks)

    putlink = [ href for name, href in putlinks.items() if name.endswith('.ovf') ][0]

    # Build a vt1 dict that has the relevant info in it
    return { 'ovf_put_url'   : putlink,
             'template_href' : r5.attrib.get('href'),
             'template_id'   : r5.attrib.get('id') }

def put_ovf(sess, vt) :
    # Remove the 'goldMaster="true"' flag from the OVF.
    # Actually, I want to be able to munge OVF from VirtualBox so there is plenty to do here:
    ovf_data = munge_ovf_data(ovf_file, template_name, network_name)

    # Put the XML data
    sess.httpPUT(vt['ovf_put_url'], "text/xml", ovf_data)
    # Done, easy.

#FIXME - if we are not munging this shouldn't be called at all.
def munge_ovf_data(ovf_file, *args, **kwargs) :

    global noop_munge

    # Read the entire .ovf file, which should be in UTF-8, and return a munged serialised
    # version.
    ovf_handle = open(ovf_file, encoding="utf-8")
    dom = ET.parse(ovf_handle).getroot()
    ovf_handle.close()

    # Munge can be bypassed but we still want to parse the XML to check it
    if not noop_munge:
        from vCloudOVFMunger import munge_ovf_tree
        munge_ovf_tree(dom, *args, **kwargs)

    return str(ET.tostring(dom), encoding="UTF-8")

def gen_timeouts():
    #Return periods to wait for 2 minutes
    return [1,1,1,3,3,3,3,5,5,5,10,10,10,10,10,10,10,10,10,0]

def poll_for_uploads(sess, vt) :

    # vt.template_href can be read repeatedly to see if:
    #   ovfDescriptorUploaded attribute has a value of true
    #   the number of File elements is > 1
    # or
    #   the status attribute has a value != 0 indicates an error

    putlinks = {}
    gotem = 0
    for n in gen_timeouts():

        r7 = sess.httpGET(vt['template_href'])

        # Error??
        if r7.attrib['status'] != '0' :
            for elem in (r7.findall(".//{%s}Task/*" % ns.vc)):
                #FIXME - don't dump directly to STDOUT
                ET.dump(elem)
            raise Exception( "bad status in VAppTemplate %s" % r7.attrib['status'] )

        # This again - should probably abstract it out.  Can you tell I'm a Perl coder??
        putlinks = { f.attrib['name']: ( l.attrib['href'], int(f.attrib.get('size','-1')), int(f.attrib.get('bytesTransferred',"0")) )
                     for f in r7.findall(".//{%s}File" % ns.vc)
                     for l in f if l.tag == "{%s}Link" % ns.vc
                                   and l.attrib.get('rel') == 'upload:default'
                   }

        if r7.attrib['ovfDescriptorUploaded'] == "true" and len(putlinks) > 1 :
            # Could verify bytesTransferred = size for the OVF but there's no point
            L.debug("Got descriptors ready for upload...")
            for e in r7.findall(".//{%s}File" % ns.vc):
                L.debug(ET.tostring(e,encoding="unicode"))
            break
        else:
            if(n):
                L.debug("Waiting for vCloud to be ready to accept the upload.")
                sleep(n)
    else:
        raise Exception("Timeout waiting for VAppTemplate to be populated.")

    #OK, we got em.
    vt['put_links'] = putlinks

def verify_upload_finished(sess, vt):
    # This will be a bit like poll_for_new
    wait_time = 0

    for n in gen_timeouts():

        r9 = sess.httpGET(vt['template_href'])

        # Wait for status to be 8
        if r9.attrib['status'] == '8' :
            break
        else:
            L.debug("Template status is %s; waiting some more." % r9.attrib['status'])
            sleep(n)
            wait_time = wait_time + n
    else:
        # Ran to end of loop
        for elem in r9.findall(".//{%s}Task/*" % ns.vc):
            ET.dump(elem)
        raise Exception("timeout")

def upload_files(sess, vt):
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
        # them for upload.  Anyway, will worry about that later.

        L.info("Uploading %s" % filename)

        #Upload and show progress on the terminal.  TODO - if not in a terminal log to the log.
        sess.httpUPLOAD(href, filename, size, sys.stdout)


# Listing and aborting partial uploads...
# In the XML retrieved from r4 the entries in the catalogue show up as "ResourceEntity" nodes.
# In the vCloud Director they show up under vApp Templates in Catalogs->My Organisation's Catalogs
# and the status is "Failed to create".
def list_existing_templates(sess, vdcurl):
    #First retrieve the VDC XML to get the ResourceEntity list
    r101 = sess.httpGET(vdcurl)

    #ET.dump(r101)
    resource_entities = [ l for l in r101.findall('.//{%s}ResourceEntity' % ns.vc)
                          if l.attrib.get('type') == "application/vnd.vmware.vcloud.vAppTemplate+xml" ]

    return { re.attrib['name'] : re.attrib['href'] for re in resource_entities }

# How to remove a template?  Looking at the XML,
# it looks like the rel="remove" link should be the same as the template link, so I should
# just be able to delete it.  Yes, that works for status "-1" (= no OVF) but what about status 0??
def remove_existing_template(sess, template_url):

    r102 = sess.httpGET(template_url)

    #ET.dump(r102)
    if r102.attrib['status'] == '-1':
        try:
            sess.httpDELETE(template_url)
            L.info("Deleted %s OK" % template_url)
        except vCloudException as e:
            L.warn("Delete failed: %i" %  e.code)

    elif r102.attrib['status'] == '0':
        # In status 0 the XML contains a rel="task:cancel" link, so I need to prod that to cancel
        # the upload.  As far as I can see, this aborts the whole thing and I don't need the subsequent DELETE
        cancel_link = [ l for l in r102.findall('.//{%s}Link' % ns.vc)
                        if l.attrib.get('rel') == "task:cancel" ][0].attrib['href']

        L.info("Attempting to abort a partial upload:")
        try:
            sess.httpPOST(cancel_link)
            L.info("Yes, that seemed to work.  Will take about 10 seconds to actually abort.")
            sleep(5)
        except vCloudException as e:
            print("Cancel failed: %s" % e)
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
    logging.basicConfig(format="%(message)s", level=log_level)
    main()
