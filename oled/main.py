"""NetWatchDog OLED front panel."""

import datetime as dt
import time

from . import boot, config, dashboard, network, popup, screensaver
from .display import OLED


def apply_brightness(display):
    hour = dt.datetime.now().hour
    if hour >= config.NIGHT_START_HOUR or hour < config.DAY_START_HOUR:
        display.contrast(config.NIGHT_CONTRAST)
    else:
        display.contrast(config.DAY_CONTRAST)


def main():
    display = OLED()
    apply_brightness(display)
    boot.run_boot(display)

    screen_index = 0
    shift_tick = 0
    last_shift = time.time()
    last_link = network.active_link()

    while True:
        apply_brightness(display)
        current_link = network.active_link()

        if popup.show_link_change(display, last_link, current_link):
            time.sleep(config.POPUP_SEC)

        last_link = current_link

        now = time.time()
        if now - last_shift >= config.BURN_SHIFT_SEC:
            shift_tick += 1
            last_shift = now

        screen_func = dashboard.SCREENS[screen_index % len(dashboard.SCREENS)]
        display.text_screen(screen_func(), shift=screensaver.shift_for_tick(shift_tick))

        screen_index += 1
        time.sleep(config.PAGE_INTERVAL_SEC)


if __name__ == "__main__":
    main()
