# Install Guide

Fresh Debian/TinkerBoard install:

```bash
sudo apt-get update
sudo apt-get install -y git
cd /opt
sudo git clone -b feature/oled-v1 https://github.com/vasinanonk-art/netwatchdog.git
cd netwatchdog
sudo sh install.sh
```

Installer creates or updates:

- `/opt/netwatchdog`
- `/etc/netwatchdog/config.yaml`
- `/run/netwatchdog`
- `/var/lib/netwatchdog/backups`
- `/var/log/netwatchdog`
- `/etc/systemd/system/netwatchdog.service`
- `/etc/systemd/system/netwatchdog-dashboard.service`
- `/etc/systemd/system/netwatchdog-oled.service` when OLED unit exists
- `/usr/local/bin/netwatchdogctl`

Installer disables legacy NetWatchDog services only:

- `netwatchdog-web.service`
- `netwatchdog-status.service`

It must not touch `smart-condo-dashboard.service` or port `8090`.

Post-install check:

```bash
systemctl is-active netwatchdog
systemctl is-active netwatchdog-dashboard
systemctl is-active netwatchdog-oled
ss -lntp | grep -E '8080|8090'
sudo netwatchdogctl selftest
```

Expected port ownership:

```text
8080 NetWatchDog Dashboard
8090 Smart Condo Dashboard
```
