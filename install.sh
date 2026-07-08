#!/bin/sh
set -eu

APP_DIR=/opt/netwatchdog
CFG_DIR=/etc/netwatchdog

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo ./install.sh" >&2
  exit 1
fi

apt-get update
apt-get install -y --no-install-recommends python3 git iproute2 iputils-ping wireless-tools iw ca-certificates

install -d "$APP_DIR" "$CFG_DIR" /run/netwatchdog /var/lib/netwatchdog/backups /var/log/netwatchdog
install -m 0755 netwatchdog.py "$APP_DIR/netwatchdog.py"
install -m 0755 status_writer.py "$APP_DIR/status_writer.py"
install -m 0644 core_config.py "$APP_DIR/core_config.py"
install -m 0644 event_engine.py "$APP_DIR/event_engine.py"
install -m 0644 health_engine.py "$APP_DIR/health_engine.py"
install -m 0644 history_engine.py "$APP_DIR/history_engine.py"
install -m 0644 netwatchdog_common.py "$APP_DIR/netwatchdog_common.py"
install -m 0755 dashboard.py "$APP_DIR/dashboard.py"
install -m 0755 netwatchdogctl.py "$APP_DIR/netwatchdogctl.py"
ln -sf "$APP_DIR/netwatchdogctl.py" /usr/local/bin/netwatchdogctl

if [ ! -f "$CFG_DIR/config.yaml" ]; then
  install -m 0644 config/netwatchdog.yaml.example "$CFG_DIR/config.yaml"
fi

install -m 0644 netwatchdog.service /etc/systemd/system/netwatchdog.service
install -m 0644 netwatchdog-dashboard.service /etc/systemd/system/netwatchdog-dashboard.service
if [ -f service/netwatchdog-status.service ]; then
  install -m 0644 service/netwatchdog-status.service /etc/systemd/system/netwatchdog-status.service
fi
if [ -f service/netwatchdog-oled.service ]; then
  install -m 0644 service/netwatchdog-oled.service /etc/systemd/system/netwatchdog-oled.service
fi

systemctl daemon-reload
systemctl enable netwatchdog netwatchdog-dashboard
systemctl restart netwatchdog
systemctl restart netwatchdog-dashboard
if systemctl list-unit-files netwatchdog-status.service >/dev/null 2>&1; then
  systemctl enable netwatchdog-status || true
  systemctl restart netwatchdog-status || true
fi

systemctl status netwatchdog --no-pager -l || true
systemctl status netwatchdog-dashboard --no-pager -l || true
