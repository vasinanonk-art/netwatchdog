"""Boot animation for OLED."""

import time


def run_boot(display):
    for pct in (5, 18, 35, 55, 72, 88, 100):
        display.loading(pct)
        time.sleep(0.22)
