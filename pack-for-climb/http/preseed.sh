#!/bin/sh

# set -e # does nothing if script is read from stdin

cd /target/tmp
touch preseed.sh_actually_ran

# This script will be piped to sh after Ubiquity install.
# Note the following advice:
# "The script is not run in the chroot, but you can chroot to /target and use it
# directly, or use the apt-install and in-target commands to easily install
# packages and run commands in the target system."
# Don't put too much in here; rely on scripts/root_setup.sh
# Also note the script is piped, which adds certain constraints.  If it gets
# too messy with dependencies use packit.perl.

# First thing - I need to install ssh but I need to stop Packer from
# connecting to it until the machine resets.  (Actually it won't anyway
# because there is no manager user until the machine resets, but still...)

# I think iptables is my friend here
iptables -A INPUT -p tcp --dport 22 -j REJECT

mkdir preseed_ssh_debs
cd preseed_ssh_debs

# Work out where the temporary server is serving from, based on the
# kernel command line.
baseurl=`grep -wo url='[^[:space:]]*\.cfg' /proc/cmdline |sed 's,/[^/]*\.cfg$,,;s,url=,,'`

#On BL we have ssh already!
if [ ! -e /target/usr/sbin/sshd ] ; then

for deb in \
libck-connector0_0.4.5-3.1ubuntu2_amd64.deb \
ncurses-term_5.9+20140118-1ubuntu1_all.deb \
openssh-server_6.6p1-2ubuntu1_amd64.deb \
openssh-sftp-server_6.6p1-2ubuntu1_amd64.deb \
python-requests_2.2.1-1_all.deb \
python-urllib3_1.7.1-1build1_all.deb \
ssh-import-id_3.21-0ubuntu1_all.deb ; do
  wget "$baseurl"/"$deb"
done

# Install all packages in this dir, skipping anything already installed
in-target dpkg -EGRi /tmp/preseed_ssh_debs

fi
