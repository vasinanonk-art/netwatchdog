"""NetWatchDog OLED front panel."""

import datetime as dt
import time

from . import boot, config, dashboard, network, popup, screensaver, status_source
from .display import OLED
from .state import RuntimeState


def apply_brightness(display):
    if not config.BRIGHTNESS_ENABLED:
        return
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


def status_signature(status):
    if not status:
        return None
    health = status.get("health") or {}
    return (
        status.get("active"),
        status.get("mode"),
        status.get("iface"),
        status.get("gateway"),
        status.get("internet"),
        status.get("failover"),
        status.get("restore"),
        status.get("ip"),
        health.get("score"),
        health.get("status"),
        tuple(health.get("reasons") or ()),
        status.get("last_event"),
        status.get("last_event_at"),
    )


def main():
    display = OLED()
    runtime = RuntimeState()
    apply_brightness(display)
    boot.run_boot(display)

    screen_index = 0
    shift_tick = 0
    last_shift = time.time()
    last_activity = time.time()
    last_page = time.time()
    last_render_key = None
    was_blank = False

    status = status_source.read_status()
    last_signature = status_signature(status)
    runtime.update_status(status)
    runtime.mark_link(current_mode(status))
    runtime.mark_internet(current_internet(status))

    while True:
        apply_brightness(display)

        status = status_source.read_status()
        signature = status_signature(status)
        status_changed = signature != last_signature
        if status_changed:
            last_signature = signature
            last_activity = time.time()
        runtime.update_status(status)

        link_event = runtime.mark_link(current_mode(status))
        net_event = runtime.mark_internet(current_internet(status))

        if link_event or net_event:
            last_activity = time.time()

        popup_rendered = False
        if popup.show_link_event(display, link_event):
            last_activity = time.time()
            last_render_key = None
            was_blank = False
            popup_rendered = True
            time.sleep(config.POPUP_SEC)
        elif popup.show_internet_event(display, net_event):
            last_activity = time.time()
            last_render_key = None
            was_blank = False
            popup_rendered = True
            time.sleep(config.POPUP_SEC)
        if popup_rendered:
            # The first normal frame after a popup silently rewrites the full buffer.
            display.request_force_refresh()

        now = time.time()
        if now - last_activity >= 600:
            if not was_blank:
                display.power(False)
                was_blank = True
                last_render_key = None
            time.sleep(1)
            continue

        woke_from_blank = False
        if was_blank:
            display.power(True)
            display.request_force_refresh()
            was_blank = False
            woke_from_blank = True

        shift_changed = False
        if now - last_shift >= config.BURN_SHIFT_SEC:
            shift_tick += 1
            last_shift = now
            shift_changed = True

        page_changed = False
        if now - last_page >= config.PAGE_INTERVAL_SEC:
            screen_index += 1
            last_page = now
            page_changed = True

        shift = screensaver.shift_for_tick(shift_tick, config.PIXEL_SHIFT)
        page = screen_index % len(dashboard.SCREENS)
        render_key = (page, shift, signature)
        refresh_due = display.refresh_due()
        if not (status_changed or page_changed or shift_changed or woke_from_blank or refresh_due or render_key != last_render_key):
            time.sleep(1)
            continue

        screen_func = dashboard.SCREENS[page]
        display.text_screen(screen_func(runtime), shift=shift)
        last_render_key = render_key
        time.sleep(1)


if __name__ == "__main__":
    main()
