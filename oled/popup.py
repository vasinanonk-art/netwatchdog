"""OLED popup helpers."""


def show_link_change(display, old_link, new_link):
    if old_link == new_link:
        return False
    if new_link == "BACKUP":
        display.popup("FAILOVER", "Backup Active")
        return True
    if new_link == "PRIMARY":
        display.popup("RESTORED", "Primary Active")
        return True
    if new_link == "LINK FAIL":
        display.popup("LINK FAIL", "Check Network")
        return True
    return False
