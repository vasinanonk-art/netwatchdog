#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, sys, tarfile, time
from pathlib import Path
from netwatchdog_common import BACKUP_DIR, CONFIG_PATH, EVENT_LOG_PATH, HISTORY_PATH, STATUS_PATH, append_event, cpu_temp_c, disk_percent, ensure_dirs, load_config, memory_percent, read_json, run_cmd

SMART_CONDO_SERVICE = "smart-condo-dashboard"
LEGACY_SERVICES = {"netwatchdog-web", "netwatchdog-status"}
RESTORE_TARGETS = {
    "etc/netwatchdog/config.yaml": Path("/etc/netwatchdog/config.yaml"),
    "var/log/netwatchdog/events.jsonl": Path("/var/log/netwatchdog/events.jsonl"),
    "var/lib/netwatchdog/history.json": Path("/var/lib/netwatchdog/history.json"),
    "run/netwatchdog/status.json": Path("/run/netwatchdog/status.json"),
}

def out(payload: object) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2)); return 0

def service_active(service: str) -> bool:
    return run_cmd(["systemctl", "is-active", "--quiet", service], 5)[0] == 0

def restart(service: str) -> int:
    if service.startswith(SMART_CONDO_SERVICE):
        return out({"ok": False, "error": "Smart Condo Dashboard is reserved", "service": service})
    allowed = set(load_config()["watchdog"].get("control_services", []))
    if service not in allowed: return out({"ok": False, "error": "service not allowed", "service": service})
    code, text = run_cmd(["systemctl", "restart", service], 20); append_event("Service Restarted", service, "warning" if code else "info")
    return out({"ok": code == 0, "service": service, "output": text})

def backup() -> int:
    ensure_dirs(); target = BACKUP_DIR / f"netwatchdog-backup-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    with tarfile.open(target, "w:gz") as tar:
        for p in (CONFIG_PATH, EVENT_LOG_PATH, HISTORY_PATH, STATUS_PATH):
            if p.exists(): tar.add(p, arcname=str(p).lstrip("/"))
    append_event("Backup Created", str(target)); return out({"ok": True, "backup": str(target)})

def restore(archive: str) -> int:
    path = Path(archive)
    if not path.is_file(): return out({"ok": False, "error": "backup not found"})
    restored = []
    with tarfile.open(path, "r:gz") as tar:
        names = set(tar.getnames())
        unsafe = sorted(n for n in names if n not in RESTORE_TARGETS)
        if unsafe: return out({"ok": False, "error": "unsafe backup members", "members": unsafe})
        for name, target in RESTORE_TARGETS.items():
            member = tar.getmember(name) if name in names else None
            if not member: continue
            src = tar.extractfile(member)
            if src is None or member.isdir() or member.issym() or member.islnk():
                return out({"ok": False, "error": f"unsafe member: {name}"})
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(src.read())
            restored.append(str(target))
    append_event("Backup Restored", archive, "warning"); return out({"ok": True, "restored": restored})

def update_info() -> int:
    fc, fo = run_cmd(["git", "fetch", "--all", "--prune"], 60); cc, cur = run_cmd(["git", "rev-parse", "--short", "HEAD"], 5); lc, lat = run_cmd(["git", "rev-parse", "--short", "@{u}"], 5)
    return out({"ok": fc == 0 and cc == 0, "current": cur, "latest": lat if lc == 0 else "unknown", "fetch": fo})

def pull() -> int:
    _, before = run_cmd(["git", "rev-parse", "--short", "HEAD"], 5); code, text = run_cmd(["git", "pull", "--ff-only"], 120); _, after = run_cmd(["git", "rev-parse", "--short", "HEAD"], 5)
    if code == 0: append_event("Updated", f"{before} -> {after}")
    return out({"ok": code == 0, "before": before, "after": after, "output": text})

def rollback(commit: str) -> int:
    if not commit or any(c not in "0123456789abcdefABCDEF" for c in commit): return out({"ok": False, "error": "commit must be hex"})
    dirty_code, dirty = run_cmd(["git", "status", "--porcelain"], 5)
    if dirty_code != 0 or dirty: return out({"ok": False, "error": "working tree is not clean", "status": dirty})
    code, text = run_cmd(["git", "reset", "--hard", commit], 60)
    if code == 0: append_event("Rollback", commit, "warning")
    return out({"ok": code == 0, "commit": commit, "output": text})

def disable_legacy() -> int:
    result = {}
    for service in sorted(LEGACY_SERVICES):
        code, text = run_cmd(["systemctl", "disable", "--now", service], 20)
        result[service] = {"ok": code == 0 or "not loaded" in text.lower() or "does not exist" in text.lower(), "output": text}
    append_event("Legacy Services Disabled", ", ".join(sorted(LEGACY_SERVICES)))
    return out({"ok": all(x["ok"] for x in result.values()), "services": result})

def selftest() -> int:
    cfg = load_config(); net = cfg["network"]; services = cfg["watchdog"].get("watched_services", [])
    checks = {
        "disk": (disk_percent("/") or 100) < 90,
        "cpu_temp": (cpu_temp_c() or 0) < 80,
        "memory": (memory_percent() or 100) < 90,
        "wifi_usb": run_cmd(["iw", "dev", str(net["usb_if"]), "link"], 5)[0] == 0,
        "wifi_onboard": run_cmd(["iw", "dev", str(net["onboard_if"]), "link"], 5)[0] == 0,
        "gateway": run_cmd(["ping", "-c", "1", "-W", "2", str(net["gateway"])], 5)[0] == 0,
        "internet": run_cmd(["ping", "-c", "1", "-W", "2", str(net["internet_target"])], 5)[0] == 0,
        "i2c": any(Path(p).exists() for p in ("/dev/i2c-0", "/dev/i2c-1", "/dev/i2c-4")),
        "oled": service_active("netwatchdog-oled"),
        "dashboard": service_active("netwatchdog-dashboard"),
        "legacy_services_disabled": not any(service_active(s) for s in LEGACY_SERVICES),
        "smart_condo_untouched": service_active(SMART_CONDO_SERVICE),
    }
    svc = {str(s): service_active(str(s)) for s in services if not str(s).startswith(SMART_CONDO_SERVICE)}
    checks["systemd_services"] = all(svc.values()) if svc else None
    ok = all(v is True or v is None for v in checks.values()); append_event("Self Test", "PASS" if ok else "FAIL", "info" if ok else "warning")
    return out({"ok": ok, "checks": checks, "services": svc, "status": read_json(STATUS_PATH, {})})

def main() -> int:
    p = argparse.ArgumentParser(prog="netwatchdogctl"); sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("restart"); r.add_argument("service")
    sub.add_parser("backup"); rs = sub.add_parser("restore"); rs.add_argument("archive")
    u = sub.add_parser("update"); u.add_argument("action", choices=["info", "pull"])
    rb = sub.add_parser("rollback"); rb.add_argument("commit"); sub.add_parser("selftest"); sub.add_parser("disable-legacy")
    a = p.parse_args()
    if a.cmd == "restart": return restart(a.service)
    if a.cmd == "backup": return backup()
    if a.cmd == "restore": return restore(a.archive)
    if a.cmd == "update": return update_info() if a.action == "info" else pull()
    if a.cmd == "rollback": return rollback(a.commit)
    if a.cmd == "selftest": return selftest()
    if a.cmd == "disable-legacy": return disable_legacy()
    return 2
if __name__ == "__main__": sys.exit(main())
