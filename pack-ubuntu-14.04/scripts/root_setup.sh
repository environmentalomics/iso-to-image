#!/bin/bash

# Runs as root after first reboot.

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

#Stuff to make VirtualBox happy
apt-get -y install virtualbox-guest-{dkms,source,utils,x11}

#Stuff to make VMWare happy
apt-get -y install open-vm-tools open-vm-tools-desktop
#Note that this is fine for VMWare Desktop users but for JASMIN
#we'll do a separate build with the official tools.

# For VirtualBox, add all sudo users (ie. manager) to the vboxsf group too
members(){
    g_line=`getent group "$1"`
    [ -n "$g_line" ] || { echo "No such group $1." >&2 ; return 1 ; }
    getent passwd | awk -F: '$4 == "'`echo "$g_line" | cut -d: -f3`'" { printf("%s ",$1) }'
    echo "$g_line" | cut -d: -f4 | tr , ' '
}

for m in `members sudo` ; do
    usermod -aG vboxsf $m
done
