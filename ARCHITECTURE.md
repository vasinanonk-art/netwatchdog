# NetWatchDog Architecture

```text
/etc/netwatchdog/config.yaml
        |
        v
+------------------+    /run/netwatchdog/status.json    +------------------+
| netwatchdog      | ----------------------------------> | OLED Front Panel |
| status writer    |                                     +------------------+
| health engine    | ----------------------------------> +------------------+
| event engine     |                                     | Web Dashboard v2 |
| history engine   | ----------------------------------> +------------------+
| service recovery |                                     | Future REST API  |
+------------------+                                     +------------------+
        |                     |
        |                     +--> /var/lib/netwatchdog/history.json
        +------------------------> /var/log/netwatchdog/events.jsonl
```

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

`/var/lib/netwatchdog/history.json` is a 24-hour ring buffer. Each sample stores CPU, RAM, temp, RSSI, gateway ping, internet ping, and health.

## Event Contract

`/var/log/netwatchdog/events.jsonl` stores one JSON object per line. Human-readable events include Boot, Internet Lost, Gateway Lost, Failover, Restored, Service Restarted, Backup Created, Backup Restored, Updated, Rollback, and Self Test.

## Crash Recovery

systemd restarts `netwatchdog` and `netwatchdog-dashboard`. The watchdog also monitors watched services and restarts failed services after repeated failures with cooldown protection.
