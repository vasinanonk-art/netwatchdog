#!/usr/bin/env python3
"""NetWatchDog shared runtime status writer.

Writes status.json for OLED/Web/API consumers.
Standalone and low-risk: it does not change routing, WiFi, or failover.
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from core_config import get, get_float, load_config
from event_engine import EventLogger
from health_engine import score as health_score

VERSION = "5.1.0-oled"


def run(cmd, timeout=2):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=timeout)
    except Exception:
        return ""


def ping_ms(host):
    out = run(["ping", "-c", "1", "-W", "1", host], timeout=2)
    for part in out.split():
        if part.startswith("time="):
            try:
                return int(float(part.split("=", 1)[1]))
            except ValueError:
                return None
    return None


def iface_up(iface):
    path = Path(f"/sys/class/net/{iface}/operstate")
    return path.exists() and path.read_text().strip() == "up"


def active_mode(primary_iface, backup_iface):
    if iface_up(primary_iface):
        return "PRIMARY"
    if iface_up(backup_iface):
        return "BACKUP"
    return "LINK FAIL"


def active_iface(mode, primary_iface, backup_iface):
    if mode == "PRIMARY":
        return primary_iface
    if mode == "BACKUP":
        return backup_iface
    return None


def ip_addr(iface):
    if not iface:
        return ""
    out = run(["ip", "-4", "addr", "show", iface])
    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
    return match.group(1) if match else ""


def wifi_rssi(iface):
    if not iface:
        return None
    out = run(["iw", "dev", iface, "link"])
    match = re.search(r"signal:\s*(-?\d+)", out)
    return int(match.group(1)) if match else None


def cpu_percent():
    def read_stat():
        vals = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:]))
        idle = vals[3] + vals[4]
        total = sum(vals)
        return idle, total

    idle1, total1 = read_stat()
    time.sleep(0.15)
    idle2, total2 = read_stat()
    total_delta = max(1, total2 - total1)
    return int(100 * (1 - ((idle2 - idle1) / total_delta)))


def ram_percent():
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":")
        mem[key] = int(value.split()[0])
    return int(100 * (1 - mem["MemAvailable"] / mem["MemTotal"]))


def temp_c():
    for p in ("/sys/class/thermal/thermal_zone0/temp", "/sys/class/thermal/thermal_zone1/temp"):
        path = Path(p)
        if path.exists():
            return int(int(path.read_text().strip()) / 1000)
    return 0


def uptime_sec():
    return int(float(Path("/proc/uptime").read_text().split()[0]))


def write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    tmp.replace(path)


def main():
    cfg = load_config()
    primary_iface = os.environ.get("NWD_PRIMARY_IFACE", get(cfg, "primary.interface"))
    backup_iface = os.environ.get("NWD_BACKUP_IFACE", get(cfg, "backup.interface"))
    gateway_host = os.environ.get("NWD_GATEWAY_HOST", get(cfg, "gateway.host"))
    internet_host = os.environ.get("NWD_INTERNET_HOST", get(cfg, "internet.host"))
    status_path = Path(os.environ.get("NWD_STATUS_PATH", get(cfg, "status.path")))
    event_log = os.environ.get("NWD_EVENT_LOG", get(cfg, "event.log"))
    interval_sec = float(os.environ.get("NWD_STATUS_INTERVAL", get_float(cfg, "status.interval", 2)))
    events = EventLogger(event_log)

    boot_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    failover_count = 0
    restore_count = 0
    retry = 0
    last_mode = None
    last_internet = None
    last_event = "BOOT"
    last_event_ts = boot_iso
    events.write("BOOT", version=VERSION)

    while True:
        mode = active_mode(primary_iface, backup_iface)
        iface = active_iface(mode, primary_iface, backup_iface)
        gw_ms = ping_ms(gateway_host)
        net_ms = ping_ms(internet_host)
        gateway_ok = gw_ms is not None
        internet_ok = net_ms is not None
        cpu = cpu_percent()
        ram = ram_percent()
        temp = temp_c()
        rssi = wifi_rssi(iface)
        ip = ip_addr(iface)
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if last_mode is not None and mode != last_mode:
            if mode == "BACKUP":
                failover_count += 1
                last_event = "FAILOVER"
            elif mode == "PRIMARY":
                restore_count += 1
                last_event = "RESTORED"
            else:
                last_event = "LINK FAIL"
            last_event_ts = now_iso
            events.write(last_event, mode=mode, iface=iface)

        if last_internet is not None and internet_ok != last_internet:
            last_event = "NET OK" if internet_ok else "NET LOST"
            last_event_ts = now_iso
            events.write(last_event, target=internet_host)

        retry = 0 if internet_ok else min(999, retry + 1)
        last_mode = mode
        last_internet = internet_ok
        health, health_reasons = health_score(gateway_ok, internet_ok, cpu, ram, temp, rssi, retry)

        data = {
            "version": VERSION,
            "mode": mode,
            "iface": iface or "",
            "gateway": gateway_ok,
            "internet": internet_ok,
            "gateway_ping": gw_ms,
            "internet_ping": net_ms,
            "last_ping": gw_ms if gw_ms is not None else -1,
            "retry": retry,
            "failover": failover_count,
            "restore": restore_count,
            "last_event": last_event,
            "last_event_at": last_event_ts,
            "boot": boot_iso,
            "uptime": uptime_sec(),
            "cpu": cpu,
            "ram": ram,
            "temp": temp,
            "ip": ip,
            "rssi": rssi,
            "health": health,
            "health_reasons": health_reasons,
            "updated_at": now_iso,
        }
        write_json_atomic(status_path, data)
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
