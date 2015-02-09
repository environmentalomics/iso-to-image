#!/bin/bash

# Runs as root after first boot.

# This version works out where the HTTP server is, then fetches and runs setup.sh,
# and then cleans up.
# Advantage is I don't have to add new files in the JSON to have them staged for the
# real setup script.

set -e

# This doesn't work after first boot, but I can feed BASEURL in packer.json...
# oh, actually, I can't - https://github.com/mitchellh/packer/issues/1277
# BASEURL=`grep -wo url='[^[:space:]]*\.cfg' /proc/cmdline |sed 's,/[^/]*\.cfg$,,;s,url=,,'`
# export BASEURL
# if [ -z "$BASEURL" ] ; then
#     echo "No BASEURL set." >&2
#     exit 1
# fi

# Plan B - all files will be provided into /tmp/files/packer-common
tmpdir="/tmp/packer-files"
cd $tmpdir

#wget "$BASEURL/setup.sh"
chmod +x packer-*/setup.sh
packer-common/setup.sh

#Self-destruct
rm -rf $tmpdir
