# NetWatchDog Architecture

```text
/etc/netwatchdog/config.yaml
        |
        v
+------------------+    /run/netwatchdog/status.json    +------------------+
| netwatchdog      | ----------------------------------> | OLED Front Panel |
| status writer    |                                     +------------------+
| health engine    | ----------------------------------> +------------------+
| event engine     |                                     | Dashboard v2     | :8080
| history engine   | ----------------------------------> +------------------+
| service recovery |                                     | Future REST API  |
+------------------+                                     +------------------+
        |                     |
        |                     +--> /var/lib/netwatchdog/history.json
        +------------------------> /var/log/netwatchdog/events.jsonl

Smart Condo Dashboard is external to NetWatchDog and owns :8090.
NetWatchDog must not bind, stop, restart or reconfigure :8090.
```

## Services

Current NetWatchDog services:

- `netwatchdog.service`
- `netwatchdog-dashboard.service`
- `netwatchdog-oled.service`

Legacy NetWatchDog services that must remain disabled:

- `netwatchdog-web.service`
- `netwatchdog-status.service`

## Data Contract

`/run/netwatchdog/status.json` contains:

- `version`
- `git_commit`
- `ts`
- `uptime_sec`
- `active`
- `route`
- `health.score`
- `health.status`
- `health.reasons`
- `metrics.cpu`
- `metrics.ram`
- `metrics.temp`
- `metrics.disk`
- `network.usb`
- `network.onboard`
- `network.internet_ms`
- `services`
- `ports`

## History Contract

`/var/lib/netwatchdog/history.json` is a 24-hour ring buffer. Each sample stores CPU, RAM, temp, RSSI, gateway ping, internet ping, and health. Writes are atomic.

## Event Contract

`/var/log/netwatchdog/events.jsonl` stores one JSON object per line. Human-readable events include Boot, Internet Lost, Gateway Lost, Failover, Restored, Service Restarted, Backup Created, Backup Restored, Updated, Rollback, Self Test and Legacy Services Disabled.

## Crash Recovery

systemd restarts `netwatchdog`, `netwatchdog-dashboard`, and `netwatchdog-oled`. The watchdog monitors allowed NetWatchDog services and restarts failed services after repeated failures with cooldown protection.

## OLED Burn Protection

OLED keeps the existing layout and adds dirty page updates, pixel shift, short blank screen saver windows, night brightness, popup timeout and adaptive text fitting.
