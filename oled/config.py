"""NetWatchDog OLED configuration."""

try:
    from core_config import get, get_bool, get_int, load_config
except Exception:
    get = get_bool = get_int = load_config = None

_cfg = load_config() if load_config else {}

I2C_BUS = 4
I2C_ADDR = 0x3C
WIDTH = 128
HEIGHT = 32

PRIMARY_IFACE = get(_cfg, "primary.interface", "wlx6c4cbcdb7033") if get else "wlx6c4cbcdb7033"
BACKUP_IFACE = get(_cfg, "backup.interface", "wlan0") if get else "wlan0"
GATEWAY_HOST = get(_cfg, "gateway.host", "192.168.1.1") if get else "192.168.1.1"
INTERNET_HOST = get(_cfg, "internet.host", "1.1.1.1") if get else "1.1.1.1"

STATUS_PATHS = [
    get(_cfg, "status.path", "/run/netwatchdog/status.json") if get else "/run/netwatchdog/status.json",
]

PAGE_INTERVAL_SEC = 3
POPUP_SEC = get_int(_cfg, "oled.popup_timeout_sec", 8) if get_int else 8
PIXEL_SHIFT = get_bool(_cfg, "oled.pixel_shift", True) if get_bool else True
BURN_SHIFT_SEC = get_int(_cfg, "oled.burn_shift_sec", 300) if get_int else 300
SCREEN_SAVER_SEC = get_int(_cfg, "oled.screen_saver_sec", 300) if get_int else 300
SCREEN_SAVER_BLANK_SEC = get_int(_cfg, "oled.screen_saver_blank_sec", 2) if get_int else 2

BRIGHTNESS_ENABLED = get_bool(_cfg, "oled.brightness_enabled", True) if get_bool else True
DAY_CONTRAST = get_int(_cfg, "oled.day_brightness", 160) if get_int else 160
NIGHT_CONTRAST = get_int(_cfg, "oled.night_brightness", 40) if get_int else 40
DAY_START_HOUR = get_int(_cfg, "oled.day_start_hour", 7) if get_int else 7
NIGHT_START_HOUR = get_int(_cfg, "oled.night_start_hour", 22) if get_int else 22
