#!/bin/bash

# This is not well tested!

# Remove any swap.  You should have parted installed on the image so that extra drive
# space can be configured on VM boot.

# Exits 0 on success, 2 on a clean failure (eg. no swap found, no parted), 1 on an error
# Final return status is that from parted

# Delete swaps from fstab
sudo sed -i '/^[^[:space:]]\+[[:space:]]\+[^[:space:]]\+[[:space:]]\+swap[[:space:]]\+/d' /etc/fstab

if ! which parted >/dev/null 2>&1 ; then
cat <<.
WARNING: Parted is not installed on the image.  Automated resizing of the disk on
         VM instantiation will not be possible, and the swap partition (if any)
         will be disabled but not removed.
.
exit 2
fi

# Remove the swap partition carefully.  Look only on the device mounted on /.
# If there is only one partition > 4 and it is swap then remove the extended
# partition.
# Else, if the last partition is swap then remove it.

# Discover the root device
root_part=`df / | tail -n1 | awk '{print $1}'`
root_dev=${root_part%[1-9]}

if [[ -z "$root_dev" || "$root_dev" = "$root_part" || "$root_dev" == *[0-9] ]]  ; then
    # Note - failure to deal with root dev >9 is really a shortcoming of this script.
    echo "Cannot determine root device or root device is >9."
    exit 1
fi

# Discover the swap device
swaps_active=$(( `swapon -s | wc -l` - 1 ))
if ! [ "$swaps_active" = 1 ] ; then
    #TODO - should maybe continue and just remove the last swap??
    echo "Did not see one single swap device to remove."
    exit 2
fi

swap_part=`swapon -s | tail -n1 | awk '{print $1}'`
if [[ "$swap_part" == /dev/mapper/crypt* ]] ; then
    # See what it really is
    echo "Looking up real partition for encrypted loopback"
    swap_part=`cryptsetup status "$swap_part" | grep '^[[:space:]]*device' | awk '{print $2}'`
fi

# Check the swap partition is on the same device as /
if ! [[ "$swap_part" == ${root_dev}? ]] ; then
    echo "Swap partition is not on same device as root partition"
    exit 2
fi

# Get the partition numbers for both devices
root_part_num=${root_part:(-1)}
swap_part_num=${swap_part:(-1)}

# Sanity check
if ! [[ "$root_part_num" -gt 0 && "$swap_part_num" -gt 0 ]] ; then
    echo "Sanity check assertion failed for $root_part/$swap_part."
    exit 1
fi

# Now look at the whole partition table and see if we are OK to remove the
# swap.
pt="`parted -sm "$root_dev" unit B print`"
p_to_delete=0

if ! echo "$pt" | grep -q ':msdos:' ; then
    echo "Failed to get info from parted, or else not an MSDOS partition table."
    exit 1
fi

# Is the swap the last partition on the disk?
if ! [[ "`echo "$pt" | grep -A 1 "^$swap_part_num:" | wc -l`" == 1 ]] ; then
    echo "Swap partition is not the last one on the disk."
    exit 2
fi

if [[ "$swap_part_num" -le 4 ]] ; then
    #OK, we are happy
    p_to_delete=$swap_part_num
else
    #Are there any partitions >4 and <$swap-part_num?
    prev_part=`echo "$pt" | grep -B 1 "^$swap_part_num:" | head -n1 | awk -F: '{print $1}'`
    if [[ $prev_part -le $root_part_num ]] ; then
	echo "Assertion failed - swap/prev/root is $swap_part_num/$prev_part/$root_part_num"
	exit 1
    elif [[ $prev_part -gt 4 ]] ; then
	# Swap is not the only thing on the extended partition
	p_to_delete=$swap_part_num
    else
	# Swap is the only thing on the extended partition, and the previous
	# partition is actually the extended partition.
	p_to_delete=$prev_part
    fi
fi

if [[ "$p_to_delete" -lt 1 ]] ; then
    echo "Assertion failed."
    exit 1
fi

#Finally! (Return status is that from parted)
swapoff -a
parted -sm "$root_dev" rm "$p_to_delete"
