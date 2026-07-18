#!/usr/bin/env python3
"""HOTFIX PACK 15: true standby mode for an unusable onboard Wi-Fi backup.

This wrapper preserves the existing NetWatchDog implementation and patches only the
onboard-backup policy. USB primary logic, route metrics, OLED, dashboard, status
writer, I2C, and port 8080 remain owned by the existing modules.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import netwatchdog as nw
from netwatchdog_common import append_event, load_config

_ALLOWED_MODES = {"active", "standby", "disabled"}
_raw = load_config()
_net = _raw.get("network", {}) if isinstance(_raw, dict) else {}
ONBOARD_BACKUP_MODE = str(_net.get("onboard_backup_mode", "standby")).strip().lower()
if ONBOARD_BACKUP_MODE not in _ALLOWED_MODES:
    ONBOARD_BACKUP_MODE = "standby"
STANDBY_PROBE_INTERVAL_SEC = max(60, int(_net.get("onboard_standby_probe_interval_sec", 300)))
RECOVERY_MAX_ATTEMPTS = max(1, min(3, int(_net.get("onboard_recovery_max_attempts", 2))))

# Runtime-only state. These attributes are intentionally attached to the existing
# WatchState instance so the status writer continues to publish one coherent state.
nw.STATE.onboard_backup_mode = ONBOARD_BACKUP_MODE
nw.STATE.onboard_required_for_failover = False
nw.STATE.onboard_recovery_attempts = 0
nw.STATE.onboard_last_recovery_result = None
nw.STATE.onboard_next_probe = None
nw.STATE.onboard_heal_suppressed_reason = "standby_usb_primary_healthy" if ONBOARD_BACKUP_MODE == "standby" else None
nw.STATE.onboard_recovery_attempted_episode = False

_original_observe_onboard = nw.observe_onboard
_original_wifi_state_machine = nw.wifi_state_machine
_original_onboard_diagnostics = nw.onboard_diagnostics
_original_init_route_state = nw.init_route_state


def _transition(state: str, health: Optional[nw.WifiHealth] = None) -> None:
    """Log only a real onboard state transition."""
    if state == nw.STATE.onboard_state:
        return
    nw.STATE.onboard_state = state
    connected = bool(health and health.connected)
    gateway = None if health is None else health.gateway_ms
    if state == "standby":
        nw.log.info("BACKUP_STANDBY")
    elif state in {"standby_available", "failover_ready"}:
        nw.log.info("BACKUP_AVAILABLE state=%s connected=%s gateway=%s", state, connected, gateway)
    elif state in {"standby_unavailable", "failover_unavailable"}:
        nw.log.warning("BACKUP_UNAVAILABLE state=%s connected=%s gateway=%s", state, connected, gateway)
    elif state == "recovery_in_progress":
        nw.log.warning("BACKUP_RECOVERY_STARTED")
    elif state == "recovery_required":
        nw.log.warning("BACKUP_RECOVERY_REQUIRED")


def _cancel_recovery_for_usb() -> None:
    nw.STATE.onboard_required_for_failover = False
    nw.STATE.onboard_recovery_attempted_episode = False
    nw.STATE.onboard_next_heal_allowed = None
    nw.STATE.onboard_backoff_step = 0
    nw.STATE.onboard_heal_times.clear()
    nw.STATE.onboard_heal_suppressed_reason = "standby_usb_primary_healthy"


def _record_standby_probe(health: nw.WifiHealth, now: float) -> nw.WifiHealth:
    nw.STATE.onboard_last_probe = now
    nw.STATE.onboard_last_health = health
    nw.STATE.onboard_next_probe = now + STANDBY_PROBE_INTERVAL_SEC
    if health.connected:
        _transition("standby_available", health)
    else:
        if nw.STATE.onboard_degraded_since is None:
            nw.STATE.onboard_degraded_since = now
        _transition("standby_unavailable", health)
    return health


def observe_onboard(usb: nw.WifiHealth, force: bool = False) -> nw.WifiHealth:
    if ONBOARD_BACKUP_MODE == "active":
        return _original_observe_onboard(usb, force)
    now = time.time()
    required = nw.STATE.active == "ONBOARD_PRIMARY" or not usb.good
    if ONBOARD_BACKUP_MODE == "disabled":
        nw.STATE.onboard_required_for_failover = False
        nw.STATE.onboard_heal_suppressed_reason = "backup_disabled"
        if force or nw.STATE.onboard_last_health is None or not nw.STATE.onboard_next_probe or now >= nw.STATE.onboard_next_probe:
            health = nw.onboard_health()
            nw.STATE.onboard_last_probe = now
            nw.STATE.onboard_last_health = health
            nw.STATE.onboard_next_probe = now + STANDBY_PROBE_INTERVAL_SEC
            _transition("standby_unavailable", health)
            return health
        return nw.STATE.onboard_last_health

    # Standby mode probes only every five minutes while USB is healthy. A forced
    # probe is reserved for failover threshold handling.
    nw.STATE.onboard_required_for_failover = required
    due = nw.STATE.onboard_next_probe is None or now >= nw.STATE.onboard_next_probe
    if force or required or due or nw.STATE.onboard_last_health is None:
        return _record_standby_probe(nw.onboard_health(), now)
    return nw.STATE.onboard_last_health


def _recover_onboard_for_failover() -> nw.WifiHealth:
    """Run one bounded recovery operation for the current USB-failure episode."""
    nw.STATE.onboard_required_for_failover = True
    nw.STATE.onboard_recovery_attempted_episode = True
    nw.STATE.onboard_heal_suppressed_reason = None
    _transition("recovery_in_progress", nw.STATE.onboard_last_health)
    append_event("Backup Recovery Started", "Onboard Wi-Fi required for failover", "warning")

    health = nw.STATE.onboard_last_health or nw.onboard_health()
    success = False
    attempts = 0
    for _ in range(RECOVERY_MAX_ATTEMPTS):
        attempts += 1
        nw.STATE.onboard_recovery_attempts += 1
        commands_ok = nw.run("systemctl restart netplan-wpa-wlan0.service")
        commands_ok = nw.run(f"ip link set {nw.CFG.onboard_if} down") and commands_ok
        time.sleep(2)
        commands_ok = nw.run(f"ip link set {nw.CFG.onboard_if} up") and commands_ok
        commands_ok = nw.run(f"networkctl reconfigure {nw.CFG.onboard_if}") and commands_ok
        time.sleep(2)
        health = nw.onboard_health()
        nw.STATE.onboard_last_probe = time.time()
        nw.STATE.onboard_last_health = health
        if commands_ok and health.good:
            success = True
            break

    nw.STATE.onboard_last_heal = time.time()
    nw.STATE.last_onboard_heal = nw.STATE.onboard_last_heal
    nw.STATE.onboard_next_heal_allowed = None
    nw.STATE.onboard_heal_times.clear()
    if success:
        nw.STATE.onboard_last_recovery_result = "succeeded"
        _transition("failover_ready", health)
        nw.log.info("BACKUP_RECOVERY_SUCCEEDED attempts=%s", attempts)
        append_event("Backup Recovery Succeeded", "Onboard Wi-Fi ready for failover")
    else:
        nw.STATE.onboard_last_recovery_result = "failed"
        nw.STATE.onboard_heal_suppressed_reason = "recovery_failed_until_usb_recovers"
        _transition("failover_unavailable", health)
        nw.log.error("BACKUP_RECOVERY_FAILED attempts=%s connected=%s gateway=%s", attempts, health.connected, health.gateway_ms)
        append_event("Backup Recovery Failed", "Onboard Wi-Fi unavailable for failover", "error")
    return health


def wifi_state_machine(usb: nw.WifiHealth, onboard: nw.WifiHealth) -> nw.WifiHealth:
    if ONBOARD_BACKUP_MODE == "active":
        return _original_wifi_state_machine(usb, onboard)

    nw.log_wifi_state_if_changed(usb, onboard)
    if nw.STATE.active == "USB_PRIMARY":
        if usb.good:
            nw.STATE.usb_fail = 0
            _cancel_recovery_for_usb()
            if not nw.verify_usb_primary():
                nw.log.warning("ROUTE_REPAIR -> USB")
                nw.set_usb_primary()
            if ONBOARD_BACKUP_MODE == "standby":
                _transition("standby_available" if onboard.connected else "standby_unavailable", onboard)
            return onboard

        nw.STATE.usb_fail += 1
        nw.log.warning("USB_FAIL %s/%s", nw.STATE.usb_fail, nw.CFG.wifi_fail_limit)
        if nw.STATE.usb_fail < nw.CFG.wifi_fail_limit:
            return onboard

        nw.heal_usb()
        if ONBOARD_BACKUP_MODE == "disabled":
            nw.STATE.onboard_heal_suppressed_reason = "backup_disabled"
            _transition("failover_unavailable", onboard)
            append_event("Gateway Lost", "USB failed and onboard backup is disabled", "error")
            return onboard

        nw.STATE.onboard_required_for_failover = True
        onboard = observe_onboard(usb, force=True)
        if onboard.good:
            _transition("failover_ready", onboard)
            nw.log.warning("FAILOVER USB -> ONBOARD")
            nw.set_onboard_primary()
            nw.STATE.usb_fail = 0
            nw.STATE.usb_recover = 0
            return onboard

        _transition("recovery_required", onboard)
        if not nw.STATE.onboard_recovery_attempted_episode:
            onboard = _recover_onboard_for_failover()
        if onboard.good:
            nw.log.warning("FAILOVER USB -> ONBOARD")
            nw.set_onboard_primary()
            nw.STATE.usb_fail = 0
            nw.STATE.usb_recover = 0
        else:
            append_event("Gateway Lost", "Both Wi-Fi links bad; onboard failover unavailable", "error")
            nw.log.error("BOTH_WIFI_BAD failover_unavailable")
        return onboard

    # Already on onboard primary. Keep existing failback thresholds and route safety,
    # but never start a perpetual recovery loop.
    if onboard.good:
        _transition("failover_ready", onboard)
        if not nw.verify_onboard_primary():
            nw.log.warning("ROUTE_REPAIR -> ONBOARD")
            nw.set_onboard_primary()
        if usb.good:
            nw.STATE.usb_recover += 1
            if nw.STATE.usb_recover >= nw.CFG.wifi_recover_limit:
                nw.log.warning("FAILBACK -> USB")
                nw.set_usb_primary()
                nw.STATE.usb_recover = 0
                nw.STATE.usb_fail = 0
                _cancel_recovery_for_usb()
                _transition("standby_available" if onboard.connected else "standby_unavailable", onboard)
        else:
            nw.STATE.usb_recover = 0
        return onboard

    if usb.good:
        nw.log.warning("FAILBACK ONBOARD -> USB")
        nw.set_usb_primary()
        _cancel_recovery_for_usb()
        _transition("standby_unavailable", onboard)
    else:
        _transition("failover_unavailable", onboard)
        append_event("Gateway Lost", "Both Wi-Fi links bad", "error")
    return onboard


def onboard_diagnostics() -> dict[str, Any]:
    diagnostics = _original_onboard_diagnostics()
    diagnostics.update({
        "onboard_backup_mode": ONBOARD_BACKUP_MODE,
        "onboard_state": nw.STATE.onboard_state,
        "onboard_required_for_failover": bool(nw.STATE.onboard_required_for_failover),
        "onboard_recovery_attempts": int(nw.STATE.onboard_recovery_attempts),
        "onboard_last_recovery_result": nw.STATE.onboard_last_recovery_result,
        "onboard_next_probe": int(nw.STATE.onboard_next_probe) if nw.STATE.onboard_next_probe else None,
        "onboard_heal_suppressed_reason": nw.STATE.onboard_heal_suppressed_reason,
    })
    return diagnostics


def init_route_state() -> None:
    _original_init_route_state()
    if ONBOARD_BACKUP_MODE == "standby" and nw.STATE.active == "USB_PRIMARY":
        _cancel_recovery_for_usb()
        _transition("standby")
    elif ONBOARD_BACKUP_MODE == "disabled":
        nw.STATE.onboard_heal_suppressed_reason = "backup_disabled"


nw.observe_onboard = observe_onboard
nw.wifi_state_machine = wifi_state_machine
nw.onboard_diagnostics = onboard_diagnostics
nw.init_route_state = init_route_state


if __name__ == "__main__":
    nw.main()
