#!/bin/sh
set -eu

APP_DIR=/opt/netwatchdog
CFG_DIR=/etc/netwatchdog
SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
STATE_DIR=/var/lib/netwatchdog/install-state

NETWATCHDOG_CHANGED=0
DASHBOARD_CHANGED=0
OLED_CHANGED=0
UNITS_CHANGED=0

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo sh install.sh" >&2
  exit 1
fi

real_path() {
  if [ -e "$1" ]; then
    readlink -f "$1"
  else
    printf '%s\n' "$1"
  fi
}

state_key() {
  printf '%s' "$1" | sed 's#[^A-Za-z0-9_.-]#_#g'
}

file_hash() {
  cksum "$1" | awk '{print $1":"$2}'
}

copy_file() {
  src="$SRC_DIR/$1"
  dst="$2"
  mode="$3"
  if [ ! -f "$src" ]; then
    echo "missing source: $src" >&2
    exit 1
  fi

  src_real=$(real_path "$src")
  dst_real=$(real_path "$dst")
  src_hash=$(file_hash "$src")
  state_file="$STATE_DIR/$(state_key "$dst").cksum"
  old_hash=$(cat "$state_file" 2>/dev/null || true)
  changed=1

  if [ -e "$dst" ] && [ "$old_hash" = "$src_hash" ]; then
    changed=0
  fi

  if [ "$src_real" = "$dst_real" ]; then
    chmod "$mode" "$dst"
  else
    if [ ! -e "$dst" ] || ! cmp -s "$src" "$dst"; then
      install -m "$mode" "$src" "$dst"
      changed=1
    else
      chmod "$mode" "$dst"
    fi
  fi

  printf '%s\n' "$src_hash" > "$state_file"
  [ "$changed" -eq 1 ]
}

restart_if_changed() {
  service="$1"
  changed="$2"
  if [ "$changed" -eq 1 ]; then
    if systemctl cat "$service" >/dev/null 2>&1; then
      systemctl restart "$service"
    fi
  fi
}

apt-get update
apt-get install -y --no-install-recommends python3 git iproute2 iputils-ping wireless-tools iw ca-certificates logrotate

install -d "$APP_DIR" "$CFG_DIR" /run/netwatchdog /var/lib/netwatchdog/backups /var/log/netwatchdog /etc/logrotate.d "$STATE_DIR"

if copy_file netwatchdog.py "$APP_DIR/netwatchdog.py" 0755; then NETWATCHDOG_CHANGED=1; fi
if copy_file status_writer.py "$APP_DIR/status_writer.py" 0755; then NETWATCHDOG_CHANGED=1; fi
if copy_file core_config.py "$APP_DIR/core_config.py" 0644; then NETWATCHDOG_CHANGED=1; OLED_CHANGED=1; fi
if copy_file event_engine.py "$APP_DIR/event_engine.py" 0644; then NETWATCHDOG_CHANGED=1; fi
if copy_file health_engine.py "$APP_DIR/health_engine.py" 0644; then NETWATCHDOG_CHANGED=1; fi
if copy_file history_engine.py "$APP_DIR/history_engine.py" 0644; then NETWATCHDOG_CHANGED=1; fi
if copy_file netwatchdog_common.py "$APP_DIR/netwatchdog_common.py" 0644; then NETWATCHDOG_CHANGED=1; DASHBOARD_CHANGED=1; OLED_CHANGED=1; fi
if copy_file dashboard.py "$APP_DIR/dashboard.py" 0755; then DASHBOARD_CHANGED=1; fi
if copy_file netwatchdogctl.py "$APP_DIR/netwatchdogctl.py" 0755; then :; fi
ln -sf "$APP_DIR/netwatchdogctl.py" /usr/local/bin/netwatchdogctl

if [ ! -f "$CFG_DIR/config.yaml" ]; then
  install -m 0644 "$SRC_DIR/config/netwatchdog.yaml.example" "$CFG_DIR/config.yaml"
  NETWATCHDOG_CHANGED=1
  DASHBOARD_CHANGED=1
  OLED_CHANGED=1
fi

if [ -f "$SRC_DIR/logrotate/netwatchdog" ]; then
  if copy_file logrotate/netwatchdog /etc/logrotate.d/netwatchdog 0644; then :; fi
fi

if copy_file netwatchdog.service /etc/systemd/system/netwatchdog.service 0644; then NETWATCHDOG_CHANGED=1; UNITS_CHANGED=1; fi
if copy_file netwatchdog-dashboard.service /etc/systemd/system/netwatchdog-dashboard.service 0644; then DASHBOARD_CHANGED=1; UNITS_CHANGED=1; fi
if [ -f "$SRC_DIR/service/netwatchdog-oled.service" ]; then
  if copy_file service/netwatchdog-oled.service /etc/systemd/system/netwatchdog-oled.service 0644; then OLED_CHANGED=1; UNITS_CHANGED=1; fi
fi

systemctl disable --now netwatchdog-web.service 2>/dev/null || true
systemctl disable --now netwatchdog-status.service 2>/dev/null || true
if [ "$UNITS_CHANGED" -eq 1 ]; then
  systemctl daemon-reload
fi
systemctl enable netwatchdog netwatchdog-dashboard
if systemctl cat netwatchdog-oled >/dev/null 2>&1; then
  systemctl enable netwatchdog-oled >/dev/null 2>&1 || true
fi

restart_if_changed netwatchdog "$NETWATCHDOG_CHANGED"
restart_if_changed netwatchdog-dashboard "$DASHBOARD_CHANGED"
restart_if_changed netwatchdog-oled "$OLED_CHANGED"

systemctl status netwatchdog --no-pager -l || true
systemctl status netwatchdog-dashboard --no-pager -l || true
