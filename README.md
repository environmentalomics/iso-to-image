Ubuntu ISO to VMWare VCloud Image
=================================

What is this?
-------------

This is a set of scripts that takes an Ubuntu ISO and prepares it to run as a VM
on VMWare VCloud (ESX), via a VirtualBox VM.

Why do you care?
----------------

If you are interested in auto-building Ubuntu images, or supporting Ubuntu on VCloud,
then you might find this useful.
It requires no proprietary software or manual intervention - ie. you can auto-build on
any Linux server without paying for extra licenses for VMWare stuff.

Why is it so messy?
-------------------

This is not currently a finished product and you are not going to be able to
run it out-of-the-box.  The scripts have grown organically as I worked out all
the steps that were needed and the hacks to make them work.  To make this into
a solid package of code would mean a total re-write, which may or may not happen.
But I'm hoping that by publishing my recipes I can save others from having to
work out everything from scratch.

In putting this together I've solved various problems and I want others to be able
to see what I've done.

If you want clarification on any aspects of the code please mail me direct to ask,
but if your question is "What do I type to make it all just work?" then you are
out of luck.

What are the steps?
-------------------

The whole process takes you from an Ubuntu ISO to a VMWare VCloud machine instance
via a VirtualBox image and a VMWare-compatible OVF.  Others have documented parts
of the process but I'm sure I'm the first to do the whole thing and to do it
without any dependencies on proprietary software (aside from the VMWare guest
drivers which you need to add into the image).

**1) Use Packer.io to make a VirtualBox VM from an Ubuntu ISO**

Packer comes with a pre-made recipe to do this from the "server" ISO,
but this version does it from the reguler "desktop" ISO.

It also sorts out adding the right drivers to make the graphics happy in
VirtualBox.

The "create_box" script is the entry point to this.  The product is an OVA file which
you can run in VirtualBox.

**2) Use Packer.io to convert this for use in VCloud**

Includes removal of swap partition, installation of drivers, setting of security settings.
This is particular to the JASMIN system at Rutherford Appleton Labs so to re-use this you'll
need to modify it to your own needs.

Removal of the swap is probably what you want in ESX anyway, but in our case it more
importantly allows the main partition to be expanded on first boot if you have opted to
deploy with a larger HDD.  See stage (5)

**2a) Further customise the image**

I got a bit distracted by a request to use my image builder to make Docker-ready images,
so I added an option to make a "flavour" by adding a post setup script.  This is
rather wrong-headed as really I should apply the flavour to the VirtualBox image then
convert it to VCloud in the standard way.  I might undo this feature but for now here it is.
Like I said, this code really was more grown than designed.

**2b) Patch the VMDK**

The VMWare guest drivers can be extracted from VCloud and if you have VMWare desktop software
you can install them within a VM running in that.  But if you try to install them in
VirtualBox then:

 i)  The installer will refuse, saying this is not a VMWare VM.
 ii) The VCloud system will not believe that the drivers are actually on the image

The setup.sh script in part (2) works arount (i) and this patcher works around (ii).

**3) Modify the OVF metadata to keep VCloud happy**

I thought it would be simpler to modify the VirtualBox OVF to work in VCloud, but in
hindsight it would have been simpler to take a template VCloud OVF and to slot in the
new VMDK and machine name.  But in any case this is the approach we have, a big ugly
munging of the OVF XML data.

**4) Upload to VCLoud**

This functionality is actually in the free (as in no cost) ovftool from VMWare,
but by the time I found it I'd already made a Python3 uploader based on the API
documentation.

**5) Bootstrap the system on first boot**

Stage (2) install a post-customisation hook, run just before VCloud resets the system
after the first boot.

For my purposes this forces the DNS servers to search 8.8.8.8 but really this is a
quirk of our particular system.

Among other things this will also check if there is significant free
space after the root partition and if so will expand the partition to make use of the
drive.  Parted and ext4 on-line resizing are reliable enough to make this OK, especially
is this is a new machine image with no precious data to lose.

The upshot is that in simple cases you can make an image with a small drive then expand the
drive at deployment time and it all "just works".

( Note - this bit really isn't tested yet )


License:
--------

Unless otherwise stated all code is Copyright (c) NERC 2014-2015 and is Free Software,
see LICENSE.txt.
