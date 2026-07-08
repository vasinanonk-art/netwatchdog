"""Central NetWatchDog config loader.

Uses a tiny YAML subset parser to avoid adding PyYAML as a dependency.
Supports simple nested keys using indentation.
"""

import os
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("NWD_CONFIG", "/etc/netwatchdog/config.yaml"))

DEFAULTS = {
    "primary.interface": "wlx6c4cbcdb7033",
    "backup.interface": "wlan0",
    "gateway.host": "192.168.1.1",
    "internet.host": "1.1.1.1",
    "status.path": "/run/netwatchdog/status.json",
    "status.interval": "2",
    "event.log": "/var/log/netwatchdog/events.log",
    "oled.enabled": "true",
}


def _strip_value(value):
    value = value.strip()
    if value.startswith(('"', "'")) and value.endswith(('"', "'")):
        return value[1:-1]
    return value


def load_config(path=CONFIG_PATH):
    data = dict(DEFAULTS)
    if not path.exists():
        return data

    stack = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        level = indent // 2
        key_value = line.strip()

        if ":" not in key_value:
            continue

        key, value = key_value.split(":", 1)
        key = key.strip()
        value = value.strip()

        stack = stack[:level]
        if value == "":
            stack.append(key)
            continue

        full_key = ".".join(stack + [key])
        data[full_key] = _strip_value(value)

    return data


def get(config, key, default=""):
    return str(config.get(key, default))


def get_int(config, key, default=0):
    try:
        return int(float(config.get(key, default)))
    except Exception:
        return default


def get_float(config, key, default=0.0):
    try:
        return float(config.get(key, default))
    except Exception:
        return default


def get_bool(config, key, default=False):
    value = str(config.get(key, default)).lower()
    return value in ("1", "true", "yes", "on", "enabled")
