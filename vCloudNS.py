#!/usr/bin/env python3

# This module just holds a convenience list of XML namespace mappings.

# Here is a ham-fisted way of getting an object where you can read values as
# ns.foo or ns['foo']

class ns(dict):
    ovf  = "http://schemas.dmtf.org/ovf/envelope/1"
    rasd = "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData"
    vssd = "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData"
    xsi  = "http://www.w3.org/2001/XMLSchema-instance"
    vbox = "http://www.virtualbox.org/ovf/machine"
    vc   = "http://www.vmware.com/vcloud/v1.5"
    vmw  = "http://www.vmware.com/schema/ovf"

    def __init__(self):
        for k,v in self.__class__.__dict__.items():
            if k.startswith('_') : continue
            self[k] = v
            self.__dict__[k] = v

ns = ns()

if __name__ == '__main__':
    import pprint
    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(dict(ns))
