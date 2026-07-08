"""Burn-in protection helpers."""

SHIFT_PATTERN = [(0, 0), (1, 0), (1, 1), (0, 1)]


def shift_for_tick(tick):
    return SHIFT_PATTERN[tick % len(SHIFT_PATTERN)]
