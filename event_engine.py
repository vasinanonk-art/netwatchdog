"""NetWatchDog event logging engine."""

from __future__ import annotations

import json
import time
from pathlib import Path

EVENT_DEDUP_WINDOW_SEC = 60
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

    def _duplicate(self, payload):
        try:
            lines = self.path.read_text(encoding="utf-8", errors="ignore").splitlines()[-20:]
        except OSError:
            return False
        now = int(payload.get("ts", time.time()))
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if now - int(item.get("ts", 0)) > EVENT_DEDUP_WINDOW_SEC:
                return False
            if item.get("event") == payload.get("event") and item.get("detail", "") == payload.get("detail", ""):
                return True
        return False

    def write(self, event, **fields):
        name = EVENT_NAMES.get(str(event), str(event).replace("_", " ").title())
        payload = {"ts": int(time.time()), "event": name, "detail": "", "fields": fields}
        if "target" in fields:
            payload["detail"] = str(fields["target"])
        elif "mode" in fields:
            payload["detail"] = str(fields["mode"])
        elif "version" in fields:
            payload["detail"] = str(fields["version"])
        if self._duplicate(payload):
            return
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, separators=(",", ":")) + "\n")


def tail(path, limit=50):
    path = Path(path)
    if not path.exists():
        return []
    return path.read_text(errors="ignore").splitlines()[-limit:]
