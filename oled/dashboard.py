"""Dashboard screen builders."""

from . import network, stats


def system_screen():
    return [
        "SYSTEM",
        f"CPU {stats.cpu_percent():02d}%  {stats.temp_c()}C",
        f"RAM {stats.ram_percent():02d}%",
    ]


def network_screen():
    gw = "GW OK" if network.gateway_ok() else "GW FAIL"
    net = "NET OK" if network.internet_ok() else "NET FAIL"
    return ["NETWORK", network.active_link(), f"{gw} {net}"]


def watchdog_screen():
    return ["WATCHDOG", network.gateway_ping_line(), "Retry 0"]


def uptime_screen(version="v5.0.1"):
    return ["SYSTEM", stats.uptime_short(), version]


SCREENS = [system_screen, network_screen, watchdog_screen, uptime_screen]
