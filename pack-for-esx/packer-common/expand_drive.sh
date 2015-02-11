#!/bin/bash

# I have determined that, despite warnings from parted, it is actually possible
# to on-line resize the root partition if the VM disk is enlarged.  This script
# is designed to be hooked at the end of ESXCustomisation, just before VMWare triggers
# a reboot.
# To work, the root partition needs to be the only one on the disk.  Thsi will be the case
# if the uploader has stripped off the swap partition form a standard Ubuntu install.  But
# the script will sanity-check in any case.

# Again we return 0 for success, 2 for clean failure, 1 for error
l="${LOG_TO:-/dev/stderr}"

# Do we have parted
if ! which parted >/dev/null 2>&1 ; then
    echo "Parted is not on the system.  Cannot continue." >> "$l"
    exit 2
fi

# Discover the root device
root_part=`df / | tail -n1 | awk '{print $1}'`
root_dev=${root_part%%[1-9]*}
root_num="${root_part#$root_dev}"
root_type=primary

# The above will totally break for LVM etc, so check we got an actual number.
if ! [[ "$root_num" -gt 0 ]] ;
    echo "Assertion failed trying to discover root device" >> "$l"
    exit 1
fi

if [[ $root_num -gt 4 ]] ; then
    root_type=logical
fi

# Ensure the root device really is ext4 (this is a bit crude but should work)
if ! grep -q ' / ext4 ' /proc/mounts ; then
    echo "Root device is not an ext4 filesystem." >> "$l"
    exit 2
fi

# Now look at the partition table and ensue that $root_num is the last partition
pt="`parted -sm "$root_dev" unit B print`"

if ! [[ "`echo "$pt" | grep -A 1 "^$root_num:" | wc -l`" == 1 ]] ; then
    echo "Root partition is not the last one on the disk." >> "$l"
    exit 2
fi

# Now see if there is free space to expand the partition.  We are looking for at
# least 1GB, which we'll call 10^9 for the sake of simplicity
one_gb=$(( 10 ** 9 ))

dev_capacity=`echo "$pt" | sed -n '2p' | awk -F: '{print $2}'`

# The number should end in B
if ! [ "${dev_capacity:(-1)}" = B ] ; then
    echo "Assertion failed" >> "$l"
    exit 1
else
    dev_capacity="${dev_capacity:0:-1}"
fi

root_start=`echo "$pt" | grep "^$root_num:" | awk -F: '{print $2}'`
root_end=`echo "$pt" | grep "^$root_num:" | awk -F: '{print $3}'`

# These should also end in B
if ! [[ "${root_end:(-1)}" = B && "${root_start:(-1)}" = B ]] ; then
    echo "Assertion failed" >> "$l"
    exit 1
else
    root_start="${root_start:0:-1}"
    root_end="${root_end:0:-1}"
fi

if [[ $(( $dev_capacity - $root_end )) -lt $one_gb ]] ; then
    echo "Not resizing partition as there is <1GB free space." >> "$l"
    exit 2
fi

# Having done all those tests, we should be able to plow ahead.

parted -a none -sm "$root_dev" unit B rm $root_num

parted -a none -sm "$root_dev" unit B mkpart $root_num $root_type $root_start 100%

resize2fs "$root_part"

# Done - yay.  VMWare will reboot for us.
