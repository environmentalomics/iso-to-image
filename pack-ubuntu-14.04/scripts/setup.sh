#!/bin/bash

set -e

# Runs as manager after first reboot.

# Let's see if I can mess with gsettings.  I don't think I want the power status (though
# it does mirror the status of the host so could actually be useful if you are running
# full-screen)
dbus-launch gsettings set com.canonical.indicator.power icon-policy 'never'

# But I really don't want the virtual screen locking (could do this for all users too?)
dbus-launch gsettings set org.gnome.desktop.screensaver lock-enabled 'false'
dbus-launch gsettings set org.gnome.desktop.screensaver ubuntu-lock-on-suspend 'false'
dbus-launch gsettings set org.gnome.desktop.session idle-delay 'uint32 0'

# And I don't want my menus shifted up the screen at all, as this is really confusing in
# a VM Window.  Actually for a VM Window you're better off switching to MATE.
# Sadly for 14.04 this is imperfect and Firefox seems to ignore it completely
#   cat > ~/.xsessionrc <<.
#   #Disable global menus
#   export UBUNTU_MENUPROXY=0
#   export QT_X11_NO_NATIVE_MENUBAR=1
#   .

# Try this instead:
dbus-launch gsettings gsettings set com.canonical.Unity integrated-menus true
