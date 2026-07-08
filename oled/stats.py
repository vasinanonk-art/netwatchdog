"""System stats for OLED dashboard."""

import os
import time


def cpu_percent():
    def read():
        vals = list(map(int, open("/proc/stat").readline().split()[1:]))
        idle = vals[3] + vals[4]
        total = sum(vals)
        return idle, total

    idle1, total1 = read()
    time.sleep(0.2)
    idle2, total2 = read()
    diff_total = max(1, total2 - total1)
    return int(100 * (1 - ((idle2 - idle1) / diff_total)))


def ram_percent():
    mem = {}
    for line in open("/proc/meminfo"):
        key, value = line.split(":")
        mem[key] = int(value.split()[0])
    return int(100 * (1 - mem["MemAvailable"] / mem["MemTotal"]))


def temp_c():
    for path in [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/class/thermal/thermal_zone1/temp",
    ]:
        if os.path.exists(path):
            return int(int(open(path).read().strip()) / 1000)
    return 0


def uptime_short():
    seconds = int(float(open("/proc/uptime").read().split()[0]))
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    if days:
        return f"UP {days}D {hours}H"
    mins = (seconds % 3600) // 60
    return f"UP {hours}H {mins}M"


def load_short():
    load1 = open("/proc/loadavg").read().split()[0]
    return f"Load {load1}"
