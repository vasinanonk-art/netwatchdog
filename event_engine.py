"""NetWatchDog event logging engine."""

from __future__ import annotations

import json
import time
from pathlib import Path

EVENT_NAMES = {
    "BOOT": "Boot",
    "NET LOST": "Internet Lost",
    "NET OK": "Restored",
    "GW LOST": "Gateway Lost",
    "GW OK": "Restored",
    "FAILOVER": "Failover",
    "RESTORED": "Restored",
    "OLED RESTART": "OLED Restarted",
}


class EventLogger:
    def __init__(self, log_path):
        self.path = Path(log_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event, **fields):
        name = EVENT_NAMES.get(str(event), str(event).replace("_", " ").title())
        payload = {"ts": int(time.time()), "event": name, "detail": "", "fields": fields}
        if "target" in fields:
            payload["detail"] = str(fields["target"])
        elif "mode" in fields:
            payload["detail"] = str(fields["mode"])
        elif "version" in fields:
            payload["detail"] = str(fields["version"])
        with self.path.open("a") as f:
            f.write(json.dumps(payload, separators=(",", ":")) + "\n")


def tail(path, limit=50):
    path = Path(path)
    if not path.exists():
        return []
    return path.read_text(errors="ignore").splitlines()[-limit:]
