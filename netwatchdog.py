#!/usr/bin/env python3
"""
NetWatchdog v5
USB Wi-Fi primary / onboard Wi-Fi backup watchdog for TinkerBoard.

Design:
- USB adapter is the preferred route.
- Onboard Wi-Fi is standby/failover.
- Health checks are conservative: Wi-Fi link + gateway ping.
- Services are checked and restarted only after repeated failure.
- All logs go to journald via stdout when run as systemd.
"""

from __future__ import annotations

import logging
import re
import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

VERSION = "5.0.0"


@dataclass(frozen=True)
class Config:
    usb_if: str = "wlx6c4cbcdb7033"
    usb_ip: str = "192.168.1.61"
    onboard_if: str = "wlan0"
    onboard_ip: str = "192.168.1.60"
    gateway: str = "192.168.1.1"
    usb_metric: int = 100
    onboard_metric: int = 600
    check_interval: int = 30
    wifi_fail_limit: int = 3
    wifi_recover_limit: int = 3
    heal_cooldown: int = 300
    service_fail_limit: int = 3
    service_heal_cooldown: int = 300
    watched_services: tuple[str, ...] = (
        "zerotier-one",
        "mosquitto",
        "presence",
        "smart-condo-dashboard",
        "condo-sensor",
        "lgtv-mqtt",
    )
    local_ports: tuple[tuple[str, str, int], ...] = (
        ("mqtt", "127.0.0.1", 1883),
        ("dashboard", "127.0.0.1", 8090),
    )


@dataclass
class WifiHealth:
    iface: str
    connected: bool
    gateway_ms: Optional[float]
    signal_dbm: Optional[int]
    freq_mhz: Optional[float]
    score: int

    @property
    def good(self) -> bool:
        return self.connected and self.gateway_ms is not None and self.score >= 70


@dataclass
class WatchState:
    active: str = "USB_PRIMARY"
    usb_fail: int = 0
    usb_recover: int = 0
    onboard_fail: int = 0
    last_usb_heal: float = 0
    last_onboard_heal: float = 0
    service_fail: Dict[str, int] = field(default_factory=dict)
    last_service_heal: Dict[str, float] = field(default_factory=dict)


CFG = Config()
STATE = WatchState()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("netwatchdog")


def run(cmd: str, timeout: int = 10) -> bool:
    try:
        return subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        ).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def output(cmd: str, timeout: int = 10) -> str:
    try:
        return subprocess.run(
            cmd,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        ).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def tcp(host: str, port: int, timeout: int = 2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def iw_link(iface: str) -> str:
    return output(f"iw dev {iface} link", timeout=5)


def wifi_connected(iface: str) -> bool:
    return "Connected to" in iw_link(iface)


def wifi_signal(iface: str) -> Optional[int]:
    match = re.search(r"signal:\s*(-?\d+)", iw_link(iface))
    return int(match.group(1)) if match else None


def wifi_freq(iface: str) -> Optional[float]:
    match = re.search(r"freq:\s*([0-9.]+)", iw_link(iface))
    return float(match.group(1)) if match else None


def gateway_ms(iface: str) -> Optional[float]:
    text = output(f"ping -I {iface} -c 1 -W 2 {CFG.gateway}", timeout=5)
    match = re.search(r"time=([0-9.]+)", text)
    return float(match.group(1)) if match else None


def wifi_health(iface: str) -> WifiHealth:
    connected = wifi_connected(iface)
    gw = gateway_ms(iface) if connected else None
    sig = wifi_signal(iface)
    freq = wifi_freq(iface)

    score = 0
    if connected:
        score += 40
    if gw is not None:
        score += 40
    if sig is not None:
        if sig >= -55:
            score += 20
        elif sig >= -70:
            score += 10

    return WifiHealth(iface, connected, gw, sig, freq, score)


def usb_health() -> WifiHealth:
    return wifi_health(CFG.usb_if)


def onboard_health() -> WifiHealth:
    return wifi_health(CFG.onboard_if)


def active_route() -> str:
    return output("ip route get 1.1.1.1", timeout=5)


def set_usb_primary() -> None:
    run(f"ip route replace default via {CFG.gateway} dev {CFG.usb_if} src {CFG.usb_ip} metric {CFG.usb_metric}")
    run(f"ip route replace default via {CFG.gateway} dev {CFG.onboard_if} src {CFG.onboard_ip} metric {CFG.onboard_metric}")
    STATE.active = "USB_PRIMARY"
    log.info("ROUTE -> USB PRIMARY")


def set_onboard_primary() -> None:
    run(f"ip route replace default via {CFG.gateway} dev {CFG.onboard_if} src {CFG.onboard_ip} metric {CFG.usb_metric}")
    run(f"ip route replace default via {CFG.gateway} dev {CFG.usb_if} src {CFG.usb_ip} metric {CFG.onboard_metric}")
    STATE.active = "ONBOARD_PRIMARY"
    log.warning("ROUTE -> ONBOARD PRIMARY")


def verify_usb_primary() -> bool:
    route = active_route()
    return CFG.usb_if in route and CFG.usb_ip in route


def verify_onboard_primary() -> bool:
    route = active_route()
    return CFG.onboard_if in route and CFG.onboard_ip in route


def heal_usb(force: bool = False) -> None:
    now = time.time()
    if not force and now - STATE.last_usb_heal < CFG.heal_cooldown:
        log.info("HEAL_USB skipped cooldown")
        return
    STATE.last_usb_heal = now
    log.warning("HEAL_USB restart usb-wifi-wpa + link reset")
    run("systemctl restart usb-wifi-wpa.service")
    run(f"ip link set {CFG.usb_if} down")
    time.sleep(2)
    run(f"ip link set {CFG.usb_if} up")
    run(f"networkctl reconfigure {CFG.usb_if}")


def heal_onboard(force: bool = False) -> None:
    now = time.time()
    if not force and now - STATE.last_onboard_heal < CFG.heal_cooldown:
        log.info("HEAL_ONBOARD skipped cooldown")
        return
    STATE.last_onboard_heal = now
    log.warning("HEAL_ONBOARD restart netplan-wpa-wlan0 + link reset")
    run("systemctl restart netplan-wpa-wlan0.service")
    run(f"ip link set {CFG.onboard_if} down")
    time.sleep(2)
    run(f"ip link set {CFG.onboard_if} up")
    run(f"networkctl reconfigure {CFG.onboard_if}")


def service_active(name: str) -> bool:
    return run(f"systemctl is-active --quiet {name}", timeout=5)


def restart_service(name: str) -> None:
    now = time.time()
    last = STATE.last_service_heal.get(name, 0)
    if now - last < CFG.service_heal_cooldown:
        log.info("SERVICE %s restart skipped cooldown", name)
        return
    STATE.last_service_heal[name] = now
    log.warning("SERVICE_RESTART %s", name)
    run(f"systemctl restart {name}", timeout=15)


def service_watch() -> None:
    for name in CFG.watched_services:
        if service_active(name):
            if STATE.service_fail.get(name, 0):
                log.info("SERVICE_RECOVER %s", name)
            STATE.service_fail[name] = 0
            continue
        STATE.service_fail[name] = STATE.service_fail.get(name, 0) + 1
        log.warning("SERVICE_FAIL %s %s/%s", name, STATE.service_fail[name], CFG.service_fail_limit)
        if STATE.service_fail[name] >= CFG.service_fail_limit:
            restart_service(name)
            STATE.service_fail[name] = 0


def port_watch() -> None:
    for label, host, port in CFG.local_ports:
        ok = tcp(host, port)
        if not ok:
            log.warning("PORT_FAIL %s %s:%s", label, host, port)


def zerotier_watch() -> None:
    info = output("zerotier-cli info", timeout=5)
    nets = output("zerotier-cli listnetworks", timeout=5)
    if "ONLINE" not in info:
        log.warning("ZEROTIER_OFFLINE")
    if "OK" not in nets or CFG.usb_ip not in active_route():
        # Do not restart here; service_watch handles service state. This is informational.
        log.info("ZEROTIER_CHECK info=%s", info[:120])


def wifi_state_machine() -> None:
    usb = usb_health()
    onboard = onboard_health()
    log.info(
        "WIFI state=%s usb_good=%s usb_score=%s usb_sig=%s usb_gw=%s onboard_good=%s onboard_score=%s onboard_sig=%s onboard_gw=%s",
        STATE.active,
        usb.good,
        usb.score,
        usb.signal_dbm,
        usb.gateway_ms,
        onboard.good,
        onboard.score,
        onboard.signal_dbm,
        onboard.gateway_ms,
    )

    if STATE.active == "USB_PRIMARY":
        if usb.good:
            STATE.usb_fail = 0
            if not verify_usb_primary():
                log.warning("ROUTE_REPAIR -> USB")
                set_usb_primary()
            if not onboard.good:
                STATE.onboard_fail += 1
                log.info("ONBOARD_STANDBY_BAD %s", STATE.onboard_fail)
                if STATE.onboard_fail >= CFG.wifi_fail_limit:
                    heal_onboard()
                    STATE.onboard_fail = 0
            else:
                STATE.onboard_fail = 0
            return

        STATE.usb_fail += 1
        log.warning("USB_FAIL %s/%s", STATE.usb_fail, CFG.wifi_fail_limit)
        heal_usb()
        if STATE.usb_fail >= CFG.wifi_fail_limit:
            if onboard.good:
                log.warning("FAILOVER USB -> ONBOARD")
                set_onboard_primary()
                STATE.usb_fail = 0
                STATE.usb_recover = 0
            else:
                log.error("BOTH_WIFI_BAD")
        return

    if STATE.active == "ONBOARD_PRIMARY":
        if onboard.good:
            if not verify_onboard_primary():
                log.warning("ROUTE_REPAIR -> ONBOARD")
                set_onboard_primary()
            if usb.good:
                STATE.usb_recover += 1
                log.info("USB_RECOVER %s/%s", STATE.usb_recover, CFG.wifi_recover_limit)
                if STATE.usb_recover >= CFG.wifi_recover_limit:
                    log.warning("FAILBACK -> USB")
                    set_usb_primary()
                    STATE.usb_recover = 0
                    STATE.usb_fail = 0
            else:
                STATE.usb_recover = 0
                heal_usb()
            return

        log.error("ONBOARD_PRIMARY_BAD")
        heal_onboard()
        if usb.good:
            log.warning("FAILBACK ONBOARD -> USB")
            set_usb_primary()
        else:
            log.error("BOTH_WIFI_BAD")


def cycle() -> None:
    wifi_state_machine()
    service_watch()
    port_watch()
    zerotier_watch()
    log.info("ACTIVE_ROUTE %s", active_route())


def main() -> None:
    log.info("=" * 60)
    log.info("NetWatchdog v%s starting", VERSION)
    log.info("USB=%s %s ONBOARD=%s %s GW=%s", CFG.usb_if, CFG.usb_ip, CFG.onboard_if, CFG.onboard_ip, CFG.gateway)
    log.info("=" * 60)
    set_usb_primary()

    while True:
        try:
            cycle()
        except Exception as exc:  # noqa: BLE001
            log.exception("UNHANDLED_EXCEPTION %s", exc)
        time.sleep(CFG.check_interval)


if __name__ == "__main__":
    main()
