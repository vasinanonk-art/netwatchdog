# NetWatchdog v5

Self-healing Wi-Fi and service watchdog for the TinkerBoard smart condo server.

## Current design

- USB Wi-Fi `wlx6c4cbcdb7033` is primary.
- Onboard Wi-Fi `wlan0` is backup.
- Route is kept on USB unless USB fails repeatedly.
- Onboard is only used for failover.
- Critical services are monitored and restarted after repeated failures.

## v5.0.1 Stable

Stability-only update. No new features.

- Startup no longer forces route back to USB immediately.
- Existing healthy USB or onboard route is kept on service restart.
- If no known route is active, NetWatchdog selects the healthy interface.
- Missing systemd units are skipped instead of being restarted forever.

Tradeoff: if a watched service unit is missing at startup and later installed without restarting NetWatchdog, it will remain skipped until `netwatchdog` is restarted.

## Install on TinkerBoard

```bash
cd /opt
rm -rf netwatchdog
git clone https://github.com/vasinanonk-art/netwatchdog.git
cd netwatchdog
chmod +x install.sh
sudo ./install.sh
```

## Update on TinkerBoard

```bash
cd /opt/netwatchdog
git pull
chmod +x install.sh
sudo ./install.sh
```

## Check

```bash
systemctl status netwatchdog --no-pager -l
journalctl -u netwatchdog -n 80 --no-pager -l
ip route get 1.1.1.1
```

Expected route:

```text
1.1.1.1 via 192.168.1.1 dev wlx6c4cbcdb7033 src 192.168.1.61
```

## Rollback

```bash
systemctl disable --now netwatchdog
ip route replace default via 192.168.1.1 dev wlx6c4cbcdb7033 src 192.168.1.61 metric 100
ip route replace default via 192.168.1.1 dev wlan0 src 192.168.1.60 metric 600
```
