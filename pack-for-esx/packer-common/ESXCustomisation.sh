#!/bin/bash

# This script wants to bee hooked as the vcloud:CustomizationScript.  Later
# there will be an alternative scheme called by CloudHands but for now just
# call /etc/ESXCustomization/main.sh with the same args provided by VCloud.

set -e

me=ESXCustomization

# For now, just debug.
l=/var/log/$me.log

echo "$0 ran at `date` with args $@" >> $l

if [ "$1" = precustomization ] ; then

    # Maybe stop NetworkManager, but I've already ensured it
    # doesn't run by putting stuff in network/interfaces.
    true

elif [ "$1" = postcustomization ] ; then

    # TODO - run /opt/vmware/bin/vmware-config-tools.pl
    # TODO - add the relevant DNS servers
    # TODO - ensure that, by whatever mechanism, SSH host keys are regenerated each time
    # a template is instantiated to make a new VM.

    ifconfig -a >> $l
    ps waux >> $l

    echo "Sorting out IP address allocation" >> $l
    ifdown -a 2>/dev/null || true

    if ! find /etc/network -type f -name 'interfaces.*' ; then
	echo "ERROR - No /etc/network/interfaces.*" >> $l
    fi

    hostname `cat /etc/hostname`

    echo "Adding local DNS to /etc/network/interfaces" >> $l
    #I'm providing a dnsmasq cache from 192.168.3.2 (nodosaurus) so use
    #that if poss.  Could configure it in VCD but not the dns-search line.
    sed -i '/^dns-/d' /etc/network/interfaces

    cat >> /etc/network/interfaces <<.
dns-nameservers 192.168.3.2 8.8.8.8 8.8.4.4
dns-search local nerc.ac.uk
.

    ifup -a

    # We need new SSH keys,
    # But maybe VMWare does this for us???
#     if [ -e /usr/sbin/sshd ] ; then
# 	echo "Regenerating SSH keys" >> $l
# 	rm -f /etc/ssh/ssh_host*_key*
# 	dpkg-reconfigure openssh-server
#     fi

    # Claim any extra disk space.
    if [ -x ./expand_drive.sh ] ; then
	echo "Trying to expand the drive." >> "$l"
	./expand_drive.sh >>"$l" 2>&1 || [ $? = 2 ]
    fi

    # Refresh the console login screen to show the new hostname
    pkill -HUP getty

    # And lightdm if it's running
    restart lightdm >> $l 2>&1 || true

    # After this, VMWare reboots, but can I exit with a non-zero status to prevent
    # that from happening?  I'll say that a status of 69 triggers this.

    exit 69
else
    echo "Unknown action - quitting" >> $l
    exit 1
fi

if [ -x ./extra.sh ] ; then
    env LOG_TO="$l" ./extra.sh "$@"
fi

echo "DONE OK" >> $l
true
