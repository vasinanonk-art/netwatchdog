#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, os, shutil, sys, tarfile, tempfile, time
from pathlib import Path

APP_DIR = Path("/opt/netwatchdog")
app_dir = str(APP_DIR)
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from netwatchdog_common import BACKUP_DIR, CONFIG_PATH, EVENT_LOG_PATH, HISTORY_PATH, STATUS_PATH, VERSION, append_event, cpu_temp_c, disk_percent, ensure_dirs, git_commit, load_config, memory_percent, read_json, run_cmd

ALLOWED_MEMBERS = {
    "etc/netwatchdog/config.yaml": CONFIG_PATH,
    "var/log/netwatchdog/events.jsonl": EVENT_LOG_PATH,
    "var/lib/netwatchdog/history.json": HISTORY_PATH,
    "run/netwatchdog/status.json": STATUS_PATH,
}
JSON_MEMBERS = {"var/lib/netwatchdog/history.json", "run/netwatchdog/status.json"}
JSONL_MEMBERS = {"var/log/netwatchdog/events.jsonl"}
SUPPORT_DIR = Path("/var/lib/netwatchdog/support")


def out(payload: object) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2)); return 0


def restart(service: str) -> int:
    allowed = set(load_config()["watchdog"].get("control_services", []))
    if service not in allowed: return out({"ok": False, "error": "service not allowed", "service": service})
    code, text = run_cmd(["systemctl", "restart", service], 20); append_event("Service Restarted", service, "warning" if code else "info")
    return out({"ok": code == 0, "service": service, "output": text})


def _validate_json_bytes(name: str, data: bytes) -> tuple[bool, str]:
    try:
        if name in JSON_MEMBERS:
            json.loads(data.decode("utf-8"))
        elif name in JSONL_MEMBERS:
            for line in data.decode("utf-8").splitlines():
                if line.strip():
                    json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, f"invalid JSON in {name}: {exc}"
    return True, ""


def verify_archive(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "backup not found"
    try:
        seen: set[str] = set()
        with tarfile.open(path, "r:gz") as tar:
            members = tar.getmembers()
            if not members:
                return False, "backup is empty"
            for member in members:
                if member.name not in ALLOWED_MEMBERS:
                    return False, f"unsafe member: {member.name}"
                if member.name in seen:
                    return False, f"duplicate member: {member.name}"
                if not member.isfile():
                    return False, f"unsupported member type: {member.name}"
                seen.add(member.name)
                extracted = tar.extractfile(member)
                if extracted is None:
                    return False, f"cannot read member: {member.name}"
                data = extracted.read()
                ok, err = _validate_json_bytes(member.name, data)
                if not ok:
                    return False, err
    except (tarfile.TarError, OSError, EOFError) as exc:
        return False, f"corrupt backup: {exc}"
    return True, ""


def _create_backup_archive(target: Path) -> tuple[bool, str]:
    ensure_dirs(); target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            for p in (CONFIG_PATH, EVENT_LOG_PATH, HISTORY_PATH, STATUS_PATH):
                if p.exists():
                    tar.add(p, arcname=str(p).lstrip("/"))
        ok, err = verify_archive(tmp)
        if not ok:
            return False, err
        os.replace(tmp, target)
        return True, ""
    finally:
        if tmp.exists():
            tmp.unlink()


def backup() -> int:
    target = BACKUP_DIR / f"netwatchdog-backup-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    ok, err = _create_backup_archive(target)
    if not ok:
        append_event("Backup Failed", err, "error")
        return out({"ok": False, "error": err})
    append_event("Backup Created", str(target)); return out({"ok": True, "backup": str(target), "verified": True})


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp_name, path)
        try:
            dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _read_archive_payload(path: Path) -> tuple[dict[Path, bytes] | None, str]:
    ok, err = verify_archive(path)
    if not ok:
        return None, err
    payload: dict[Path, bytes] = {}
    with tarfile.open(path, "r:gz") as tar:
        for member in tar.getmembers():
            extracted = tar.extractfile(member)
            if extracted is None:
                return None, f"cannot read member: {member.name}"
            payload[ALLOWED_MEMBERS[member.name]] = extracted.read()
    return payload, ""


def _verify_files_after_restore(payload: dict[Path, bytes]) -> tuple[bool, str]:
    for path, expected in payload.items():
        try:
            actual = path.read_bytes()
        except OSError as exc:
            return False, f"restore verification failed for {path}: {exc}"
        if actual != expected:
            return False, f"restore verification mismatch: {path}"
    return True, ""


def _restore_payload(payload: dict[Path, bytes]) -> tuple[bool, str]:
    try:
        for path, data in payload.items():
            _atomic_write(path, data)
    except OSError as exc:
        return False, f"atomic restore failed: {exc}"
    return _verify_files_after_restore(payload)


def restore(archive: str) -> int:
    path = Path(archive)
    payload, err = _read_archive_payload(path)
    if payload is None:
        append_event("Restore Aborted", err, "error")
        return out({"ok": False, "error": err})

    rollback_archive = BACKUP_DIR / f"pre-restore-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    ok, err = _create_backup_archive(rollback_archive)
    if not ok:
        append_event("Restore Aborted", f"rollback backup failed: {err}", "error")
        return out({"ok": False, "error": f"rollback backup failed: {err}"})

    ok, err = _restore_payload(payload)
    if not ok:
        rollback_payload, rollback_err = _read_archive_payload(rollback_archive)
        if rollback_payload is not None:
            rb_ok, rb_err = _restore_payload(rollback_payload)
            detail = "rollback applied" if rb_ok else f"rollback failed: {rb_err}"
        else:
            detail = f"rollback unavailable: {rollback_err}"
        append_event("Restore Failed", f"{err}; {detail}", "error")
        return out({"ok": False, "error": err, "rollback": detail, "rollback_backup": str(rollback_archive)})

    append_event("Backup Restored", archive, "warning"); return out({"ok": True, "restored": archive, "verified": True, "rollback_backup": str(rollback_archive)})


def update_info() -> int:
    fc, fo = run_cmd(["git", "fetch", "--all", "--prune"], 60); cc, cur = run_cmd(["git", "rev-parse", "--short", "HEAD"], 5); lc, lat = run_cmd(["git", "rev-parse", "--short", "@{u}"], 5)
    return out({"ok": fc == 0 and cc == 0, "current": cur, "latest": lat if lc == 0 else "unknown", "fetch": fo})


def pull() -> int:
    _, before = run_cmd(["git", "rev-parse", "--short", "HEAD"], 5); code, text = run_cmd(["git", "pull", "--ff-only"], 120); _, after = run_cmd(["git", "rev-parse", "--short", "HEAD"], 5)
    if code == 0: append_event("Updated", f"{before} -> {after}")
    return out({"ok": code == 0, "before": before, "after": after, "output": text})


def rollback(commit: str) -> int:
    if not commit or any(c not in "0123456789abcdefABCDEF" for c in commit): return out({"ok": False, "error": "commit must be hex"})
    code, text = run_cmd(["git", "reset", "--hard", commit], 60)
    if code == 0: append_event("Rollback", commit, "warning")
    return out({"ok": code == 0, "commit": commit, "output": text})


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
        "i2c": Path("/dev/i2c-1").exists() or Path("/dev/i2c-0").exists(),
    }
    checks["oled"] = checks["i2c"]
    svc = {str(s): run_cmd(["systemctl", "is-active", "--quiet", str(s)], 5)[0] == 0 for s in services}
    checks["systemd_services"] = all(svc.values()) if svc else None
    ok = all(v is True or v is None for v in checks.values()); append_event("Self Test", "PASS" if ok else "FAIL", "info" if ok else "warning")
    return out({"ok": ok, "checks": checks, "services": svc, "status": read_json(STATUS_PATH, {})})


def _pass_fail(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _format_uptime(seconds: object) -> str:
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        return "unknown"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"


def doctor() -> int:
    status = read_json(STATUS_PATH, {})
    status = status if isinstance(status, dict) else {}
    network = status.get("network") if isinstance(status.get("network"), dict) else {}
    usb = network.get("usb") if isinstance(network.get("usb"), dict) else {}
    onboard = network.get("onboard") if isinstance(network.get("onboard"), dict) else {}
    health = status.get("health") if isinstance(status.get("health"), dict) else {}
    services = status.get("services") if isinstance(status.get("services"), dict) else {}

    usb_ok = bool(usb.get("connected"))
    onboard_ok = bool(onboard.get("connected"))
    gateway_ok = usb.get("gateway_ms") is not None if status.get("active") == "USB_PRIMARY" else onboard.get("gateway_ms") is not None
    internet_ok = network.get("internet_ms") is not None
    oled_ok = run_cmd(["systemctl", "is-active", "--quiet", "netwatchdog-oled"], 5)[0] == 0
    dashboard_ok = run_cmd(["systemctl", "is-active", "--quiet", "netwatchdog-dashboard"], 5)[0] == 0
    services_ok = all(value == "active" for value in services.values()) if services else False
    health_ok = health.get("status") in {"OK", "DEGRADED"}
    overall = all((usb_ok, onboard_ok, gateway_ok, internet_ok, oled_ok, dashboard_ok, services_ok, health_ok))

    print(f"Version: {status.get('version', VERSION)}")
    print(f"Git Commit: {status.get('git_commit', git_commit())}")
    print(f"Uptime: {_format_uptime(status.get('uptime_sec'))}")
    print(f"Health: {health.get('status', 'unknown')} ({health.get('score', 'unknown')})")
    print(f"USB WiFi: {_pass_fail(usb_ok)}")
    print(f"Onboard WiFi: {_pass_fail(onboard_ok)}")
    print(f"Gateway: {_pass_fail(gateway_ok)}")
    print(f"Internet: {_pass_fail(internet_ok)}")
    print(f"OLED: {_pass_fail(oled_ok)}")
    print(f"Dashboard: {_pass_fail(dashboard_ok)}")
    print(f"Services: {_pass_fail(services_ok)}")
    print(f"Overall: {_pass_fail(overall)}")
    return 0 if overall else 1


def _write_command_output(path: Path, args: list[str], timeout: int = 30) -> None:
    code, text = run_cmd(args, timeout)
    path.write_text(f"command: {' '.join(args)}\nexit_code: {code}\n\n{text}\n", encoding="utf-8")


def support() -> int:
    SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = SUPPORT_DIR / f"support-{stamp}.tar.gz"
    work = Path(tempfile.mkdtemp(prefix=f"support-{stamp}-", dir=str(SUPPORT_DIR)))
    try:
        files = {
            STATUS_PATH: "status.json",
            HISTORY_PATH: "history.json",
            EVENT_LOG_PATH: "events.jsonl",
            CONFIG_PATH: "config.yaml",
        }
        for source, name in files.items():
            if source.exists():
                shutil.copy2(source, work / name)

        _write_command_output(work / "journal-netwatchdog.txt", ["journalctl", "-u", "netwatchdog", "-n", "500", "--no-pager", "-l"], 30)
        _write_command_output(work / "journal-dashboard.txt", ["journalctl", "-u", "netwatchdog-dashboard", "-n", "500", "--no-pager", "-l"], 30)
        _write_command_output(work / "journal-oled.txt", ["journalctl", "-u", "netwatchdog-oled", "-n", "500", "--no-pager", "-l"], 30)

        status_parts = []
        for service in ("netwatchdog", "netwatchdog-dashboard", "netwatchdog-oled"):
            code, text = run_cmd(["systemctl", "status", service, "--no-pager", "-l"], 20)
            status_parts.append(f"===== {service} (exit {code}) =====\n{text}\n")
        (work / "systemctl-status.txt").write_text("\n".join(status_parts), encoding="utf-8")

        _write_command_output(work / "ip-route.txt", ["ip", "route"], 10)
        _write_command_output(work / "ip-addr.txt", ["ip", "addr"], 10)
        _write_command_output(work / "iw-dev.txt", ["iw", "dev"], 10)
        _write_command_output(work / "uname.txt", ["uname", "-a"], 10)
        _write_command_output(work / "uptime.txt", ["uptime"], 10)

        with tarfile.open(target, "w:gz") as tar:
            for item in sorted(work.iterdir()):
                tar.add(item, arcname=item.name)
    except (OSError, tarfile.TarError) as exc:
        print(f"Support bundle failed: {exc}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"Support archive: {target}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="netwatchdogctl"); sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("restart"); r.add_argument("service")
    sub.add_parser("backup"); rs = sub.add_parser("restore"); rs.add_argument("archive")
    u = sub.add_parser("update"); u.add_argument("action", choices=["info", "pull"])
    rb = sub.add_parser("rollback"); rb.add_argument("commit")
    sub.add_parser("selftest"); sub.add_parser("doctor"); sub.add_parser("support")
    a = p.parse_args()
    if a.cmd == "restart": return restart(a.service)
    if a.cmd == "backup": return backup()
    if a.cmd == "restore": return restore(a.archive)
    if a.cmd == "update": return update_info() if a.action == "info" else pull()
    if a.cmd == "rollback": return rollback(a.commit)
    if a.cmd == "selftest": return selftest()
    if a.cmd == "doctor": return doctor()
    if a.cmd == "support": return support()
    return 2
if __name__ == "__main__": sys.exit(main())
