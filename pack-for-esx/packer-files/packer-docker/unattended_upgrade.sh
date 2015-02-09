#!/bin/bash

# TODO - Bio-Linux also should receive automated security updates by
# default, so add this to recon.test.d or else bung the files in a
# package.

# This installer is designed for Minibuntu but should apply to
# Bio-Linux too.

# Nothing will work without Cron running.
apt-get -y install cron anacron unattended-upgrades

cat > /etc/apt/apt.conf.d/55unattended-upgrades-override <<.
// Activate partial unattended upgrade
APT::Periodic {
    Update-Package-Lists "1";
    Download-Upgradeable-Packages "1";
    AutocleanInterval "7";
    Unattended-Upgrade "1";
};

// All security patches and Docker packages
Unattended-Upgrade::Allowed-Origins {
    "\${distro_id}:\${distro_codename}-security";
    "\${distro_id}:\${distro_codename}-updates";
    ":"; //Fudge for Docker, but it doesn't fully work anyway
};
.

# For docker, shout at the user in MOTD.
cat >/etc/update-motd.d/92-docker-update <<.
#!/bin/sh

# This is really, really horrible but I can't see a better way to do it just now...
if env LANG=C apt-get -s --print-uris install lxc-docker 2>&1 | \
	grep -q 'The following packages will be upgraded'
then

    echo
    echo "There is a new Docker version available.  Please run 'sudo apt-get install lxc-docker'"
    echo "to install it."
    echo
fi
.

chmod +x /etc/update-motd.d/92-docker-update

echo "Auto-updates set up."
