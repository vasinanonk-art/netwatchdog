"""Minimal SSD1306 128x32 I2C driver for NetWatchDog OLED.

No luma.oled, no pip dependencies. Uses Debian python3-smbus + Pillow.
"""

import smbus
from PIL import Image, ImageDraw, ImageFont

from . import config


class OLED:
    def __init__(self, bus=config.I2C_BUS, addr=config.I2C_ADDR):
        self.bus = smbus.SMBus(bus)
        self.addr = addr
        self.width = config.WIDTH
        self.height = config.HEIGHT
        self.font = ImageFont.load_default()
        self._init_display()

    def cmd(self, value):
        self.bus.write_i2c_block_data(self.addr, 0x00, [value])

    def data(self, values):
        for i in range(0, len(values), 16):
            self.bus.write_i2c_block_data(self.addr, 0x40, values[i:i + 16])

    def _init_display(self):
        for c in [
            0xAE, 0xD5, 0x80, 0xA8, 0x1F, 0xD3, 0x00, 0x40,
            0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x02,
            0x81, config.DAY_CONTRAST, 0xD9, 0xF1, 0xDB, 0x40,
            0xA4, 0xA6, 0xAF,
        ]:
            self.cmd(c)

    def contrast(self, value):
        self.cmd(0x81)
        self.cmd(max(0, min(255, int(value))))

    def clear(self):
        blank = Image.new("1", (self.width, self.height), 0)
        self.show(blank)

    def image(self):
        return Image.new("1", (self.width, self.height), 0)

    def draw(self, image):
        return ImageDraw.Draw(image)

    def show(self, image):
        image = image.convert("1")
        for page in range(4):
            self.cmd(0xB0 + page)
            self.cmd(0x00)
            self.cmd(0x10)
            buf = []
            for x in range(self.width):
                b = 0
                for bit in range(8):
                    y = page * 8 + bit
                    if image.getpixel((x, y)) == 255:
                        b |= 1 << bit
                buf.append(b)
            self.data(buf)

    def text_screen(self, lines, shift=(0, 0)):
        img = self.image()
        d = self.draw(img)
        x0, y0 = shift
        y = y0
        for line in lines[:3]:
            d.text((x0, y), line, font=self.font, fill=255)
            y += 11
        self.show(img)

    def popup(self, title, line2="", line3=""):
        img = self.image()
        d = self.draw(img)
        d.rectangle((0, 0, self.width - 1, self.height - 1), outline=255)
        d.text((8, 3), title[:18], font=self.font, fill=255)
        if line2:
            d.text((8, 14), line2[:18], font=self.font, fill=255)
        if line3:
            d.text((8, 23), line3[:18], font=self.font, fill=255)
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
