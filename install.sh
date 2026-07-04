#!/bin/sh
set -eu

install -d /opt/netwatchdog
install -m 0755 netwatchdog.py /opt/netwatchdog/netwatchdog.py
install -m 0644 netwatchdog.service /etc/systemd/system/netwatchdog.service

systemctl daemon-reload
systemctl enable netwatchdog
systemctl restart netwatchdog

systemctl status netwatchdog --no-pager -l || true
