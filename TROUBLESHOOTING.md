# Troubleshooting

## Dashboard not opening

```bash
systemctl status netwatchdog-dashboard --no-pager -l
journalctl -u netwatchdog-dashboard -n 80 --no-pager -l
ss -lntp | grep 8090
```

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

## Service restart loop

```bash
journalctl -u netwatchdog -n 120 --no-pager -l
systemctl status <service> --no-pager -l
```

## Restore backup

```bash
sudo netwatchdogctl restore /var/lib/netwatchdog/backups/<file>.tar.gz
sudo systemctl restart netwatchdog netwatchdog-dashboard
```
