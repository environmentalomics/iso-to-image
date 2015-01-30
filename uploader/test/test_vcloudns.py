#!/usr/bin/env python3
# encoding: UTF-8

import unittest
import re
#Use the default ETree, even though the LXML one is better.
import xml.etree.ElementTree as ET
from vCloudNS import ns

class NSTests(unittest.TestCase):

    def setUp(self):
        self.somexml = ET.XML(
"""<vc:foo xmlns="http://schemas.dmtf.org/ovf/envelope/1"
           xmlns:vc="http://www.vmware.com/vcloud/v1.5"
           xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1"
           xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData"
           xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData"
           xmlns:vbox="http://www.virtualbox.org/ovf/machine">
    <bar><rasd:baz vbox:eep="1234" /><rasd:baz vbox:eep="5678" />
    </bar>
    </vc:foo>""")

    def test_ns_1(self):
        #Just make sure that loading the module lets me see an example
        #namespace.
        self.assertEqual(ns.vc, "http://www.vmware.com/vcloud/v1.5")

    def test_ns_2(self):
        #And also ensure that I can access the info both ways
        self.assertEqual(ns.vc, ns['vc'])

    def test_ns_3(self):
        #Ensure that I can use the namespaces to navigate my sample XML doc
        #(not really a unit test but hey)
#         ET.dump(self.somexml)
        self.assertEqual(len(self.somexml.findall("{%(ovf)s}bar/{%(rasd)s}baz" % ns)), 2)
