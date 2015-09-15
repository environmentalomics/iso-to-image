#!python3
import sys
import re
import xml.etree.ElementTree as ET

from vCloudNS import ns

""" When I started this, I was sure my easiest approach would be to take the OVF from
    VirtualBox and munge it into somethign that VCloud would like.
    Now I think I should have started with a VCloud template and just bunged
    the disk info into it.  Oh well.
"""

def munge_ovf_tree(dom, set_ovf_name = None, set_network_name = None) :

    # Sanity check the XML contains 1 VirtualSystem tag, though of course we have no hope of
    # fully validating the input file.
    if len( dom.findall('.//{%(ovf)s}VirtualSystem' % ns) ) != 1 :
        raise Exception("Did not find a singleton VirtualSystem element as expected when munging the XML.")

    # If there is no CustomizationSection then add one after the ovf:NetworkSection
    nsect_index = [i for i, j in enumerate(dom) if j.tag == "{%(ovf)s}NetworkSection" % ns][0]
    if not dom.findall('.//{%(vc)s}CustomizationSection' % ns):
        csect = ET.Element('{%(vc)s}CustomizationSection' % ns)
        dom.insert(nsect_index + 1, csect)
        csect.set('goldMaster', 'false')
        csect.set("{%(ovf)s}required" % ns, 'false')
        ET.SubElement(csect, "{%(ovf)s}Info" % ns).text = 'VApp template customization section'
        ET.SubElement(csect, "{%(vc)s}CustomizeOnInstantiate" % ns).text = 'true'
        csect.text = "\n"
        csect.tail = "\n"

    # Seems we might want this - VCloud-specific settings
    # But really CloudHands should sort all this out
    # This needs to come right after the CustomizationSection
    if set_network_name:
        if not dom.findall(".//{%(vc)s}NetworkConfigSection" % ns):
            csect_index = [i for i, j in enumerate(dom) if j.tag == "{%(vc)s}CustomizationSection" % ns][0]
            ncsect = ET.Element("{%(vc)s}NetworkConfigSection" % ns)
            dom.insert(csect_index + 1, ncsect)
            ncsect.set("{%(ovf)s}required" % ns, 'false')
            ET.SubElement(ncsect, "{%(ovf)s}Info" % ns).text = 'The configuration parameters for logical networks'
            ncsect_nc = ET.SubElement(ncsect, "{%(vc)s}NetworkConfig" % ns)
            ncsect_nc.set("networkName", set_network_name)
            ncsect_nc_conf = ET.SubElement(ncsect_nc, "{%(vc)s}Configuration" % ns)
            ncsect_nc_conf_parent = ET.SubElement(ncsect_nc_conf, "{%(vc)s}ParentNetwork" % ns)
            ncsect_nc_conf_parent.set('name', set_network_name)
            ncsect_nc_conf_parent.set('href', '')
            ET.SubElement(ncsect_nc_conf, "{%(vc)s}FenceMode" % ns).text = 'bridged'
            ET.SubElement(ncsect_nc_conf, "{%(vc)s}RetainNetInfoAcrossDeployments" % ns).text = 'false'

            ET.SubElement(ncsect_nc, "{%(vc)s}IsDeployed" % ns).text = 'false'

    # In any case clear the goldMaster flag
    for elem in dom.findall('.//{%(vc)s}CustomizationSection' % ns):
        if 'goldMaster' in elem.keys():
            elem.set('goldMaster', 'false')

    # And add the vcloud:GuestCustomizationSection
    for vs in dom.findall(".//{%(ovf)s}VirtualSystem" % ns):
        if not vs.findall(".//{%(vc)s}GuestCustomizationSection" % ns) :
            gsect = ET.SubElement(vs, '{%(vc)s}GuestCustomizationSection' % ns)
            gsect.set("{%(ovf)s}required" % ns, 'false')
            ET.SubElement(gsect, "{%(ovf)s}Info" % ns).text = 'Specifies Guest OS Customization Settings'
            ET.SubElement(gsect, "{%(vc)s}Enabled" % ns).text = 'true'
            ET.SubElement(gsect, "{%(vc)s}ChangeSid" % ns).text = 'false'
            ET.SubElement(gsect, "{%(vc)s}JoinDomainEnabled" % ns).text = 'false'
            ET.SubElement(gsect, "{%(vc)s}UseOrgSettings" % ns).text = 'false'
            ET.SubElement(gsect, "{%(vc)s}AdminPasswordEnabled" % ns).text = 'false'
            ET.SubElement(gsect, "{%(vc)s}AdminPasswordAuto" % ns).text = 'false'
            ET.SubElement(gsect, "{%(vc)s}ResetPasswordRequired" % ns).text = 'false'
            ET.SubElement(gsect, "{%(vc)s}CustomizationScript" % ns).text = \
                    '#!/bin/sh\ncd /etc/ESXCustomisation && ./main.sh "$@" ; [ 69 != $? ]\n'
            # This gets overwritten later.
            ET.SubElement(gsect, "{%(vc)s}ComputerName" % ns).text = 'innominatus'


    # To be able to delete nodes, I need to be able to match Elements to parents
    # Maybe XSLT was neater after all??
    def get_parents(atree):
        tree_parents={atree:atree}
        stack = [atree]
        while stack:
            parent = stack.pop()
            for e in parent:
                stack.append(e)
                tree_parents[e] = parent
        #DEBUG
#         for e in atree.iter():
#             print("%s -> %s" % (tree_parents[e].tag, e.tag))

        return tree_parents

    tps = get_parents(dom)

    # Set the operating system the way VMWare likes
    for elem in dom.findall("{%(ovf)s}VirtualSystem/{%(ovf)s}OperatingSystemSection" % ns):
        if elem.get("{%(ovf)s}id" % ns, "") == "94":
            elem.set("{%(vmw)s}osType" % ns, "ubuntu64Guest")

    # Force the VirtualSystemType to vmx-10
    for elem in dom.findall('{%(ovf)s}VirtualSystem//{%(vssd)s}VirtualSystemType' % ns):
            elem.text = 'vmx-10'

    # Prune out the whole vbox:Machine section
    for elem in dom.findall('.//{%(vbox)s}Machine' % ns):
        tps[elem].remove(elem)

    # Switch any VirtualHardwareSection/Item/rasd:ResourceType that is 10 (network card) to SubType VMXNET3
    for elem in dom.findall('.//{%(ovf)s}VirtualHardwareSection/{%(ovf)s}Item/{%(rasd)s}ResourceType' % ns):
            if elem.findtext('.') == '10':
                subtypenode = tps[elem].find('{%(rasd)s}ResourceSubType' % ns)
                if subtypenode is not None:
                    subtypenode.text = 'VMXNET3'
                else:
                    #This needs to insert the value before the type, but that's tricky
                    #to do with ET.
                    parent_node = tps[elem]
                    parent_node.remove(elem)
                    subtypenode = ET.SubElement(parent_node,'{%(rasd)s}ResourceSubType' % ns)
                    subtypenode.text = 'VMXNET3'
                    elem = ET.SubElement(parent_node,'{%(rasd)s}ResourceType' % ns)
                    elem.text = '10'

    # Remove soundcards; we need them not
    for elem in dom.findall('.//{%(ovf)s}VirtualHardwareSection/{%(ovf)s}Item/{%(rasd)s}ElementName' % ns):
        if elem.findtext('.') == 'sound':
            # Remove the parent of elem
            tps[tps[elem]].remove(tps[elem])

    # Ensure that memory size is specified the way VMWare likes
    for elem in dom.findall('.//{%(ovf)s}VirtualHardwareSection/{%(ovf)s}Item/{%(rasd)s}AllocationUnits' % ns):
        if elem.findtext('.') == 'MegaBytes':
            elem.text = 'byte * 2^20'

    # Seems that for VMDK files produced by VirtualBox I need to round the capacity up to the nearest 2^20 bytes.
    for elem in dom.findall(".//{%(ovf)s}Disk" % ns):
        if elem.get("{%(ovf)s}capacityAllocationUnits" % ns, 'Bytes') == 'Bytes':
            elem.set("{%(ovf)s}capacityAllocationUnits" % ns, "byte")
            cap = int(elem.get("{%(ovf)s}capacity" % ns, "0"))
            if cap % ( 2**20 ) != 0:
                cap = cap - ( cap % ( 2**20 ) ) + ( 2**20 )
                elem.set("{%(ovf)s}capacity" % ns, str(cap))


    # ESX can't do SATA controllers, so force them to VirtualSCSI
    for elem in dom.findall('.//{%(ovf)s}VirtualHardwareSection/{%(ovf)s}Item/{%(rasd)s}ResourceType' % ns):
        if elem.findtext('.') == '20':
            elem.text = '6'
            for stelem in tps[elem].findall("{%(rasd)s}ResourceSubType" % ns):
                stelem.text = 'VirtualSCSI'
            #    stelem.text = 'lsilogic'

    # I may well not need this...
    for elem in dom.findall(".//{%(rasd)s}HostResource" % ns):
        if elem.findtext('.').startswith('/disk'):
            elem.text = 'ovf:' + elem.text

    # Machines uploaded to VCloud should take IPs from the connection pool, though I think this will be forced
    # when they are deployed in any case.
    # FIXME - vCloud only seems to like having this set to NAT, and so I'm always having to set it
    # on deployment.  Ah, no, this needs to match something in NetworkConfigSection
    if set_network_name:
        for elem in dom.findall('.//{%(ovf)s}VirtualHardwareSection/{%(ovf)s}Item/{%(rasd)s}Connection' % ns):
            if elem.findtext('.') == 'NAT':
                #elem.set("{%(vc)s}ipAddress" % ns, "192.168.3.254")
                elem.set("{%(vc)s}ipAddressingMode" % ns, "POOL")
                elem.set("{%(vc)s}primaryNetworkConnection" % ns, "true")
                elem.text = set_network_name
        for elem in dom.findall('.//{%(ovf)s}NetworkSection/{%(ovf)s}Network' % ns):
            elem.set("{%(ovf)s}name" % ns, set_network_name)

    # Set the machine name to set_ovf_name if it is supplied
    # Sanitising needed
    if set_ovf_name:
        name_clean = sanitise_machine_name(set_ovf_name)
        for elem in dom.findall(".//{%(ovf)s}VirtualSystem" % ns):
            elem.set("{%(ovf)s}id" % ns, name_clean)
        for elem in dom.findall('.//{%(ovf)s}VirtualHardwareSection/{%(ovf)s}System/{%(vssd)s}VirtualSystemIdentifier' % ns):
            elem.text = name_clean
        for elem in dom.findall('.//{%(vc)s}GuestCustomizationSection/{%(vc)s}ComputerName' % ns):
            elem.text = name_clean

    # Now add stuff to the VirtualHardwareSection to convince VCloud that the drivers are installed.
    for elem in dom.findall(".//{%(ovf)s}VirtualHardwareSection" % ns):
        #Don't add anything if there is any vmw:Config element already
        if elem.findall("./{%(vmw)s}Config" % ns) : continue
        for foo in (
            ("cpuHotAddEnabled", "true"),
            ("cpuHotRemoveEnabled", "false"),
            ("firmware", "bios"),
            ("virtualICH7MPresent", "false"),
            ("virtualSMCPresent", "false"),
            ("memoryHotAddEnabled", "true"),
            ("nestedHVEnabled", "false"),
            ("powerOpInfo.powerOffType", "soft"),
            ("powerOpInfo.resetType", "soft"),
            ("powerOpInfo.standbyAction", "checkpoint"),
            ("powerOpInfo.suspendType", "hard"),
            ("tools.afterPowerOn", "true"),
            ("tools.afterResume", "true"),
            ("tools.beforeGuestShutdown", "true"),
            ("tools.beforeGuestStandby", "true"),
            ("tools.syncTimeWithHost", "false"),
            ("tools.toolsUpgradePolicy", "manual")
        ):
            config_elem = ET.SubElement(elem, "{%(vmw)s}Config" % ns)
            config_elem.set("{%(ovf)s}required" % ns, "false")
            config_elem.set("{%(vmw)s}key" % ns, foo[0])
            config_elem.set("{%(vmw)s}value" % ns, foo[1])

    return True

def sanitise_machine_name(instr):
    #Lowercase name, switch all [^a-z0-9-] to - and trim leading and trailing
    #and double hyphens.
    # You'll get an exception if the resulting name is under 2 chars.
    return re.search('[^-].*[^-]', '-'.join(re.split('[^a-z0-9]+', instr.lower()))).group(0)

def main():
    #If called as a script, munge STDIN to STDOUT
    dom = ET.parse(sys.stdin).getroot()

    munge_ovf_tree(dom, *sys.argv[1:])

    print(str(ET.tostring(dom), encoding="UTF-8"))

if __name__ == '__main__':
    main()

