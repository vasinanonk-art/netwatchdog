# Backup Guide

Create a backup:

```bash
sudo netwatchdogctl backup
```

Backups are written to:

```text
/var/lib/netwatchdog/backups/
```

Included files:

- `/etc/netwatchdog/config.yaml`
- `/run/netwatchdog/status.json`
- `/var/lib/netwatchdog/history.json`
- `/var/log/netwatchdog/events.jsonl`

Restore:

```bash
sudo netwatchdogctl restore /var/lib/netwatchdog/backups/<backup-file>.tar.gz
sudo systemctl restart netwatchdog netwatchdog-dashboard netwatchdog-oled
```

Safety:

- Restore accepts only NetWatchDog allowlisted files.
- Restore does not touch Smart Condo Dashboard.
- Restore does not touch port `8090`.
