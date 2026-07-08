#!/usr/bin/env python3
from __future__ import annotations

import json, os, tempfile, time
from pathlib import Path

RETENTION_SEC = 24 * 60 * 60
INTERVAL_SEC = 10


def read(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def write_atomic(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, separators=(",", ":")); f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def append(path, sample, now=None):
    now = int(now or time.time())
    sample = dict(sample); sample["ts"] = int(sample.get("ts", now))
    data = read(path); data.append(sample)
    data = [x for x in data if int(x.get("ts", 0)) >= now - RETENTION_SEC]
    data = data[-(RETENTION_SEC // INTERVAL_SEC + 6):]
    write_atomic(path, data)
    return data
