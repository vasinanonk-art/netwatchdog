# NetWatchDog v5.1.1 LTS

Self-healing Wi-Fi, service watchdog, status writer, dashboard, history, backup, update and self-test tools for a TinkerBoard running 24/7.

## Design Rules

- Stability > features.
- Single source of truth: `/run/netwatchdog/status.json`.
- Low CPU/RAM: pure Python stdlib, no React, no SQLite, no new runtime framework.
- History uses a 24-hour ring buffer in `/var/lib/netwatchdog/history.json` with a hard limit of 8640 samples.
- Events are human readable JSONL in `/var/log/netwatchdog/events.jsonl` and duplicate events are suppressed for 60 seconds.
- Config is centralized at `/etc/netwatchdog/config.yaml`.

## Services

| Service | Purpose |
|---|---|
| `netwatchdog` | Wi-Fi failover, health, history, events, status writer, crash recovery for watched services |
| `netwatchdog-dashboard` | Pure Python dashboard v2 on port `8080` |

## Install

```bash
cd /opt
sudo rm -rf netwatchdog
git clone -b feature/oled-v1 https://github.com/vasinanonk-art/netwatchdog.git
cd netwatchdog
sudo ./install.sh
```

The installer restarts only NetWatchDog services whose installed files changed. It does not manage or restart Smart Condo Dashboard.

## Update

```bash
cd /opt/netwatchdog
git pull --ff-only
sudo ./install.sh
```

## Check

```bash
systemctl status netwatchdog --no-pager -l
systemctl status netwatchdog-dashboard --no-pager -l
journalctl -u netwatchdog -n 80 --no-pager -l
cat /run/netwatchdog/status.json
```

Dashboard:

```text
http://<tinkerboard-ip>:8080/
```

## Control

Only allowlisted systemd services can be restarted. No arbitrary shell execution.

```bash
sudo netwatchdogctl restart netwatchdog
sudo netwatchdogctl restart netwatchdog-dashboard
sudo netwatchdogctl restart netwatchdog-oled
```

## Backup / Restore

```bash
sudo netwatchdogctl backup
sudo netwatchdogctl restore /var/lib/netwatchdog/backups/netwatchdog-backup-YYYYMMDD-HHMMSS.tar.gz
```

Backups are verified after creation. Restore verifies the archive before applying it, writes files atomically, verifies restored files, and creates a rollback backup before restore. If post-restore verification fails, NetWatchDog attempts an automatic rollback.

## Update Manager

```bash
cd /opt/netwatchdog
sudo netwatchdogctl update info
sudo netwatchdogctl update pull
sudo netwatchdogctl rollback <commit_sha>
```

Rollback uses `git reset --hard <commit_sha>`. Blast radius: local uncommitted changes in `/opt/netwatchdog` are discarded.

## Self Test

```bash
sudo netwatchdogctl selftest
```

Checks OLED/I2C, disk, CPU temp, memory, Wi-Fi, gateway, internet, and systemd services.

## OLED Contract

OLED must consume `/run/netwatchdog/status.json`. v5.1 keeps that contract stable. Burn-in settings live in `/etc/netwatchdog/config.yaml` under `oled`.

If an OLED service exists as `netwatchdog-oled`, NetWatchDog monitors and restarts it after repeated failure.

## Tradeoffs / Failure Points

- JSON history is intentionally simple and low overhead. If power is cut during write, atomic replace protects the file, but the latest sample can be lost.
- Config parser supports the YAML subset used by this project. It avoids adding PyYAML to keep dependencies low.
- Dashboard restart control is allowlist-only. Any new controllable service must be added to `watchdog.control_services`.
- `rollback` is powerful and destructive to local uncommitted repo changes. Use only after backup.
