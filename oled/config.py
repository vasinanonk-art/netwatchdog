"""NetWatchDog OLED configuration."""

I2C_BUS = 4
I2C_ADDR = 0x3C
WIDTH = 128
HEIGHT = 32

PRIMARY_IFACE = "wlx6c4cbcdb7033"
BACKUP_IFACE = "wlan0"
GATEWAY_HOST = "192.168.1.1"
INTERNET_HOST = "1.1.1.1"

STATUS_PATHS = [
    "/run/netwatchdog/status.json",
    "/opt/netwatchdog-run/status.json",
]

PAGE_INTERVAL_SEC = 3
POPUP_SEC = 5
BURN_SHIFT_SEC = 60

DAY_CONTRAST = 200
NIGHT_CONTRAST = 70
DAY_START_HOUR = 7
NIGHT_START_HOUR = 22
