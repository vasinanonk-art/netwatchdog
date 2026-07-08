"""NetWatchDog health scoring engine."""


def score(gateway_ok, internet_ok, cpu, ram, temp, rssi=None, retry=0):
    value = 100
    reasons = []

    if not gateway_ok:
        value -= 25
        reasons.append("Gateway lost")
    if not internet_ok:
        value -= 25
        reasons.append("Internet unstable")
    if cpu is not None and cpu >= 85:
        value -= 15
        reasons.append("CPU high")
    if ram is not None and ram >= 85:
        value -= 15
        reasons.append("RAM high")
    if temp is not None and temp >= 75:
        value -= 15
        reasons.append("CPU temp high")
    if rssi is not None and rssi < -70:
        value -= 10
        reasons.append("RSSI poor")
    if retry:
        value -= min(10, retry * 2)
        reasons.append("Retry active")

    value = max(0, min(100, value))
    return value, reasons or ["Normal"]


def status(value):
    if value >= 85:
        return "OK"
    if value >= 70:
        return "DEGRADED"
    return "CRITICAL"
