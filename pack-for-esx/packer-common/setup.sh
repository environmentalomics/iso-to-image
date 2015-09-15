#!/bin/bash

set -e

# A script to ensure that the Ubuntu host is ready to run on VCloud.  I'd
# like this to be runnable on any Ubuntu and also to be invokable either from
# the VCloud deployment hooks or else as the packer root_setup script while still
# in VirtualBox.  And it should need no network access.

#==I root
# This bit allows me to have this script fetch the files from a base URL,
# but they should just magically be here via Packer or Packit file provisioning.
while read -r l ; do
    [ -z "$BASEURL" ] && break
    l="${l#* }"
    ( cd packer-common && wget -q "$BASEURL/$l" )
done <<.
#==F VMWare_Guest_Tools_9.4.5_esx.tar
#==F id_rsa.pub
#==F ESXfirstboot.sh
.

# Not needed, I hope
#apt-get update -y -q > /dev/null

# Sanity check
if ! which dpkg ; then
    echo "Cannot find command dpkg.  This script only works on Debian-based systems."
    false
fi

# This can stop the script jamming due to questions about config updates
export UCF_FORCE_CONFFOLD=1

echo Removing avahi-autoipd
dpkg -P avahi-autoipd

echo Removing the open-vm tools
rm -f /etc/vmware-tools/*.old
dpkg -P open-vm-tools open-vm-tools-desktop

echo And the VirtualBox tools too
dpkg -P virtualbox-guest-{dkms,source,utils,x11}

if [ -e /opt/vmware/lib/vmware-tools ] ; then
    echo "Seems a version of the VMWare guest tools are already installed"
else
    echo "Installing the ESX guest tools"
    # Grab VMwareTools-latest.tar.xz
    # Packer will ensure the file is there for me, or I could use packit.perl.
    # Note that I just tarred up the CD image, so I have to unpack twice.

    tar -xvf packer-common/VMWare_Guest_Tools_*.tar
    tar -xzf */VMwareTools-*.tar.gz

    ( cd vmware-tools-distrib &&
	./vmware-install.pl --prefix=/opt/vmware --default ) || true
    #Note this exits with an error complaining it wants to run in a VM.
    #We need to make it run on first boot inside a VirtualBox VM, or else
    #fake it - see below.

    #This should be how we tell VMWare-Tools to auto-rebuild kernel mods.
    cat >>/etc/vmware-tools/locations <<.
remove_answer AUTO_KMODS_ENABLED_ANSWER
answer AUTO_KMODS_ENABLED_ANSWER yes
remove_answer AUTO_KMODS_ENABLED
answer AUTO_KMODS_ENABLED yes
.

    for sbin in /opt/vmware/lib/vmware-tools/sbin?? ; do
	mv $sbin/vmware-checkvm $sbin/vmware-checkvm.real
	cat >>$sbin/vmware-checkvm <<'.'
#!/bin/sh
if [ "$*" = "" -a "$FAKE_VMWARE_FTW" = "yes" ] ; then
    echo "You really are in VMWare, honest to (good)ness"
else
    exec "`readlink -f $0`".real
fi
.
	chmod +x $sbin/vmware-checkvm
    done

    #Also the drivers rely on this directory being present:
    mkdir -p /etc/dhcp3

    #Don't normally do this unless we are in a VMWare VM, but we've
    #faked it.
    export FAKE_VMWARE_FTW=yes
    /opt/vmware/bin/vmware-config-tools.pl -p --default --skip-stop-start
fi

# I have to do something, according to Jonathan, to make the network work when the thing is
# snapshotted and de-snapshotted.  I suspect it is something like this:
rm -f /etc/udev/rules.d/*-persistent-net.rules
for killit in /lib/udev/write_net_rules ; do
    dpkg-divert --rename --divert "$killit".real "$killit"
    cat > "$killit" <<.
#!/bin/sh
# Script diverted to "$killit".real and disabled for ESX compatibility.
true
.
    chmod 755 "$killit"
done

echo Editing Grub settings

# Turn off IPV6 by setting GRUB_CMDLINE_LINUX="ipv6.disable=1" in /etc/default/grub.
# Also make lightdm not run by default by adding "text" argument.  You can run it by
# logging in as manager and doing "sudo start lightdm"
# Also, stop Grub complaining that the drives have changed when it is reconfigured.
# echo "SET grub2/linux_cmdline ipv6.disable=1 text" | debconf-communicate
echo "SET grub-pc/install_devices /dev/sda" | debconf-communicate
echo "SET grub-pc/install_devices_disks_changed /dev/sda" | debconf-communicate

# Apparently this sets the debconf setting, not vice-versa
sed -i 's/^\(GRUB_CMDLINE_LINUX_DEFAULT\)=.*/\1=""/' /etc/default/grub
sed -i 's/^\(GRUB_CMDLINE_LINUX\)=.*/\1="ipv6.disable=1 text"/' /etc/default/grub

dpkg-reconfigure -pcritical -ftext -u grub-pc

# Also Exim needs to be told about this, if it is installed.
rm -f /var/log/exim4/paniclog 2>/dev/null
if echo "SET exim4/dc_local_interfaces 127.0.0.1" | debconf-communicate ; then
    sed -i 's/\(dc_local_interfaces=\).*/\1'"'127.0.0.1'/" /etc/exim4/update-exim4.conf.conf
    dpkg-reconfigure -pcritical exim4-config
fi

# Switch the default desktop to MATE
# Note that auto-login for the manager user will have been set in preseed.cfg
# if you are working on the BL OVA image, but you won't be auto-starting
# X anyway - see the Grub stuff above.
if which mate-session >/dev/null 2>&1 && \
    [ -d /usr/share/lightdm/lightdm.conf.d ] ; then
cat > /usr/share/lightdm/lightdm.conf.d/60-mate.conf <<.
[SeatDefaults]
user-session=MATE
.
fi

# Implement the fix given here, to enable hardware hotplug:
# http://tech.vg.no/2014/01/08/how-to-make-ubuntu-play-nice-with-vmware/
true <<EOF
$ echo acpi_memhotplug | sudo tee -a /etc/modules
$ cat << EOF | sudo tee /etc/udev/rules.d/99-vmware-hotplug-udev.rules
# Automatically enable hot-plugged CPUs and memory
ACTION=="add", SUBSYSTEM=="cpu", ATTR{online}="1"
ACTION=="add", SUBSYSTEM=="memory", ATTR{state}="online"
EOF

# TODO - test that the above works on a fresh Ubuntu image.

# NetworkManager runs and starts managing the network cards, which gets in the
# way of the crufty ESX customisations. Simplest option
# is hopefully just to modify eth0 in /etc/network/interfaces
sed -i 's/^\(iface [a-z0-9]* inet\) dhcp/\1 manual/' /etc/network/interfaces

# One solution - in the boot sequence run ESXfirstboot, which should
# bootstrap vmware and then fix the networking and reboot (or something)
# efb=ESXfirstboot
# cp $efb.sh /etc/init.d/$efb
# chmod +x /etc/init.d/$efb
# Disabled in favour of proper hook...
#for rc in 1 2 ; do ln -s ../init.d/$efb /etc/rc${rc}.d/S99$efb ; done

# Here is an actual post-customisation script.  This will be referenced
# in the OVF
# FIXME - what script does get run?  David told me.
# For now...
mkdir -p /etc/ESXCustomisation
cp packer-common/ESXCustomisation.sh /etc/ESXCustomisation/main.sh
chmod +x /etc/ESXCustomisation/main.sh

# Turn off password based SSH and load the NEBC public key. Later this will be replaced by
# "something better" (TM).

echo Setting up key-based ssh login

# In BL the initial user is always called manager, but more generally it should be user 1000
prime_user="`getent passwd 1000 | cut -d: -f1`"
if [ -z "$prime_user" ] ; then
    echo "Error trying to determine where to put the SSH public key."
    echo "Normally /home/manager/.ssh/authorized_keys"
fi
if ! groups "$prime_user" | cut -d: -f2 | sed 's/  */\n/g' | grep -qx sudo ; then
    echo "User $prime_user is not in the sudo group.  That doesn't seem right"
fi
su -c 'mkdir -p -m700 ~/.ssh' "$prime_user"

if su -c 'test -s ~/.ssh/authorized_keys' "$prime_user" ; then
    echo "~/.ssh/authorized_keys already has data.  Will not write to it."
else

    grep -q '' packer-common/id_*.pub #ie. check id_*.pub has data
    cat packer-common/id_*.pub | su -c 'umask 077 ; cat >> ~/.ssh/authorized_keys' "$prime_user"
fi

# Kill the swap.  Swap is inappropriate on ESX, as far as I can see.  Also with no
# swap partition we can more easily do a cheeky disk resize post-customisation.
# Note that a return val of 2 is to be regarded as success.
echo "Running swap remover script."
bash packer-common/kill_swap.sh || [ $? = 2 ]
cp packer-common/expand_drive.sh /etc/ESXCustomisation/
chmod +x /etc/ESXCustomisation/expand_drive.sh

# Unattended upgrades are wanted by default.
bash packer-common/unattended_upgrade.sh

#After this, Packer can't work any more. You'd better have the key to get back in!
read -r -d '' admonishment <<"." || true
# Password-based authentication has been disabled for accessing this Cloud system
# as it is highly insecure.  Do not re-enable it!!  There are always alternatives.
# Ask the Cloud system administrators for advice.
.

sed -i 's/^#\?\(PasswordAuthentication \).*/'"`awk 1 ORS='\\\\n' <<<"$admonishment"`"'\1 no/' /etc/ssh/sshd_config
restart ssh

# On the EOS cloud we don't currently have any valid nameservers set by vCloud, so for now
# add 8.8.8.8.
# FIXME
# But I think this needs to be done after the network has been configured on first boot.
#     resolvconf -a eth0.manual <<.
#     nameserver 8.8.8.8
#     nameserver 8.8.4.4
#     search nerc.ac.uk
#     .
#     cat >> /etc/network/interfaces <<.
#     dns-nameservers 8.8.8.8 8.8.4.4
#     dns-search nerc.ac.uk
#     .

# Allow for custom configuration flavour.
packer_cust=`ls -d packer-* | grep -vFx packer-common`
if [ -d "$packer_cust" ] ; then
    if [ -e "$packer_cust"/ESXCustomisation.sh ] ; then
	cp "$packer_cust"/ESXCustomisation.sh /etc/ESXCustomisation/extra.sh
	chmod +x /etc/ESXCustomisation/extra.sh
    fi
    chmod +x "$packer_cust"/setup.sh
    "$packer_cust"/setup.sh
fi

# That's all for now, so make your image and load it up.
echo FINISHED
