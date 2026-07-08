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

    def show(self, image, force=False):
        self.power(True)
        pages = self._pages(image)
        previous = self._last_pages
        changed = False
        for page, buf in enumerate(pages):
            if not force and previous is not None and previous[page] == buf:
                continue
            if not self.cmd(0xB0 + page):
                continue
            if not self.cmd(0x00):
                continue
            if not self.cmd(0x10):
                continue
            if self.data(buf):
                changed = True
        if changed or force or previous is None:
            self._last_pages = pages

    def _fit(self, text, max_px=128):
        text = str(text)
        if self.draw(self.image()).textlength(text, font=self.font) <= max_px:
            return text
        ellipsis = "…"
        while text and self.draw(self.image()).textlength(text + ellipsis, font=self.font) > max_px:
            text = text[:-1]
        return text + ellipsis if text else ""

    def text_screen(self, lines, shift=(0, 0)):
        img = self.image()
        d = self.draw(img)
        x0, y0 = shift
        max_px = self.width - max(0, x0) - 1
        for y, line in zip((0 + y0, 10 + y0, 20 + y0), lines[:3]):
            d.text((x0, y), self._fit(line, max_px), font=self.font, fill=255)
        self.show(img)

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
