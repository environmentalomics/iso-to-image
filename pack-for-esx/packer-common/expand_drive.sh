#!/bin/bash

# Update on 17/6/15 - apparently I can get this functionality from the
# cloud-initramfs-growroot, so I need to see if this works.  Ideally it
# might work on both VirtualBox and VCloud and if so I'll add it to the
# standard VirtualBox build, along with instrux on how to make the hard drive
# larger (bung these on the manager desktop!).

# I have determined that, despite warnings from parted, it is actually possible
# to on-line resize the root partition if the VM disk is enlarged.  This script
# is designed to be hooked at the end of ESXCustomisation, just before VMWare triggers
# a reboot.
# To work, the root partition needs to be the only one on the disk.  Thsi will be the case
# if the uploader has stripped off the swap partition form a standard Ubuntu install.  But
# the script will sanity-check in any case.

# Again we return 0 for success, 2 for clean failure, 1 for error
# Explicit log is silly - just let the caller redirect.
#l="${LOG_TO:-/dev/stderr}"

# Do we have parted
if ! which parted >/dev/null 2>&1 ; then
    echo "Parted is not on the system.  Cannot continue."
    exit 2
fi

# Specifically we need a version of Parted that has the patch
#   0004-parted-make-_partition_warn_busy-actually-a-warning.patch
# applied.  This means we need the version from Trusty, even though it
# appears to be the same version as the one in Precise.  Note that if you do upgrade
# parted the script will not work fully on Precise as the Kernel will reject the modification
# to the live partitions.  You can rectify matters by rebooting and running
# "resize2fs /dev/..." manually.

# Discover the root device
root_part=`df / | tail -n1 | awk '{print $1}'`
root_dev=${root_part%%[1-9]*}
root_num="${root_part#$root_dev}"
root_type=primary

# The above will totally break for LVM etc, so check we got an actual number.
if ! [[ "$root_num" -gt 0 ]] ; then
    echo "Assertion failed trying to discover root device"
    exit 1
fi

if [[ $root_num -gt 4 ]] ; then
    root_type=logical
fi

# Ensure the root device really is ext4 (this is a bit crude but should work)
if ! grep -q ' / ext4 ' /proc/mounts ; then
    echo "Root device is not an ext4 filesystem."
    exit 2
fi

# Now look at the partition table and ensue that $root_num is the last partition
pt="`parted -sm "$root_dev" unit B print`"

if ! [[ "`echo "$pt" | grep -A 1 "^$root_num:" | wc -l`" == 1 ]] ; then

    # TODO - if there is one more partition and it is swap I should be able to
    # do this:
    #  0) Determine exact size and UUID of swap
    #  1) swapoff -a
    #  2) Delete it
    #  3) If this leaves an empty logical partition delete that too
    #  4) Expand root but leaving room for swap
    #  5) Make an extended partition if root_type=primary
    #  6) Make a new swap partition in the space
    #  7) Format it
    #  8) Munge /etc/fstab to ensure we see the new drive
    # This is looking tricky, and a reading of the script from cloud-initramfs-growroot
    # reveals many further gotchas for this to work in the general case.

    echo "Root partition is not the last one on the disk."
    exit 2
fi

# Now see if there is free space to expand the partition.  We are looking for at
# least 1GB, which we'll call 10^9 for the sake of simplicity
one_gb=$(( 10 ** 9 ))

dev_capacity=`echo "$pt" | sed -n '2p' | awk -F: '{print $2}'`

# The number should end in B
if ! [ "${dev_capacity:(-1)}" = B ] ; then
    echo "Assertion failed"
    exit 1
else
    dev_capacity="${dev_capacity:0:-1}"
fi

root_start=`echo "$pt" | grep "^$root_num:" | awk -F: '{print $2}'`
root_end=`echo "$pt" | grep "^$root_num:" | awk -F: '{print $3}'`

# These should also end in B
if ! [[ "${root_end:(-1)}" = B && "${root_start:(-1)}" = B ]] ; then
    echo "Assertion failed"
    exit 1
else
    root_start="${root_start:0:-1}"
    root_end="${root_end:0:-1}"
fi

if [[ $(( $dev_capacity - $root_end )) -lt $one_gb ]] ; then
    echo "Not resizing partition as there is <1GB free space."
    exit 2
fi

# Having done all those tests, we should be able to plow ahead.

#parted -a none -sm "$root_dev" unit B rm $root_num
# Yes, this is the way to force parted to do it, bizzarrely
echo "rm $root_num"$'\ny\ni\nquit' | sudo parted ---pretend-input-tty -a none -m "$root_dev"

parted -a none -sm "$root_dev" unit B mkpart $root_type $root_start 100%

resize2fs "$root_part"

# Done - yay.  VMWare will reboot for us.
