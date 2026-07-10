"""Burn-in protection helpers."""

SHIFT_PATTERN = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1)]


def shift_for_tick(tick, enabled=True):
    if not enabled:
        return (0, 0)
    return SHIFT_PATTERN[tick % len(SHIFT_PATTERN)]


def should_blank(now, last_activity, timeout_sec, blank_sec):
    if timeout_sec <= 0 or blank_sec <= 0:
        return False
    elapsed = int(now - last_activity)
    if elapsed < timeout_sec:
        return False
    cycle = timeout_sec + blank_sec
    return (elapsed % cycle) >= timeout_sec
