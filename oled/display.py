"""Minimal SSD1306 128x32 I2C driver for NetWatchDog OLED.

No luma.oled, no pip dependencies. Uses Debian python3-smbus + Pillow.
"""

import time

import smbus
from PIL import Image, ImageDraw, ImageFont

from . import config

try:
    from netwatchdog_common import append_event
except Exception:
    append_event = None


class OLED:
    FULL_REFRESH_INTERVAL_SEC = 60.0

    def __init__(self, bus=config.I2C_BUS, addr=config.I2C_ADDR):
        self.bus_id = bus
        self.bus = smbus.SMBus(bus)
        self.addr = addr
        self.width = config.WIDTH
        self.height = config.HEIGHT
        self.font = ImageFont.load_default()
        self._last_pages = None
        self._display_on = True
        self._last_recover = 0.0
        self._force_next_frame = True
        self.partial_updates = 0
        self.full_refreshes = 0
        self.last_full_refresh = 0.0
        self.recoveries = 0
        self.page_write_failures = 0
        self._init_display()

    def _event(self, name, detail=""):
        if append_event:
            try:
                append_event(name, detail)
            except Exception:
                pass

    def _write_cmd(self, value):
        self.bus.write_i2c_block_data(self.addr, 0x00, [value])

    def _write_data(self, values):
        for i in range(0, len(values), 16):
            self.bus.write_i2c_block_data(self.addr, 0x40, values[i:i + 16])

    def request_force_refresh(self):
        """Make the next rendered frame a silent full-buffer refresh."""
        self._force_next_frame = True

    def refresh_due(self, now=None):
        now = time.monotonic() if now is None else float(now)
        return self._force_next_frame or self.last_full_refresh <= 0 or now - self.last_full_refresh >= self.FULL_REFRESH_INTERVAL_SEC

    def diagnostics(self):
        """OLED-only runtime diagnostics; not written to shared status/history."""
        return {
            "partial_updates": self.partial_updates,
            "full_refreshes": self.full_refreshes,
            "last_full_refresh": self.last_full_refresh,
            "recoveries": self.recoveries,
            "page_write_failures": self.page_write_failures,
        }

    def _recover(self):
        now = time.monotonic()
        if now - self._last_recover < 2:
            return False
        self._last_recover = now
        try:
            try:
                self.bus.close()
            except Exception:
                pass
            time.sleep(0.1)
            self.bus = smbus.SMBus(self.bus_id)
            self._last_pages = None
            self._display_on = True
            for c in self._init_sequence():
                self._write_cmd(c)
            self.recoveries += 1
            self.request_force_refresh()
            self._event("OLED Recovered", "I2C display reinitialized")
            return True
        except OSError:
            return False

    def cmd(self, value):
        try:
            self._write_cmd(value)
        except OSError:
            if not self._recover():
                return False
            try:
                self._write_cmd(value)
            except OSError:
                return False
        return True

    def data(self, values):
        try:
            self._write_data(values)
        except OSError:
            if not self._recover():
                return False
            try:
                self._write_data(values)
            except OSError:
                return False
        return True

    def _init_sequence(self):
        return [
            0xAE, 0xD5, 0x80, 0xA8, 0x1F, 0xD3, 0x00, 0x40,
            0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x02,
            0x81, config.DAY_CONTRAST, 0xD9, 0xF1, 0xDB, 0x40,
            0xA4, 0xA6, 0xAF,
        ]

    def _init_display(self):
        for c in self._init_sequence():
            self.cmd(c)

    def contrast(self, value):
        self.cmd(0x81)
        self.cmd(max(0, min(255, int(value))))

    def power(self, enabled):
        enabled = bool(enabled)
        if enabled != self._display_on:
            if self.cmd(0xAF if enabled else 0xAE):
                self._display_on = enabled

    def clear(self):
        blank = Image.new("1", (self.width, self.height), 0)
        self.show(blank, force=True)

    def image(self):
        return Image.new("1", (self.width, self.height), 0)

    def draw(self, image):
        return ImageDraw.Draw(image)

    def _pages(self, image):
        image = image.convert("1")
        pages = []
        for page in range(self.height // 8):
            buf = []
            for x in range(self.width):
                b = 0
                for bit in range(8):
                    y = page * 8 + bit
                    if image.getpixel((x, y)) == 255:
                        b |= 1 << bit
                buf.append(b)
            pages.append(buf)
        return pages

    @staticmethod
    def _changed_runs(current, previous):
        start = None
        for index, value in enumerate(current):
            changed = previous is None or previous[index] != value
            if changed and start is None:
                start = index
            elif not changed and start is not None:
                yield start, index
                start = None
        if start is not None:
            yield start, len(current)

    def _write_page_run(self, page, start, values):
        if not self.cmd(0xB0 + page):
            self.page_write_failures += 1
            self.request_force_refresh()
            return False
        if not self.cmd(start & 0x0F):
            self.page_write_failures += 1
            self.request_force_refresh()
            return False
        if not self.cmd(0x10 | ((start >> 4) & 0x0F)):
            self.page_write_failures += 1
            self.request_force_refresh()
            return False
        if not self.data(values):
            self.page_write_failures += 1
            self.request_force_refresh()
            return False
        return True

    def show(self, image, force=False):
        self.power(True)
        now = time.monotonic()
        full_refresh = bool(force or self.refresh_due(now))
        pages = self._pages(image)
        previous = self._last_pages
        updated = False
        failed = False

        for page, buf in enumerate(pages):
            old = None if full_refresh or previous is None else previous[page]
            for start, end in self._changed_runs(buf, old):
                if self._write_page_run(page, start, buf[start:end]):
                    updated = True
                else:
                    failed = True

        if failed:
            # Never publish a cache that may differ from the hardware framebuffer.
            self._last_pages = None
            self.request_force_refresh()
            return False

        self._last_pages = pages
        if full_refresh:
            self.full_refreshes += 1
            self.last_full_refresh = now
            self._force_next_frame = False
        elif updated:
            self.partial_updates += 1
        return True

    def _fit(self, text, max_px=128):
        text = str(text)
        if self.draw(self.image()).textlength(text, font=self.font) <= max_px:
            return text
        ellipsis = "…"
        while text and self.draw(self.image()).textlength(text + ellipsis, font=self.font) > max_px:
            text = text[:-1]
        return text + ellipsis if text else ""

    def text_screen(self, lines, shift=(0, 0), force=False):
        img = self.image()
        d = self.draw(img)
        x0, y0 = shift
        max_px = self.width - max(0, x0) - 1
        for y, line in zip((0 + y0, 10 + y0, 20 + y0), lines[:3]):
            d.text((x0, y), self._fit(line, max_px), font=self.font, fill=255)
        return self.show(img, force=force)

    def popup(self, title, line2="", line3=""):
        img = self.image()
        d = self.draw(img)
        d.rectangle((0, 0, self.width - 1, self.height - 1), outline=255)
        d.text((8, 2), self._fit(title, 108), font=self.font, fill=255)
        if line2:
            d.text((8, 13), self._fit(line2, 108), font=self.font, fill=255)
        if line3:
            d.text((8, 22), self._fit(line3, 108), font=self.font, fill=255)
        self.show(img)

    def loading(self, pct):
        img = self.image()
        d = self.draw(img)
        d.text((18, 0), "NetWatchDog", font=self.font, fill=255)
        d.text((38, 10), "Loading", font=self.font, fill=255)
        d.rectangle((14, 24, 114, 31), outline=255)
        fill = int(96 * max(0, min(100, pct)) / 100)
        if fill > 0:
            d.rectangle((16, 26, 16 + fill, 29), fill=255)
        self.show(img)
