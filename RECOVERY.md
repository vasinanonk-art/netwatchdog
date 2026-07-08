# Recovery Guide

## Dashboard down

```bash
sudo systemctl restart netwatchdog-dashboard
sudo journalctl -u netwatchdog-dashboard -n 80 --no-pager -l
ss -lntp | grep 8080
```

Expected:

```text
python3 dashboard.py listening on 0.0.0.0:8080
```

If `8080` is already used by a legacy NetWatchDog service:

```bash
sudo netwatchdogctl disable-legacy
sudo systemctl restart netwatchdog-dashboard
```

Do not stop or modify Smart Condo Dashboard on `8090`.

## OLED down

```bash
sudo systemctl restart netwatchdog-oled
sudo journalctl -u netwatchdog-oled -n 80 --no-pager -l
ls /dev/i2c-*
```

## Watchdog down

```bash
sudo systemctl restart netwatchdog
sudo journalctl -u netwatchdog -n 120 --no-pager -l
cat /run/netwatchdog/status.json
```

## Full service recovery

```bash
sudo netwatchdogctl selftest
sudo systemctl restart netwatchdog netwatchdog-dashboard netwatchdog-oled
sudo netwatchdogctl selftest
```

## Rollback

```bash
cd /opt/netwatchdog
sudo netwatchdogctl backup
sudo netwatchdogctl rollback <known-good-commit>
sudo sh install.sh
```
