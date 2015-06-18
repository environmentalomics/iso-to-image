#!/bin/bash

set -e

# A script to ensure that the Ubuntu host is ready to run on CLIMB.  While this
# script is goint to be user for Bio-Linux I'd like it to work on any Ubuntu 14.04
# and it will be tested on minibuntu.
# The script needs to run fully in VirtualBox.  Ideally it should need no network
# access.

# Sanity check
if ! which dpkg ; then
    echo "Cannot find command dpkg.  This script only works on Debian-based systems."
    false
fi

# On minibuntu we have neither the Universe repo active nor add-apt-repository
# available to make it so.  Bootstrap to be sure.
apt-get update -y -q > /dev/null
apt-get install -y apt-transport-https software-properties-common ca-certificates
add-apt-repository universe

#Again...
apt-get update -y -q > /dev/null
sudo apt-get -y install cloud-initramfs-growroot cloud-init

# And replace the cloud.cfg file with my own
[ -e /etc/cloud/cloud.cfg ] #It does exist, right?
cat packer-common/cloud.cfg > /etc/cloud/cloud.cfg

echo Removing avahi-autoipd
dpkg -P avahi-autoipd

echo Removing the open-vm tools
rm -f /etc/vmware-tools/*.old
dpkg -P open-vm-tools open-vm-tools-desktop

echo And the VirtualBox tools too
dpkg -P virtualbox-guest-{dkms,source,utils,x11}

# What guest drivers do we actually need.  We'll see.

# I have to do something, according to Jonathan, to make the network work when the thing is
# snapshotted and de-snapshotted.  I suspect it is something like this:
# It may be that cloud-init sorts this already?
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
# Finally, boot to tty and disable Plymouth (as per Simon's advice)
echo "SET grub-pc/install_devices /dev/sda" | debconf-communicate
echo "SET grub-pc/install_devices_disks_changed /dev/sda" | debconf-communicate

# Apparently this sets the debconf setting, not vice-versa
sed -i 's/^\(GRUB_CMDLINE_LINUX_DEFAULT\)=.*/\1=""/' /etc/default/grub
sed -i 's/^\(GRUB_CMDLINE_LINUX\)=.*/\1="text console=tty0 console=ttyS0,115200"/' /etc/default/grub

dpkg-reconfigure -pcritical -u grub-pc

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

# NetworkManager runs and starts managing the network cards, which gets in the
# way of ESX but maybe not cloud-init?
#sed -i 's/^\(iface [a-z0-9]* inet\) dhcp/\1 manual/' /etc/network/interfaces

# Leave it it to cloud-init to sort out SSH keys.  See the customised cloud.cfg
# settings file.

# Kill the swap.  Swap is inappropriate on CLIMB, as far as I can see.  Also with no
# swap partition we can more easily do a cheeky disk resize post-customisation.
# Note that a return val of 2 is to be regarded as success.
echo "Running swap remover script."
bash packer-common/kill_swap.sh || [ $? = 2 ]

# Unattended upgrades are wanted by default.
bash packer-common/unattended_upgrade.sh

#After this, Packer can't work any more.  You'll either need to go in at the console
#or else cloud-init needs to set up a working key.
read -r -d '' admonishment <<"." || true
# Password-based authentication has been disabled for accessing this Cloud system
# as it is highly insecure.  Do not re-enable it!!  There are always alternatives.
# Ask the Cloud system administrators for advice.
.

sed -i 's/^#\?\(PasswordAuthentication \).*/'"`awk 1 ORS='\\\\n' <<<"$admonishment"`"'\1 no/' /etc/ssh/sshd_config
restart ssh


# That's all for now, so make your image and load it up.
echo FINISHED
