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
install -m 0644 netwatchdog_common.py "$APP_DIR/netwatchdog_common.py"
install -m 0755 dashboard.py "$APP_DIR/dashboard.py"
install -m 0755 netwatchdogctl.py "$APP_DIR/netwatchdogctl.py"
ln -sf "$APP_DIR/netwatchdogctl.py" /usr/local/bin/netwatchdogctl

if [ ! -f "$CFG_DIR/config.yaml" ]; then
  install -m 0644 config.yaml "$CFG_DIR/config.yaml"
fi

install -m 0644 netwatchdog.service /etc/systemd/system/netwatchdog.service
install -m 0644 netwatchdog-dashboard.service /etc/systemd/system/netwatchdog-dashboard.service

systemctl daemon-reload
systemctl enable netwatchdog netwatchdog-dashboard
systemctl restart netwatchdog
systemctl restart netwatchdog-dashboard

systemctl status netwatchdog --no-pager -l || true
systemctl status netwatchdog-dashboard --no-pager -l || true
