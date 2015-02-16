#!/bin/bash
set -e

# This is a script to install Docker as wanted by Priyam at QMUL.

# The script is designed to run as a post-customisation on MiniBuntu in order
# to produce as standard Docker image, but for testing I'll just run it in the
# VCloud VM, after instantiation, to set it up.

if [ `id -u ` != 0 ] ; then
    echo "This script needs to run as root."
    exit 1
fi

#Deferred installer
TO_INSTALL=
d-install() { TO_INSTALL="$TO_INSTALL $@" ; }
d-commit() { apt-get update && apt-get install -y $TO_INSTALL ; }

# 1 - Install Docker itself.

# We need this before adding the docker repo
if ! [ -e /usr/lib/apt/methods/https ] || \
   ! which add-apt-repository >/dev/null 2>&1 ; then
    apt-get update
    apt-get install -y apt-transport-https software-properties-common \
	 ca-certificates
fi
add-apt-repository universe

# Since we can't always validate the HTTPS cert, and all the packages are
# signed anyway, do this:
cat >/etc/apt/apt.conf.d/30httpsnoverify <<.
Acquire::https {
    Verify-Peer "false";
};
.

cat >/etc/apt/sources.list.d/docker.list <<.
deb https://get.docker.com/ubuntu docker main
.
apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys A88D21E9

# Note docker does need apparmor even though it does not declare the dependency.
# Also wants SSL certs.
# I'm installing all the depends/recommends from the docker.io package here
d-install lxc-docker apparmor ca-certificates
d-install cgroup-lite git git-man liberror-perl aufs-tools

#####
## To verify that everything has worked as expected:
##
## $ sudo docker run -i -t ubuntu /bin/bash
####

# 2 - Install Ruby.  Priyam asked for 2.1 but we only have 2.0 in the
# regular repo so we'll use Brightbox.
# Using add-apt-repository as we had to install it in any case.
add-apt-repository ppa:brightbox/ruby-ng

# Manual method was...
# . /etc/lsb-release
# cat >/etc/apt/sources.list.d/brightbox-ruby.list <<.
# deb http://ppa.launchpad.net/brightbox/ruby-ng/ubuntu $DISTRIB_CODENAME main
# deb-src http://ppa.launchpad.net/brightbox/ruby-ng/ubuntu $DISTRIB_CODENAME main
# .
# apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C3173AA6

d-install bind9-host
d-install ruby2.1

# Do this before creating the user.
d-commit

# 3 - Ensure all users go in the Docker group

# Fortunately I already have this code from adding Bio-Linux users into the arb group

if ! grep -q '^EXTRA_GROUPS=".* docker.*"' /etc/adduser.conf ; then
    echo "Fixing EXTRA_GROUPS"
    sed -i 's/^[# ]*\(EXTRA_GROUPS="[^"]*\)"/\1 docker"/' /etc/adduser.conf
fi

if ! grep -q '^ADD_EXTRA_GROUPS=1' /etc/adduser.conf ; then
    echo "Fixing ADD_EXTRA_GROUPS"
    sed -i 's/^[ #]*\(ADD_EXTRA_GROUPS\)=.*/\1=1/' /etc/adduser.conf
fi

# 4 - Add Priyam account.  This obviously shouldn't go in the regular image build but I
# add it here for completeness.  Also assures us that (3) worked.

# Since the password is only good for sudo I'll set it the same as the user name.

adduser --disabled-password --gecos 'Anurag Priyam,,,' priyam
echo "priyam" | tee - | passwd priyam 2>/dev/null
usermod -aG sudo priyam

su -c 'mkdir -p -m700 ~/.ssh' priyam
cat packer-docker/id_priyam.pub | su -c 'umask 077 ; cat >> ~/.ssh/authorized_keys' priyam

echo "User priyam looks like this:"
id priyam

# 5 - Set appropriate auto-update settings, overriding the ones in packer-common
bash packer-docker/unattended_upgrade.sh

echo DONESKI
echo "A reboot may be needed to actually get Docker to work"
