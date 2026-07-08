#!/bin/sh
set -eu

APP_DIR=/opt/netwatchdog
CFG_DIR=/etc/netwatchdog
SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo sh install.sh" >&2
  exit 1
fi

copy_file() {
  src="$SRC_DIR/$1"
  dst="$2"
  mode="$3"
  if [ ! -f "$src" ]; then
    echo "missing source: $src" >&2
    exit 1
  fi
  if [ "$(readlink -f "$src")" = "$(readlink -f "$dst" 2>/dev/null || true)" ]; then
    chmod "$mode" "$dst"
    return
  fi
  install -m "$mode" "$src" "$dst"
}

apt-get update
apt-get install -y --no-install-recommends python3 git iproute2 iputils-ping wireless-tools iw ca-certificates

install -d "$APP_DIR" "$CFG_DIR" /run/netwatchdog /var/lib/netwatchdog/backups /var/log/netwatchdog
copy_file netwatchdog.py "$APP_DIR/netwatchdog.py" 0755
copy_file status_writer.py "$APP_DIR/status_writer.py" 0755
copy_file core_config.py "$APP_DIR/core_config.py" 0644
copy_file event_engine.py "$APP_DIR/event_engine.py" 0644
copy_file health_engine.py "$APP_DIR/health_engine.py" 0644
copy_file history_engine.py "$APP_DIR/history_engine.py" 0644
copy_file netwatchdog_common.py "$APP_DIR/netwatchdog_common.py" 0644
copy_file dashboard.py "$APP_DIR/dashboard.py" 0755
copy_file netwatchdogctl.py "$APP_DIR/netwatchdogctl.py" 0755
ln -sf "$APP_DIR/netwatchdogctl.py" /usr/local/bin/netwatchdogctl

if [ ! -f "$CFG_DIR/config.yaml" ]; then
  install -m 0644 "$SRC_DIR/config/netwatchdog.yaml.example" "$CFG_DIR/config.yaml"
fi

copy_file netwatchdog.service /etc/systemd/system/netwatchdog.service 0644
copy_file netwatchdog-dashboard.service /etc/systemd/system/netwatchdog-dashboard.service 0644
if [ -f "$SRC_DIR/service/netwatchdog-oled.service" ]; then
  copy_file service/netwatchdog-oled.service /etc/systemd/system/netwatchdog-oled.service 0644
fi

systemctl disable --now netwatchdog-web.service 2>/dev/null || true
systemctl disable --now netwatchdog-status.service 2>/dev/null || true
systemctl daemon-reload
systemctl enable netwatchdog netwatchdog-dashboard
systemctl restart netwatchdog
systemctl restart netwatchdog-dashboard

systemctl status netwatchdog --no-pager -l || true
systemctl status netwatchdog-dashboard --no-pager -l || true
