#!/bin/bash

# TODO - Bio-Linux also should receive automated security updates by
# default, so add this to recon.test.d or else bung the files in a
# package.

# This installer is designed for Minibuntu but should apply to
# Bio-Linux too.  Build flavours can override these settings - see
# the docker script.

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
  "bio-linux:standard"; // For old-style BL packages.
};
.

echo "Auto-updates set up."
