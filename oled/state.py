"""Small runtime state tracker for OLED front panel.

No persistence yet. Keeps counters and recent events only inside the OLED service.
"""

import time


class RuntimeState:
    def __init__(self):
        self.started_at = time.time()
        self.failover_count = 0
        self.restore_count = 0
        self.internet_loss_count = 0
        self.last_event = "BOOT"
        self.last_event_at = self.started_at
        self.last_link = None
        self.last_internet_ok = None

    def mark_link(self, link):
        now = time.time()
        event = None
        if self.last_link is not None and link != self.last_link:
            if link == "BACKUP":
                self.failover_count += 1
                event = "FAILOVER"
            elif link == "PRIMARY":
                self.restore_count += 1
                event = "RESTORED"
            else:
                event = "LINK FAIL"

        self.last_link = link
        if event:
            self.last_event = event
            self.last_event_at = now
        return event

    def mark_internet(self, ok):
        now = time.time()
        event = None
        if self.last_internet_ok is not None and ok != self.last_internet_ok:
            if not ok:
                self.internet_loss_count += 1
                event = "NET LOST"
            else:
                event = "NET OK"

        self.last_internet_ok = ok
        if event:
            self.last_event = event
            self.last_event_at = now
        return event

    def last_event_age(self):
        seconds = int(time.time() - self.last_event_at)
        if seconds < 60:
            return f"{seconds}s ago"
        minutes = seconds // 60
        return f"{minutes}m ago"
