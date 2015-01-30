#!/usr/bin/env python3
# encoding: UTF-8

import unittest
import re
import lxml.etree as ET
from uploader import munge_ovf_data

# Testing the uploader is a bit tricky as most functionality involves
# interaction with a live vCloud system.  But I can test the XML munging
# bit.

# python3 -m unittest test.test_xml_munging

class XMLTests(unittest.TestCase):

    def setUp(self):
        self.files_to_test = ('centos6-stemcell', 'packer-virtualbox')
        self.data_dir = 'test'

    def tearDown(self):
        pass

    #Before Python 3.4, each test needs a separate function, so I need
    #to do this long-hand.
    def test_munge_file_0(self):
        self._test_munge(self.files_to_test[0])

    def test_munge_file_1(self):
        self._test_munge(self.files_to_test[1])

    def _test_munge(self, filename):

        dd = self.data_dir

        result1 = munge_ovf_data("%s/%s.orig.ovf" % (dd, filename), 'test-name', 'eoscloud-U-NERCvSE')
        fh2 = open("%s/%s.munged.ovf" % (dd, filename), 'r', encoding="utf-8")

        #Comparing XML string-wise is a non, starter, so we parse the result1 back into
        #a tree and also parse fh2 and compare them tree-wise.
        dom1 = ET.fromstring(result1)
        dom2 = ET.parse(fh2).getroot()

        fh2.close()

        self.assertTrue(xml_compare(dom1, dom2, print))

# Nicked from https://bitbucket.org/ianb/formencode/src/tip/formencode/doctest_xml_compare.py#cl-70
# with a couple of tweaks to suit my needs.
def xml_compare(x1, x2, reporter=None):
    if x1.tag != x2.tag:
        if reporter:
            reporter('Tags do not match: %s and %s' % (x1.tag, x2.tag))
        return False
    for name, value in x1.attrib.items():
        if x2.attrib.get(name) != value:
            if reporter:
                reporter('Attributes do not match: %s=%r, %s=%r'
                         % (name, value, name, x2.attrib.get(name)))
            return False
    for name in x2.attrib.keys():
        if name not in x1.attrib:
            if reporter:
                reporter('x2 has an attribute x1 is missing: %s'
                         % name)
            return False
    #Allow different whitespace on text if there are subelements (ie. pretty-printing)
    if not x1.getchildren() and x1.text != x2.text:
        if reporter:
            reporter('text of %r: %r != %r' % (x1.tag, x1.text, x2.text))
        return False
    if x1.getchildren() and (x1.text or "").strip() != (x2.text or "").strip():
        if reporter:
            reporter('text of %r: %r != %r' % (x1.tag, x1.text, x2.text))
        return False
    #Allow different whitespace in tails.
    if (x1.tail or "").strip() != (x2.tail or "").strip():
        if reporter:
            reporter('tail of %r: %r != %r' % (x1.tag, x1.tail, x2.tail))
        return False
    cl1 = x1.getchildren()
    cl2 = x2.getchildren()
    if len(cl1) != len(cl2):
        if reporter:
            reporter('children of %r length differs, %i != %i'
                     % (x1.tag, len(cl1), len(cl2)))
        return False
    i = 0
    for c1, c2 in zip(cl1, cl2):
        i += 1
        if not xml_compare(c1, c2, reporter=reporter):
            if reporter:
                reporter('children %i do not match: %s'
                         % (i, c1.tag))
            return False
    return True

if __name__ == '__main__':
        unittest.main()
