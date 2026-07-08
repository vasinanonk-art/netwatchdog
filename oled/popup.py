"""OLED popup helpers."""


def show_link_event(display, event):
    if event == "FAILOVER":
        display.popup("FAILOVER", "Backup Active")
        return True
    if event == "RESTORED":
        display.popup("RESTORED", "Primary Active")
        return True
    if event == "LINK FAIL":
        display.popup("LINK FAIL", "Check Network")
        return True
    return False


def show_internet_event(display, event):
    if event == "NET LOST":
        display.popup("NET LOST", "Internet Down")
        return True
    if event == "NET OK":
        display.popup("NET OK", "Internet Back")
        return True
    return False
