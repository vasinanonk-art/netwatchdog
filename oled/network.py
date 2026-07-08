"""Network status helpers for OLED dashboard."""

import os
import re
import subprocess

from . import config


def ping_ok(host, timeout=1):
    try:
        return subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
    except Exception:
        return False


def ping_ms(host):
    try:
        out = subprocess.check_output(
            ["ping", "-c", "1", "-W", "1", host],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for part in out.split():
            if part.startswith("time="):
                return int(float(part.split("=", 1)[1]))
    except Exception:
        pass
    return None


def iface_up(name):
    path = f"/sys/class/net/{name}/operstate"
    return os.path.exists(path) and open(path).read().strip() == "up"


def active_link():
    if iface_up(config.PRIMARY_IFACE):
        return "PRIMARY"
    if iface_up(config.BACKUP_IFACE):
        return "BACKUP"
    return "LINK FAIL"


def active_iface():
    link = active_link()
    if link == "PRIMARY":
        return config.PRIMARY_IFACE
    if link == "BACKUP":
        return config.BACKUP_IFACE
    return None


def gateway_ok():
    return ping_ok(config.GATEWAY_HOST)


def internet_ok():
    return ping_ok(config.INTERNET_HOST)


def gateway_ping_line():
    ms = ping_ms(config.GATEWAY_HOST)
    return "GW --" if ms is None else f"GW {ms}ms"


def ip_addr(iface=None):
    iface = iface or active_iface()
    if not iface:
        return "IP --"
    try:
        out = subprocess.check_output(["ip", "-4", "addr", "show", iface], text=True)
        match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "IP --"


def wifi_rssi(iface=None):
    iface = iface or active_iface()
    if not iface:
        return None
    try:
        out = subprocess.check_output(["iw", "dev", iface, "link"], stderr=subprocess.DEVNULL, text=True)
        match = re.search(r"signal:\s*(-?\d+)", out)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return None


def wifi_rssi_line():
    rssi = wifi_rssi()
    return "RSSI --" if rssi is None else f"RSSI {rssi}dBm"
