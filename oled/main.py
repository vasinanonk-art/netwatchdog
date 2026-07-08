"""NetWatchDog OLED front panel."""

import datetime as dt
import time

from . import boot, config, dashboard, network, popup, screensaver, status_source
from .display import OLED
from .state import RuntimeState


def apply_brightness(display):
    hour = dt.datetime.now().hour
    if hour >= config.NIGHT_START_HOUR or hour < config.DAY_START_HOUR:
        display.contrast(config.NIGHT_CONTRAST)
    else:
        display.contrast(config.DAY_CONTRAST)


def current_mode(status):
    if status and status.get("mode"):
        return str(status.get("mode")).upper()
    return network.active_link()


def current_internet(status):
    if status and "internet" in status:
        return status_source.get_bool(status, "internet", False)
    return network.internet_ok()


def main():
    display = OLED()
    runtime = RuntimeState()
    apply_brightness(display)
    boot.run_boot(display)

    screen_index = 0
    shift_tick = 0
    last_shift = time.time()
    last_activity = time.time()
    was_blank = False

    status = status_source.read_status()
    runtime.update_status(status)
    runtime.mark_link(current_mode(status))
    runtime.mark_internet(current_internet(status))

    while True:
        apply_brightness(display)

        status = status_source.read_status()
        runtime.update_status(status)

        link_event = runtime.mark_link(current_mode(status))
        net_event = runtime.mark_internet(current_internet(status))

        if link_event or net_event:
            last_activity = time.time()

        if popup.show_link_event(display, link_event):
            last_activity = time.time()
            time.sleep(config.POPUP_SEC)
        elif popup.show_internet_event(display, net_event):
            last_activity = time.time()
            time.sleep(config.POPUP_SEC)

        now = time.time()
        if screensaver.should_blank(now, last_activity, config.SCREEN_SAVER_SEC, config.SCREEN_SAVER_BLANK_SEC):
            if not was_blank:
                display.power(False)
                was_blank = True
            time.sleep(1)
            continue

        if was_blank:
            display.power(True)
            was_blank = False

        if now - last_shift >= config.BURN_SHIFT_SEC:
            shift_tick += 1
            last_shift = now

        screen_func = dashboard.SCREENS[screen_index % len(dashboard.SCREENS)]
        display.text_screen(screen_func(runtime), shift=screensaver.shift_for_tick(shift_tick, config.PIXEL_SHIFT))

        screen_index += 1
        time.sleep(config.PAGE_INTERVAL_SEC)


if __name__ == "__main__":
    main()
