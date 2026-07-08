"""NetWatchDog health scoring engine."""


def score(gateway_ok, internet_ok, cpu, ram, temp, rssi=None, retry=0):
    value = 100
    reasons = []

    if not gateway_ok:
        value -= 30
        reasons.append("GW")
    if not internet_ok:
        value -= 35
        reasons.append("NET")
    if cpu >= 90:
        value -= 10
        reasons.append("CPU")
    if ram >= 90:
        value -= 10
        reasons.append("RAM")
    if temp >= 75:
        value -= 10
        reasons.append("TEMP")
    if rssi is not None and rssi < -75:
        value -= 5
        reasons.append("RSSI")
    if retry:
        value -= min(10, retry * 2)
        reasons.append("RETRY")

    value = max(0, min(100, value))
    return value, reasons
