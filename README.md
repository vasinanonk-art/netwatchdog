# NetWatchDog v5.1 Stable

Self-healing Wi-Fi, service watchdog, OLED front panel, dashboard, history, backup, update and self-test tools for a TinkerBoard running 24/7.

## Hard Rules

- `8080` = NetWatchDog Dashboard.
- `8090` = Smart Condo Dashboard. Do not bind, stop, restart, reconfigure, or modify it.
- Single source of truth: `/run/netwatchdog/status.json`.
- No React, no SQLite, no unnecessary runtime dependency.
- History uses a 24-hour ring buffer in `/var/lib/netwatchdog/history.json`.
- Events are human readable JSONL in `/var/log/netwatchdog/events.jsonl`.
- Config is centralized at `/etc/netwatchdog/config.yaml`.

## Services

| Service | Purpose |
|---|---|
| `netwatchdog` | Wi-Fi failover, health, history, events, status writer, crash recovery for watched services |
| `netwatchdog-dashboard` | Pure Python dashboard v2 on port `8080` |
| `netwatchdog-oled` | OLED front panel with burn-in protection |

Legacy services are disabled by installer and must not be recreated:

- `netwatchdog-web`
- `netwatchdog-status`

## Install

```bash
cd /opt
sudo rm -rf netwatchdog
git clone -b feature/oled-v1 https://github.com/vasinanonk-art/netwatchdog.git
cd netwatchdog
sudo sh install.sh
```

## Update

```bash
cd /opt/netwatchdog
git pull --ff-only
sudo sh install.sh
```

## Check

```bash
systemctl status netwatchdog --no-pager -l
systemctl status netwatchdog-dashboard --no-pager -l
systemctl status netwatchdog-oled --no-pager -l
ss -lntp | grep -E '8080|8090'
cat /run/netwatchdog/status.json
```

Expected port ownership:

```text
8080 NetWatchDog Dashboard
8090 Smart Condo Dashboard
```

Dashboard:

```text
http://<tinkerboard-ip>:8080/
```

## Control

Only allowlisted NetWatchDog services can be restarted. Smart Condo Dashboard is blocked.

```bash
sudo netwatchdogctl restart netwatchdog
sudo netwatchdogctl restart netwatchdog-dashboard
sudo netwatchdogctl restart netwatchdog-oled
sudo netwatchdogctl disable-legacy
```

## Backup / Restore

```bash
sudo netwatchdogctl backup
sudo netwatchdogctl restore /var/lib/netwatchdog/backups/netwatchdog-backup-YYYYMMDD-HHMMSS.tar.gz
```

Restore only accepts the NetWatchDog config, status, history and events paths.

## Update Manager

```bash
cd /opt/netwatchdog
sudo netwatchdogctl update info
sudo netwatchdogctl update pull
sudo netwatchdogctl rollback <commit_sha>
```

Rollback refuses to run when the working tree is dirty. Blast radius if used: repo files in `/opt/netwatchdog` are reset to the selected commit.

## Self Test

```bash
sudo netwatchdogctl selftest
```

Checks OLED/I2C, disk, CPU temp, memory, USB Wi-Fi, onboard Wi-Fi, gateway, internet, legacy services disabled, Smart Condo Dashboard still active, and monitored systemd services.

## OLED Burn Protection

OLED keeps the existing layout and adds:

- Dirty page updates.
- Pixel shift.
- Short blank screen saver cycle.
- Night brightness schedule.
- Popup timeout.
- Adaptive text truncation for long interface names.

Config keys live under `oled` in `/etc/netwatchdog/config.yaml`.

## Tradeoffs / Failure Points

- JSON history is intentionally simple and low overhead. Atomic writes protect the file, but the latest sample can still be lost on hard power cut.
- Config parser supports the YAML subset used by this project. It avoids PyYAML to keep dependencies low.
- Dashboard control is allowlist-only. New controllable NetWatchDog services must be added to `watchdog.control_services`.
- Update and rollback require a clean git working tree for safety.
