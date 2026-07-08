#!/usr/bin/env python3
"""NetWatchDog shared runtime status writer.

Writes /run/netwatchdog/status.json for OLED/Web/API consumers.
This is intentionally standalone and low-risk: it does not change routing,
WiFi, failover, or existing NetWatchDog behavior.
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "5.1.0-oled"
PRIMARY_IFACE = os.environ.get("NWD_PRIMARY_IFACE", "wlx6c4cbcdb7033")
BACKUP_IFACE = os.environ.get("NWD_BACKUP_IFACE", "wlan0")
GATEWAY_HOST = os.environ.get("NWD_GATEWAY_HOST", "192.168.1.1")
INTERNET_HOST = os.environ.get("NWD_INTERNET_HOST", "1.1.1.1")
STATUS_PATH = Path(os.environ.get("NWD_STATUS_PATH", "/run/netwatchdog/status.json"))
EVENT_LOG = Path(os.environ.get("NWD_EVENT_LOG", "/var/log/netwatchdog/events.log"))
INTERVAL_SEC = float(os.environ.get("NWD_STATUS_INTERVAL", "2"))


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


def active_mode():
    if iface_up(PRIMARY_IFACE):
        return "PRIMARY"
    if iface_up(BACKUP_IFACE):
        return "BACKUP"
    return "LINK FAIL"


def active_iface(mode):
    if mode == "PRIMARY":
        return PRIMARY_IFACE
    if mode == "BACKUP":
        return BACKUP_IFACE
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


def health_score(gateway_ok, internet_ok, cpu, ram, temp, rssi):
    score = 100
    if not gateway_ok:
        score -= 30
    if not internet_ok:
        score -= 35
    if cpu >= 90:
        score -= 10
    if ram >= 90:
        score -= 10
    if temp >= 75:
        score -= 10
    if rssi is not None and rssi < -75:
        score -= 5
    return max(0, min(100, score))


def write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    tmp.replace(path)


def log_event(event):
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    with EVENT_LOG.open("a") as f:
        f.write(f"{ts} {event}\n")


def main():
    boot_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    failover_count = 0
    restore_count = 0
    retry = 0
    last_mode = None
    last_internet = None
    last_event = "BOOT"
    last_event_ts = boot_iso

    while True:
        mode = active_mode()
        iface = active_iface(mode)
        gw_ms = ping_ms(GATEWAY_HOST)
        net_ms = ping_ms(INTERNET_HOST)
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
            log_event(last_event)

        if last_internet is not None and internet_ok != last_internet:
            last_event = "NET OK" if internet_ok else "NET LOST"
            last_event_ts = now_iso
            log_event(last_event)

        retry = 0 if internet_ok else min(999, retry + 1)
        last_mode = mode
        last_internet = internet_ok

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
            "health": health_score(gateway_ok, internet_ok, cpu, ram, temp, rssi),
            "updated_at": now_iso,
        }
        write_json_atomic(STATUS_PATH, data)
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
