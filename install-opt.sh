#!/bin/sh
set -eu

SRC_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DEST_DIR="/opt/netwatchdog-run"

install -d "$DEST_DIR"
install -m 0755 "$SRC_DIR/netwatchdog.py" "$DEST_DIR/netwatchdog.py"
install -m 0644 "$SRC_DIR/netwatchdog.service" /etc/systemd/system/netwatchdog.service

sed -i 's|WorkingDirectory=/opt/netwatchdog|WorkingDirectory=/opt/netwatchdog-run|' /etc/systemd/system/netwatchdog.service
sed -i 's|ExecStart=/usr/bin/python3 /opt/netwatchdog/netwatchdog.py|ExecStart=/usr/bin/python3 /opt/netwatchdog-run/netwatchdog.py|' /etc/systemd/system/netwatchdog.service

systemctl daemon-reload
systemctl enable netwatchdog
systemctl restart netwatchdog
systemctl status netwatchdog --no-pager -l || true
