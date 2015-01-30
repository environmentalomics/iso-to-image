#!/usr/bin/env python3
# encoding: UTF-8

import unittest
from vCloudOVFMunger import sanitise_machine_name

# Test my basic string sanitiser.  This needs no setup, files, or network stuff.

# python -m unittest test.test_sanitise_machine_name

class XMLTests(unittest.TestCase):

    def setUp(self):
        self.alltests = [
    'same-string'           ,'same-string',
    'lOWER cASE'            ,'lower-case',
    'L0@d$@  jµnk'          ,'l0-d-j-nk',
    '   trim my e\nds \n\n' ,'trim-my-e-ds'
    ]

    def tearDown(self):
        pass

    #Before Python 3.4, each test needs a separate function, so I need
    #to do this long-hand.
    def test_santise_0(self):
        self._t(0)
    def test_santise_1(self):
        self._t(1)
    def test_santise_2(self):
        self._t(2)
    def test_santise_3(self):
        self._t(3)

    def _t(self, idx):

        fromstr = self.alltests[idx * 2]
        tostr = self.alltests[idx * 2 + 1]
        self.assertEqual(sanitise_machine_name(fromstr), tostr)

if __name__ == '__main__':
        unittest.main()
