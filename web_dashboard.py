#!/usr/bin/env python3
"""Minimal NetWatchDog Web Dashboard.

No external dependencies. Reads the same status.json and event log used by OLED.
"""

import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from core_config import get, get_int, load_config
from event_engine import tail

cfg = load_config()
HOST = os.environ.get("NWD_WEB_HOST", "0.0.0.0")
PORT = int(os.environ.get("NWD_WEB_PORT", get_int(cfg, "web.port", 8080)))
STATUS_PATH = Path(os.environ.get("NWD_STATUS_PATH", get(cfg, "status.path")))
EVENT_LOG = Path(os.environ.get("NWD_EVENT_LOG", get(cfg, "event.log")))


def read_status():
    if not STATUS_PATH.exists():
        return {"error": "status.json not found"}
    try:
        return json.loads(STATUS_PATH.read_text())
    except Exception as exc:
        return {"error": str(exc)}


def json_response(handler, data, status=200):
    body = json.dumps(data, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def html_page(status, events):
    def v(key, default="-"):
        return html.escape(str(status.get(key, default)))

    ok = bool(status.get("internet")) and bool(status.get("gateway"))
    color = "#16a34a" if ok else "#dc2626"
    event_items = "".join(f"<li>{html.escape(line)}</li>" for line in events[-20:]) or "<li>No events</li>"

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="5">
<title>NetWatchDog</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#0f172a;color:#e5e7eb;margin:0;padding:20px}}
.container{{max-width:980px;margin:auto}}
.header{{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}}
.badge{{background:{color};color:white;padding:10px 16px;border-radius:999px;font-weight:700}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:18px}}
.card{{background:#111827;border:1px solid #1f2937;border-radius:16px;padding:16px;box-shadow:0 10px 20px rgba(0,0,0,.18)}}
.card h2{{font-size:14px;color:#94a3b8;margin:0 0 12px;text-transform:uppercase;letter-spacing:.08em}}
.value{{font-size:28px;font-weight:800;margin:0}}
.small{{color:#94a3b8;font-size:13px;margin-top:6px}}
ul{{margin:0;padding-left:20px;line-height:1.7;font-family:ui-monospace,Menlo,monospace;font-size:13px}}
a{{color:#93c5fd}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>NetWatchDog</h1>
      <div class="small">Version {v('version')} · Updated {v('updated_at')}</div>
    </div>
    <div class="badge">Health {v('health')}%</div>
  </div>

  <div class="grid">
    <div class="card"><h2>Mode</h2><p class="value">{v('mode')}</p><div class="small">Iface {v('iface')}</div></div>
    <div class="card"><h2>Network</h2><p class="value">GW {v('gateway')}</p><div class="small">NET {v('internet')} · Ping {v('last_ping')} ms</div></div>
    <div class="card"><h2>System</h2><p class="value">CPU {v('cpu')}%</p><div class="small">RAM {v('ram')}% · Temp {v('temp')}C</div></div>
    <div class="card"><h2>Wireless</h2><p class="value">{v('rssi')} dBm</p><div class="small">IP {v('ip')}</div></div>
    <div class="card"><h2>Watchdog</h2><p class="value">Retry {v('retry')}</p><div class="small">Failover {v('failover')} · Restore {v('restore')}</div></div>
    <div class="card"><h2>Last Event</h2><p class="value">{v('last_event')}</p><div class="small">{v('last_event_at')}</div></div>
  </div>

  <div class="card" style="margin-top:14px">
    <h2>Recent Events</h2>
    <ul>{event_items}</ul>
  </div>
</div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            return json_response(self, read_status())
        if path == "/api/events":
            return json_response(self, {"events": tail(EVENT_LOG, 100)})
        if path == "/healthz":
            return json_response(self, {"ok": True})
        if path in ("/", "/index.html"):
            status = read_status()
            events = tail(EVENT_LOG, 50)
            body = html_page(status, events).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"NetWatchDog dashboard listening on {HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
