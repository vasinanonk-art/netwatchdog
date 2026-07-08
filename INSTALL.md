# Install Guide

Fresh Debian/TinkerBoard install:

```bash
sudo apt-get update
sudo apt-get install -y git
cd /opt
sudo git clone -b feature/oled-v1 https://github.com/vasinanonk-art/netwatchdog.git
cd netwatchdog
sudo ./install.sh
```

Installer creates:

- `/opt/netwatchdog`
- `/etc/netwatchdog/config.yaml`
- `/run/netwatchdog`
- `/var/lib/netwatchdog/backups`
- `/var/log/netwatchdog`
- `/etc/systemd/system/netwatchdog.service`
- `/etc/systemd/system/netwatchdog-dashboard.service`
- `/usr/local/bin/netwatchdogctl`

Post-install check:

```bash
systemctl is-active netwatchdog
systemctl is-active netwatchdog-dashboard
sudo netwatchdogctl selftest
```
