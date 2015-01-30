#!/bin/bash

# Runs as root after first reboot.
# This version sets up stuff for JASMIN

set -e

# Updating and Upgrading dependencies (I took off -qq to see the output here)
apt-get update -y -q > /dev/null

# I can skip this, to make a release that really matches the ISO.
# But then I can't be sure the apt-gets below will work.
# sudo apt-get upgrade -y > /dev/null

# Install whatever
#sudo apt-get -y -q install curl wget git tmux firefox xvfb vim
#sudo apt-get -y -q install linux-headers-$(uname -r) build-essential dkms nfs-common
apt-get -y install vim kbuild dkms

# Grab VMwareTools-latest.tar.xz
# Can I get this from the webserver?  Or by asking Packer to provide it directly?
tar -xvaf VMwareTools-latest.tar.gz
cd vmware-tools-distrib
./vmware-install.pl --prefix=/opt/vmware --default
#This should be how we tell VMWare-Tools to auto-rebuild kernel mods.
cat >>/etc/vmware-tools/locations <<.
remove_answer AUTO_KMODS_ENABLED_ANSWER
answer AUTO_KMODS_ENABLED_ANSWER yes
remove_answer AUTO_KMODS_ENABLED
answer AUTO_KMODS_ENABLED yes
.
/opt/vmware/bin/vmware-config-tools.pl -p --default


# TODO - turn off IPV6 by setting GRUB_CMDLINE_LINUX="ipv6.disable=1" in /etc/default/grub,
# and test that it works.

# TODO - disable password for manager and add SSH key.  Can I do that here?
