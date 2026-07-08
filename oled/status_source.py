"""Optional status.json reader for OLED.

OLED can use NetWatchDog core status when available, and safely fall back to
local checks when the file is missing or malformed.
"""

import json
import os

from . import config


def read_status():
    for path in config.STATUS_PATHS:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            return None
    return None


def get_str(data, key, default=""):
    if not data:
        return default
    value = data.get(key, default)
    return str(value) if value is not None else default


def get_bool(data, key, default=None):
    if not data or key not in data:
        return default
    value = data.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "ok", "up")
    return bool(value)


def get_int(data, key, default=0):
    if not data or key not in data:
        return default
    try:
        return int(float(data.get(key)))
    except Exception:
        return default
