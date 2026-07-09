#!/usr/bin/env python3
from __future__ import annotations

import logging, re, socket, subprocess, time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from netwatchdog_common import STATUS_PATH, VERSION, append_event, atomic_write_json, cpu_percent, cpu_temp_c, disk_percent, ensure_dirs, git_commit, health_score, load_config, memory_percent, update_history

@dataclass(frozen=True)
class Config:
    usb_if: str; usb_ip: str; onboard_if: str; onboard_ip: str; gateway: str; internet_target: str
    usb_metric: int; onboard_metric: int; check_interval: int; wifi_fail_limit: int; wifi_recover_limit: int
    heal_cooldown: int; service_fail_limit: int; service_heal_cooldown: int
    watched_services: tuple[str, ...]; local_ports: tuple[tuple[str, str, int], ...]

@dataclass
class WifiHealth:
    iface: str; connected: bool; gateway_ms: Optional[float]; signal_dbm: Optional[int]; freq_mhz: Optional[float]; score: int
    @property
    def good(self) -> bool:
        return self.connected and self.gateway_ms is not None and self.score >= 70

@dataclass
class WatchState:
    active: str = "USB_PRIMARY"
    usb_fail: int = 0; usb_recover: int = 0; onboard_fail: int = 0
    last_usb_heal: float = 0; last_onboard_heal: float = 0
    service_fail: Dict[str, int] = field(default_factory=dict)
    last_service_heal: Dict[str, float] = field(default_factory=dict)
    missing_services: set[str] = field(default_factory=set)
    gateway_was_down: bool = False; internet_was_down: bool = False
    gateway_fail: int = 0; gateway_recover: int = 0
    internet_fail: int = 0; internet_recover: int = 0
    last_wifi_log: Any = None


def build_config() -> Config:
    raw = load_config(); net = raw["network"]; wd = raw["watchdog"]
    ports = [(str(p["label"]), str(p["host"]), int(p["port"])) for p in wd.get("local_ports", []) if isinstance(p, dict)]
    return Config(str(net["usb_if"]), str(net["usb_ip"]), str(net["onboard_if"]), str(net["onboard_ip"]), str(net["gateway"]), str(net["internet_target"]), int(net["usb_metric"]), int(net["onboard_metric"]), int(wd["check_interval"]), int(net["wifi_fail_limit"]), int(net["wifi_recover_limit"]), int(net["heal_cooldown"]), int(wd["service_fail_limit"]), int(wd["service_heal_cooldown"]), tuple(str(s) for s in wd.get("watched_services", [])), tuple(ports))

CFG = build_config(); STATE = WatchState()
EVENT_DEBOUNCE = max(2, CFG.wifi_fail_limit)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("netwatchdog")


def run(cmd: str, timeout: int = 10) -> bool:
    try: return subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout).returncode == 0
    except subprocess.TimeoutExpired: return False


def output(cmd: str, timeout: int = 10) -> str:
    try: return subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout).stdout.strip()
    except subprocess.TimeoutExpired: return ""


def tcp(host: str, port: int, timeout: int = 2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout): return True
    except OSError: return False


def ping_ms(target: str, iface: str | None = None) -> Optional[float]:
    cmd = f"ping -c 1 -W 2 {target}" if iface is None else f"ping -I {iface} -c 1 -W 2 {target}"
    m = re.search(r"time=([0-9.]+)", output(cmd, 5))
    return float(m.group(1)) if m else None


def iw_link(iface: str) -> str: return output(f"iw dev {iface} link", 5)
def wifi_connected(iface: str) -> bool: return "Connected to" in iw_link(iface)
def wifi_signal(iface: str) -> Optional[int]:
    m = re.search(r"signal:\s*(-?\d+)", iw_link(iface)); return int(m.group(1)) if m else None
def wifi_freq(iface: str) -> Optional[float]:
    m = re.search(r"freq:\s*([0-9.]+)", iw_link(iface)); return float(m.group(1)) if m else None
def gateway_ms(iface: str) -> Optional[float]: return ping_ms(CFG.gateway, iface)


def wifi_health(iface: str) -> WifiHealth:
    connected = wifi_connected(iface); gw = gateway_ms(iface) if connected else None; sig = wifi_signal(iface); freq = wifi_freq(iface)
    score = (40 if connected else 0) + (40 if gw is not None else 0) + (20 if sig is not None and sig >= -55 else 10 if sig is not None and sig >= -70 else 0)
    return WifiHealth(iface, connected, gw, sig, freq, score)


def usb_health() -> WifiHealth: return wifi_health(CFG.usb_if)
def onboard_health() -> WifiHealth: return wifi_health(CFG.onboard_if)
def active_route() -> str: return output(f"ip route get {CFG.internet_target}", 5)


def set_usb_primary() -> None:
    run(f"ip route replace default via {CFG.gateway} dev {CFG.usb_if} src {CFG.usb_ip} metric {CFG.usb_metric}")
    run(f"ip route replace default via {CFG.gateway} dev {CFG.onboard_if} src {CFG.onboard_ip} metric {CFG.onboard_metric}")
    STATE.active = "USB_PRIMARY"; append_event("Restored", "USB primary route active"); log.info("ROUTE -> USB PRIMARY")


def set_onboard_primary() -> None:
    run(f"ip route replace default via {CFG.gateway} dev {CFG.onboard_if} src {CFG.onboard_ip} metric {CFG.usb_metric}")
    run(f"ip route replace default via {CFG.gateway} dev {CFG.usb_if} src {CFG.usb_ip} metric {CFG.onboard_metric}")
    STATE.active = "ONBOARD_PRIMARY"; append_event("Failover", "Onboard Wi-Fi primary route active", "warning"); log.warning("ROUTE -> ONBOARD PRIMARY")


def verify_usb_primary() -> bool:
    r = active_route(); return CFG.usb_if in r and CFG.usb_ip in r
def verify_onboard_primary() -> bool:
    r = active_route(); return CFG.onboard_if in r and CFG.onboard_ip in r


def heal_usb(force: bool = False) -> None:
    now = time.time()
    if not force and now - STATE.last_usb_heal < CFG.heal_cooldown: log.info("HEAL_USB skipped cooldown"); return
    STATE.last_usb_heal = now; append_event("USB WiFi Heal", "Restart usb-wifi-wpa and reset link", "warning")
    run("systemctl restart usb-wifi-wpa.service"); run(f"ip link set {CFG.usb_if} down"); time.sleep(2); run(f"ip link set {CFG.usb_if} up"); run(f"networkctl reconfigure {CFG.usb_if}")


def heal_onboard(force: bool = False) -> None:
    now = time.time()
    if not force and now - STATE.last_onboard_heal < CFG.heal_cooldown: log.info("HEAL_ONBOARD skipped cooldown"); return
    STATE.last_onboard_heal = now; append_event("Onboard WiFi Heal", "Restart netplan-wpa-wlan0 and reset link", "warning")
    run("systemctl restart netplan-wpa-wlan0.service"); run(f"ip link set {CFG.onboard_if} down"); time.sleep(2); run(f"ip link set {CFG.onboard_if} up"); run(f"networkctl reconfigure {CFG.onboard_if}")


def service_exists(name: str) -> bool: return run(f"systemctl cat {name}", 5)
def service_active(name: str) -> bool: return run(f"systemctl is-active --quiet {name}", 5)


def restart_service(name: str) -> None:
    now = time.time(); last = STATE.last_service_heal.get(name, 0)
    if now - last < CFG.service_heal_cooldown: log.info("SERVICE %s restart skipped cooldown", name); return
    STATE.last_service_heal[name] = now; append_event("Service Restarted", name, "warning"); log.warning("SERVICE_RESTART %s", name); run(f"systemctl restart {name}", 15)


def service_watch() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in CFG.watched_services:
        if name in STATE.missing_services: result[name] = "missing"; continue
        if not service_exists(name): STATE.missing_services.add(name); STATE.service_fail.pop(name, None); result[name] = "missing"; log.info("SERVICE_SKIP_MISSING %s", name); continue
        if service_active(name):
            if STATE.service_fail.get(name, 0): append_event("Service Restored", name); log.info("SERVICE_RECOVER %s", name)
            STATE.service_fail[name] = 0; result[name] = "active"; continue
        STATE.service_fail[name] = STATE.service_fail.get(name, 0) + 1; result[name] = "failed"; log.warning("SERVICE_FAIL %s %s/%s", name, STATE.service_fail[name], CFG.service_fail_limit)
        if STATE.service_fail[name] >= CFG.service_fail_limit: restart_service(name); STATE.service_fail[name] = 0
    return result


def port_watch() -> list[dict[str, Any]]:
    ports = []
    for label, host, port in CFG.local_ports:
        ok = tcp(host, port); ports.append({"label": label, "host": host, "port": port, "ok": ok})
        if not ok: log.warning("PORT_FAIL %s %s:%s", label, host, port)
    return ports


def zerotier_watch() -> None:
    info = output("zerotier-cli info", 5); nets = output("zerotier-cli listnetworks", 5)
    if info and "ONLINE" not in info: log.warning("ZEROTIER_OFFLINE")
    if nets and ("OK" not in nets or CFG.usb_ip not in active_route()): log.info("ZEROTIER_CHECK info=%s", info[:120])


def init_route_state() -> None:
    append_event("Boot", f"NetWatchDog v{VERSION} starting"); r = active_route()
    if CFG.usb_if in r and CFG.usb_ip in r: STATE.active = "USB_PRIMARY"; log.info("START_ROUTE USB_PRIMARY existing route kept"); return
    if CFG.onboard_if in r and CFG.onboard_ip in r: STATE.active = "ONBOARD_PRIMARY"; log.warning("START_ROUTE ONBOARD_PRIMARY existing route kept"); return
    usb = usb_health(); onboard = onboard_health()
    if usb.good: set_usb_primary(); return
    if onboard.good: set_onboard_primary(); return
    append_event("Gateway Lost", "No healthy Wi-Fi during boot", "error"); log.error("START_ROUTE no healthy Wi-Fi; route unchanged")


def log_wifi_state_if_changed(usb: WifiHealth, onboard: WifiHealth) -> None:
    signature = (STATE.active, usb.good, onboard.good, usb.score, onboard.score)
    if signature == STATE.last_wifi_log:
        return
    STATE.last_wifi_log = signature
    log.info("WIFI state=%s usb_good=%s usb_score=%s usb_sig=%s onboard_good=%s onboard_score=%s onboard_sig=%s", STATE.active, usb.good, usb.score, usb.signal_dbm, onboard.good, onboard.score, onboard.signal_dbm)


def wifi_state_machine(usb: WifiHealth, onboard: WifiHealth) -> None:
    log_wifi_state_if_changed(usb, onboard)
    if STATE.active == "USB_PRIMARY":
        if usb.good:
            STATE.usb_fail = 0
            if not verify_usb_primary(): log.warning("ROUTE_REPAIR -> USB"); set_usb_primary()
            if not onboard.good:
                STATE.onboard_fail += 1
                log.info("ONBOARD_FAIL %s/%s", STATE.onboard_fail, CFG.wifi_fail_limit)
                if STATE.onboard_fail >= CFG.wifi_fail_limit: heal_onboard(); STATE.onboard_fail = 0
            else: STATE.onboard_fail = 0
            return
        STATE.usb_fail += 1; log.warning("USB_FAIL %s/%s", STATE.usb_fail, CFG.wifi_fail_limit)
        if STATE.usb_fail >= CFG.wifi_fail_limit:
            heal_usb()
            if onboard.good: log.warning("FAILOVER USB -> ONBOARD"); set_onboard_primary(); STATE.usb_fail = 0; STATE.usb_recover = 0
            else: append_event("Gateway Lost", "Both Wi-Fi links bad", "error"); log.error("BOTH_WIFI_BAD")
        return
    if onboard.good:
        if not verify_onboard_primary(): log.warning("ROUTE_REPAIR -> ONBOARD"); set_onboard_primary()
        if usb.good:
            STATE.usb_recover += 1
            if STATE.usb_recover >= CFG.wifi_recover_limit: log.warning("FAILBACK -> USB"); set_usb_primary(); STATE.usb_recover = 0; STATE.usb_fail = 0
        else:
            STATE.usb_recover = 0
            STATE.usb_fail += 1
            log.info("USB_RECOVER_WAIT %s/%s", STATE.usb_fail, CFG.wifi_fail_limit)
            if STATE.usb_fail >= CFG.wifi_fail_limit: heal_usb(); STATE.usb_fail = 0
        return
    STATE.onboard_fail += 1
    log.warning("ONBOARD_PRIMARY_FAIL %s/%s", STATE.onboard_fail, CFG.wifi_fail_limit)
    if STATE.onboard_fail >= CFG.wifi_fail_limit:
        heal_onboard(); STATE.onboard_fail = 0
        if usb.good: log.warning("FAILBACK ONBOARD -> USB"); set_usb_primary()
        else: append_event("Gateway Lost", "Both Wi-Fi links bad", "error"); log.error("BOTH_WIFI_BAD")


def debounce_link_event(name: str, ok: bool, was_down: bool, fail_attr: str, recover_attr: str, lost_event: str, lost_detail: str, restore_detail: str) -> bool:
    if ok:
        setattr(STATE, fail_attr, 0)
        if was_down:
            setattr(STATE, recover_attr, getattr(STATE, recover_attr) + 1)
            if getattr(STATE, recover_attr) >= EVENT_DEBOUNCE:
                append_event("Restored", restore_detail)
                setattr(STATE, recover_attr, 0)
                return False
        else:
            setattr(STATE, recover_attr, 0)
        return was_down
    setattr(STATE, recover_attr, 0)
    if not was_down:
        setattr(STATE, fail_attr, getattr(STATE, fail_attr) + 1)
        if getattr(STATE, fail_attr) >= EVENT_DEBOUNCE:
            append_event(lost_event, lost_detail, "error")
            setattr(STATE, fail_attr, 0)
            return True
    return was_down


def write_status(usb: WifiHealth, onboard: WifiHealth, services: dict[str, str], ports: list[dict[str, Any]]) -> None:
    now = int(time.time()); active_iface = CFG.usb_if if STATE.active == "USB_PRIMARY" else CFG.onboard_if; active = usb if active_iface == CFG.usb_if else onboard
    internet = ping_ms(CFG.internet_target, active_iface if active.connected else None); cpu = cpu_percent(); ram = memory_percent(); temp = cpu_temp_c(); disk = disk_percent("/")
    health = health_score(cpu, ram, temp, active.signal_dbm, active.gateway_ms, internet)
    STATE.gateway_was_down = debounce_link_event("gateway", active.gateway_ms is not None, STATE.gateway_was_down, "gateway_fail", "gateway_recover", "Gateway Lost", CFG.gateway, "Gateway reachable")
    STATE.internet_was_down = debounce_link_event("internet", internet is not None, STATE.internet_was_down, "internet_fail", "internet_recover", "Internet Lost", CFG.internet_target, "Internet reachable")
    sample = {"ts": now, "cpu": cpu, "ram": ram, "temp": temp, "rssi": active.signal_dbm, "gateway_ms": active.gateway_ms, "internet_ms": internet, "health": health["score"]}
    update_history(sample)
    atomic_write_json(STATUS_PATH, {"version": VERSION, "git_commit": git_commit(), "ts": now, "uptime_sec": int(time.monotonic()), "active": STATE.active, "route": active_route(), "health": health, "metrics": {"cpu": cpu, "ram": ram, "temp": temp, "disk": disk}, "network": {"usb": usb.__dict__, "onboard": onboard.__dict__, "internet_ms": internet, "gateway": CFG.gateway, "internet_target": CFG.internet_target}, "services": services, "ports": ports})


def cycle() -> None:
    usb = usb_health(); onboard = onboard_health(); wifi_state_machine(usb, onboard); services = service_watch(); ports = port_watch(); zerotier_watch(); write_status(usb, onboard, services, ports)


def main() -> None:
    ensure_dirs(); log.info("NetWatchDog v%s starting", VERSION); log.info("USB=%s %s ONBOARD=%s %s GW=%s", CFG.usb_if, CFG.usb_ip, CFG.onboard_if, CFG.onboard_ip, CFG.gateway); init_route_state()
    while True:
        try: cycle()
        except Exception as exc: append_event("Watchdog Error", str(exc), "error"); log.exception("UNHANDLED_EXCEPTION %s", exc)
        time.sleep(max(5, CFG.check_interval))

if __name__ == "__main__": main()
