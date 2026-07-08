"""Dashboard screen builders."""

from . import config, network, stats


def system_screen(runtime=None):
    return [
        "SYSTEM",
        f"CPU {stats.cpu_percent():02d}%  {stats.temp_c()}C",
        f"RAM {stats.ram_percent():02d}%",
    ]


def network_screen(runtime=None):
    gw = "GW OK" if network.gateway_ok() else "GW FAIL"
    net = "NET OK" if network.internet_ok() else "NET FAIL"
    return ["NETWORK", network.active_link(), f"{gw} {net}"]


def watchdog_screen(runtime=None):
    retries = runtime.failover_count if runtime else 0
    return ["WATCHDOG", network.gateway_ping_line(), f"Failover {retries}"]


def uptime_screen(runtime=None, version="v5.0.1"):
    return ["SYSTEM", stats.uptime_short(), version]


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
    event_screen,
    iface_screen,
    uptime_screen,
]
