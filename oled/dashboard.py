"""Dashboard screen builders."""

from . import config, network, stats, status_source


def _status(runtime=None):
    return getattr(runtime, "status", None) if runtime else None


def _mode(data):
    mode = status_source.get_str(data, "mode", "")
    return mode.upper() if mode else network.active_link()


def _gateway_ok(data):
    value = status_source.get_bool(data, "gateway", None)
    return network.gateway_ok() if value is None else value


def _internet_ok(data):
    value = status_source.get_bool(data, "internet", None)
    return network.internet_ok() if value is None else value


def _last_ping(data):
    value = status_source.get_int(data, "last_ping", -1)
    if value >= 0:
        return f"Ping {value}ms"
    return network.gateway_ping_line()


def health_score(data=None):
    score = 100
    if not _gateway_ok(data):
        score -= 35
    if not _internet_ok(data):
        score -= 35
    if stats.cpu_percent() > 85:
        score -= 10
    if stats.ram_percent() > 85:
        score -= 10
    retry = status_source.get_int(data, "retry", 0)
    score -= min(10, retry * 2)
    return max(0, min(100, score))


def system_screen(runtime=None):
    return [
        "SYSTEM",
        f"CPU {stats.cpu_percent():02d}%  {stats.temp_c()}C",
        f"RAM {stats.ram_percent():02d}%",
    ]


def network_screen(runtime=None):
    data = _status(runtime)
    gw = "GW OK" if _gateway_ok(data) else "GW FAIL"
    net = "NET OK" if _internet_ok(data) else "NET FAIL"
    return ["NETWORK", _mode(data), f"{gw} {net}"]


def watchdog_screen(runtime=None):
    data = _status(runtime)
    retry = status_source.get_int(data, "retry", 0)
    failover = status_source.get_int(data, "failover", runtime.failover_count if runtime else 0)
    return ["WATCHDOG", _last_ping(data), f"Retry {retry} F{failover}"]


def health_screen(runtime=None):
    data = _status(runtime)
    return ["HEALTH", f"Score {health_score(data)}%", _mode(data)]


def ip_screen(runtime=None):
    data = _status(runtime)
    ip = status_source.get_str(data, "ip", network.ip_addr())
    return ["IP", ip[:18], _mode(data)]


def wifi_screen(runtime=None):
    data = _status(runtime)
    rssi = status_source.get_int(data, "rssi", 999)
    line = f"RSSI {rssi}dBm" if rssi != 999 else network.wifi_rssi_line()
    return ["WIFI", _mode(data), line]


def uptime_screen(runtime=None, version="v5.0.1"):
    data = _status(runtime)
    ver = status_source.get_str(data, "version", version)
    return ["SYSTEM", stats.uptime_short(), ver[:18]]


def event_screen(runtime=None):
    if not runtime:
        return ["EVENT", "No runtime", ""]
    return ["EVENT", runtime.last_event, runtime.last_event_age()]


def iface_screen(runtime=None):
    pri = "PRI UP" if network.iface_up(config.PRIMARY_IFACE) else "PRI DOWN"
    bak = "BAK UP" if network.iface_up(config.BACKUP_IFACE) else "BAK DOWN"
    return ["INTERFACE", pri, bak]


SCREENS = [
    system_screen,
    network_screen,
    watchdog_screen,
    health_screen,
    event_screen,
    ip_screen,
    wifi_screen,
    iface_screen,
    uptime_screen,
]
