#!/usr/bin/env python3
# encoding: UTF-8

import sys
import xml.etree.ElementTree as ET
from vCloudOVFMunger import munge_ovf_tree

# Simple script that will munge stdin and spit result to stdout.
# Args (machine name, network) will be passed directly to munge_ovf_tree

# TODO - is stdin automatically regarded at utf-8?
dom = ET.parse(sys.stdin).getroot()

munge_ovf_tree(dom, *sys.argv[1:])

print(str(ET.tostring(dom), encoding="UTF-8"))
