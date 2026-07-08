#!/usr/bin/env python3
from __future__ import annotations

import json, os, shutil, subprocess, tempfile, time
from pathlib import Path
from typing import Any

VERSION = "5.1.0"
CONFIG_PATH = Path("/etc/netwatchdog/config.yaml")
RUN_DIR = Path("/run/netwatchdog")
DATA_DIR = Path("/var/lib/netwatchdog")
LOG_DIR = Path("/var/log/netwatchdog")
STATUS_PATH = RUN_DIR / "status.json"
HISTORY_PATH = DATA_DIR / "history.json"
EVENT_LOG_PATH = LOG_DIR / "events.jsonl"
BACKUP_DIR = DATA_DIR / "backups"
HISTORY_INTERVAL_SEC = 10
HISTORY_RETENTION_SEC = 86400

DEFAULT_CONFIG: dict[str, Any] = {
    "network": {"usb_if": "wlx6c4cbcdb7033", "usb_ip": "192.168.1.61", "onboard_if": "wlan0", "onboard_ip": "192.168.1.60", "gateway": "192.168.1.1", "internet_target": "1.1.1.1", "usb_metric": 100, "onboard_metric": 600, "wifi_fail_limit": 3, "wifi_recover_limit": 3, "heal_cooldown": 300},
    "watchdog": {"check_interval": 10, "service_fail_limit": 3, "service_heal_cooldown": 300, "watched_services": ["netwatchdog", "netwatchdog-dashboard", "netwatchdog-oled", "zerotier-one", "mosquitto", "presence", "smart-condo-dashboard", "condo-sensor", "lgtv-mqtt"], "control_services": ["netwatchdog", "netwatchdog-dashboard", "netwatchdog-oled"], "local_ports": [{"label": "mqtt", "host": "127.0.0.1", "port": 1883}, {"label": "dashboard", "host": "127.0.0.1", "port": 8090}]},
    "dashboard": {"host": "0.0.0.0", "port": 8090, "refresh_sec": 5},
    "oled": {"pixel_shift": True, "screen_saver_sec": 300, "night_brightness": 32, "day_brightness": 160, "popup_timeout_sec": 8},
}

def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in overlay.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out

def scalar(v: str) -> Any:
    v = v.strip().strip('"').strip("'")
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        return int(v)
    except ValueError:
        return v

def parse_config(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    section = ""
    list_key = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        item = line.strip()
        if indent == 0 and item.endswith(":"):
            section = item[:-1]
            root.setdefault(section, {})
            list_key = ""
            continue
        if not section:
            continue
        sec = root.setdefault(section, {})
        if not isinstance(sec, dict):
            continue
        if item.endswith(":"):
            list_key = item[:-1]
            sec[list_key] = [] if list_key in ("watched_services", "control_services", "local_ports") else {}
            continue
        if item.startswith("- ") and list_key:
            val = item[2:].strip()
            target = sec.setdefault(list_key, [])
            if isinstance(target, list):
                if ":" in val:
                    k, v = val.split(":", 1)
                    target.append({k.strip(): scalar(v)})
                else:
                    target.append(scalar(val))
            continue
        if ":" in item:
            k, v = item.split(":", 1)
            if list_key == "local_ports" and isinstance(sec.get(list_key), list) and sec[list_key] and isinstance(sec[list_key][-1], dict) and indent > 4:
                sec[list_key][-1][k.strip()] = scalar(v)
            else:
                list_key = ""
                sec[k.strip()] = scalar(v)
    return root

def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG
    try:
        return deep_merge(DEFAULT_CONFIG, parse_config(CONFIG_PATH.read_text(encoding="utf-8")))
    except OSError:
        return DEFAULT_CONFIG

def ensure_dirs() -> None:
    for p in (RUN_DIR, DATA_DIR, LOG_DIR, BACKUP_DIR):
        p.mkdir(parents=True, exist_ok=True)

def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":")); f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default

def append_event(event: str, detail: str = "", level: str = "info") -> None:
    ensure_dirs()
    with EVENT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": int(time.time()), "event": event, "detail": detail, "level": level}, ensure_ascii=False, separators=(",", ":")) + "\n")

def read_events(limit: int = 50) -> list[dict[str, Any]]:
    try:
        lines = EVENT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out

def update_history(sample: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_dirs()
    now = int(sample.get("ts", time.time()))
    hist = read_json(HISTORY_PATH, [])
    hist = hist if isinstance(hist, list) else []
    hist.append(sample)
    hist = [x for x in hist if int(x.get("ts", 0)) >= now - HISTORY_RETENTION_SEC]
    hist = hist[-(HISTORY_RETENTION_SEC // HISTORY_INTERVAL_SEC + 6):]
    atomic_write_json(HISTORY_PATH, hist)
    return hist

def cpu_percent() -> float | None:
    def read() -> tuple[int, int]:
        vals = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        return vals[3] + vals[4], sum(vals)
    try:
        i1, t1 = read(); time.sleep(0.05); i2, t2 = read()
        return round((1 - ((i2 - i1) / (t2 - t1))) * 100, 1) if t2 > t1 else None
    except Exception:
        return None

def memory_percent() -> float | None:
    try:
        data = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1); data[k] = int(v.strip().split()[0])
        return round((1 - data["MemAvailable"] / data["MemTotal"]) * 100, 1)
    except Exception:
        return None

def cpu_temp_c() -> float | None:
    for p in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")):
        try:
            v = int(p.read_text().strip()); return round(v / 1000, 1) if v > 1000 else float(v)
        except Exception:
            continue
    return None

def disk_percent(path: str = "/") -> float | None:
    try:
        u = shutil.disk_usage(path); return round((u.used / u.total) * 100, 1)
    except OSError:
        return None

def run_cmd(args: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return p.returncode, p.stdout.strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"

def git_commit(repo_dir: str = "/opt/netwatchdog") -> str:
    code, out = run_cmd(["git", "-C", repo_dir, "rev-parse", "--short", "HEAD"], 5)
    return out if code == 0 else "unknown"

def health_score(cpu: float | None, ram: float | None, temp: float | None, rssi: int | None, gw: float | None, net: float | None) -> dict[str, Any]:
    score, reasons = 100, []
    if net is None: score -= 25; reasons.append("Internet unstable")
    if gw is None: score -= 25; reasons.append("Gateway lost")
    if cpu is not None and cpu >= 85: score -= 15; reasons.append("CPU high")
    if ram is not None and ram >= 85: score -= 15; reasons.append("RAM high")
    if temp is not None and temp >= 75: score -= 15; reasons.append("CPU temp high")
    if rssi is not None and rssi < -70: score -= 10; reasons.append("RSSI poor")
    score = max(0, min(100, score))
    return {"score": score, "status": "OK" if score >= 85 else "DEGRADED" if score >= 70 else "CRITICAL", "reasons": reasons or ["Normal"]}
