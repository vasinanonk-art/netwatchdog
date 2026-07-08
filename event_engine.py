"""NetWatchDog event logging engine."""

from datetime import datetime
from pathlib import Path


class EventLogger:
    def __init__(self, log_path):
        self.path = Path(log_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event, **fields):
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        extras = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
        line = f"{ts} {event}"
        if extras:
            line += f" {extras}"
        with self.path.open("a") as f:
            f.write(line + "\n")


def tail(path, limit=50):
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(errors="ignore").splitlines()
    return lines[-limit:]
