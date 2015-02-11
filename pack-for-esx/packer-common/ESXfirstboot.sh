#!/bin/bash

# This script wants to bee hooked either to run on first boot (/etc/rc?.d) or
# else to be run as part of the deployment on ESX.
# But what I don't know is if the latter will work, given that
# /opt/vmware/bin/vmware-config-tools.pl won't run until it is within a VMWare VM,

# On 7/1/15 - looks like I worked around that, so see ESXCustomisation.sh
# for a modified version that runs that way.

set -e

# TODO - run /opt/vmware/bin/vmware-config-tools.pl
# TODO - add the relevant DNS servers and ensure that NetworkManager isn't trying
# to manage eth0.
# TODO - ensure that, by whatever mechanism, SSH host keys are regenerated each time
# a template is instantiated to make a new VM.

# How to say things to the user.
. /lib/lsb/init-functions
say_message() {
    if [ -x /bin/plymouth ] && /bin/plymouth --ping ; then
	/bin/plymouth message --text="$*"
    elif type log_warning_msg >/dev/null ; then
	log_warning_msg "$*"
    else
	echo "$*" >&2
    fi
}


me=ESXfirstboot

# For now, just debug.
l=/var/log/$me.log
echo "$0 actually ran at `date`" >> $l

ifconfig -a >> $l

ps waux >> $l

# say_message "Setting up VMWare client drivers on first boot"
# /opt/vmware/bin/vmware-config-tools.pl -p --default >>$l 2>&1
say_message "Skipping setting up VMWare client drivers on first boot"

sleeps=2
timeout=2
finishtime=0
say_message "Waiting $timeout minutes for IP address allocation"
ifdown -a 2>/dev/null || true
for n in `seq 1 $sleeps $(( 60 * $timeout ))` ; do
    sleep $sleeps
    if find /etc/network -type f -name 'interfaces.*' ; then

	#Need a better fix for DNS.
	cat >> /etc/network/interfaces <<.
dns-nameservers 8.8.8.8 8.8.4.4
dns-search nerc.ac.uk
.

	ifup -a

	hostname `cat /etc/hostname`

	finishtime=$n
	break
    fi
done

if [ "$finishtime" = 0 ] ; then
    say_message "No network after $n seconds.  Boo."
    sleep $sleeps
else
    echo "Network set up after $n seconds" >> $l
    ifconfig -a >> $l
fi


# That should be it.  Do I need to reboot for guest customisations to take effect?
# Do I need to reboot again so that the network actually comes up?

# Clean myself up
echo rm /etc/rc?.d/S99$me >> $l
rm /etc/rc?.d/S99$me
