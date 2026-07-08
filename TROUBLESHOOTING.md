# Troubleshooting

## Dashboard not opening

```bash
systemctl status netwatchdog-dashboard --no-pager -l
journalctl -u netwatchdog-dashboard -n 80 --no-pager -l
ss -lntp | grep -E '8080|8090'
```

Expected:

```text
8080 NetWatchDog Dashboard
8090 Smart Condo Dashboard
```

If NetWatchDog legacy services are using `8080`:

```bash
sudo netwatchdogctl disable-legacy
sudo systemctl restart netwatchdog-dashboard
```

Do not stop or modify `smart-condo-dashboard.service`.

## Status not updating

```bash
systemctl status netwatchdog --no-pager -l
journalctl -u netwatchdog -n 80 --no-pager -l
cat /run/netwatchdog/status.json
```

## Gateway Lost

```bash
ip route get 1.1.1.1
ping -c 3 192.168.1.1
iw dev wlx6c4cbcdb7033 link
iw dev wlan0 link
```

## Internet Lost

```bash
ping -c 3 1.1.1.1
resolvectl status || true
ip route
```

## OLED issue

```bash
systemctl status netwatchdog-oled --no-pager -l
journalctl -u netwatchdog-oled -n 80 --no-pager -l
ls /dev/i2c-*
```

## Service restart loop

```bash
journalctl -u netwatchdog -n 120 --no-pager -l
systemctl status <service> --no-pager -l
```

## Restore backup

```bash
sudo netwatchdogctl restore /var/lib/netwatchdog/backups/<file>.tar.gz
sudo systemctl restart netwatchdog netwatchdog-dashboard netwatchdog-oled
```

## Full self test

```bash
sudo netwatchdogctl selftest
```
