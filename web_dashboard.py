#!/usr/bin/env python3
"""Minimal NetWatchDog Web Dashboard.

No external dependencies. Reads the same status.json and event log used by OLED.
"""

import html
import json
import os
from datetime import datetime, timezone
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


def html_response(handler, body):
    payload = body.encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def html_page():
    return """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NetWatchDog</title>
<style>
:root{--bg:#0f172a;--card:#111827;--line:#1f2937;--text:#e5e7eb;--muted:#94a3b8;--green:#16a34a;--yellow:#ca8a04;--red:#dc2626}
*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:var(--bg);color:var(--text);margin:0;padding:20px}.container{max-width:1200px;margin:auto}.header{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}h1{margin:0 0 10px;font-size:34px}.badge{color:white;padding:10px 16px;border-radius:999px;font-weight:800}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:18px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:0 10px 20px rgba(0,0,0,.18)}.card h2{font-size:14px;color:var(--muted);margin:0 0 12px;text-transform:uppercase;letter-spacing:.08em}.value{font-size:28px;font-weight:850;margin:0}.small{color:var(--muted);font-size:13px;margin-top:6px}.ok{color:#4ade80}.warn{color:#facc15}.bad{color:#f87171}ul{margin:0;padding-left:20px;line-height:1.7;font-family:ui-monospace,Menlo,monospace;font-size:13px}.dot{display:inline-block;width:9px;height:9px;border-radius:99px;margin-right:7px;background:var(--green)}.dot.bad{background:var(--red)}.dot.warn{background:var(--yellow)}@media(max-width:600px){body{padding:14px}h1{font-size:28px}.value{font-size:24px}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>NetWatchDog</h1>
      <div class="small">Version <span id="version">-</span> · Updated <span id="updated">-</span></div>
    </div>
    <div id="healthBadge" class="badge">Health -%</div>
  </div>

  <div class="grid">
    <div class="card"><h2>Mode</h2><p id="mode" class="value">-</p><div id="iface" class="small">Iface -</div></div>
    <div class="card"><h2>Gateway</h2><p id="gateway" class="value">-</p><div id="gatewayDetail" class="small">Ping - ms</div></div>
    <div class="card"><h2>Internet</h2><p id="internet" class="value">-</p><div id="internetDetail" class="small">Ping - ms</div></div>
    <div class="card"><h2>System</h2><p id="cpu" class="value">CPU -%</p><div id="systemDetail" class="small">RAM -% · Temp -C</div></div>
    <div class="card"><h2>Wireless</h2><p id="rssi" class="value">- dBm</p><div id="wifiDetail" class="small">IP -</div></div>
    <div class="card"><h2>Watchdog</h2><p id="retry" class="value">Retry -</p><div id="watchdogDetail" class="small">Failover - · Restore -</div></div>
    <div class="card"><h2>Last Event</h2><p id="lastEvent" class="value">-</p><div id="lastEventAt" class="small">-</div></div>
  </div>

  <div class="card" style="margin-top:14px">
    <h2>Recent Events</h2>
    <ul id="events"><li>Loading...</li></ul>
  </div>
</div>
<script>
function cls(ok){return ok ? 'ok' : 'bad'}
function boolText(ok){return ok ? 'Online' : 'Offline'}
function healthColor(v){return v >= 90 ? 'var(--green)' : (v >= 70 ? 'var(--yellow)' : 'var(--red)')}
function rssiQuality(v){if(v===null||v===undefined)return 'Unknown'; if(v>=-55)return 'Excellent'; if(v>=-67)return 'Good'; if(v>=-75)return 'Fair'; return 'Poor'}
function ageText(iso){if(!iso)return '-'; const t=Date.parse(iso); if(!t)return iso; const s=Math.max(0,Math.floor((Date.now()-t)/1000)); if(s<60)return s+' sec ago'; const m=Math.floor(s/60); if(m<60)return m+' min ago'; const h=Math.floor(m/60); return h+' hr ago'}
function timeText(iso){if(!iso)return '-'; const t=new Date(iso); if(isNaN(t))return iso; return t.toLocaleTimeString()}
function set(id,val){document.getElementById(id).textContent=val}
async function refresh(){
  const s=await fetch('/api/status',{cache:'no-store'}).then(r=>r.json()).catch(()=>({error:'offline'}));
  const ev=await fetch('/api/events',{cache:'no-store'}).then(r=>r.json()).catch(()=>({events:[]}));
  set('version', s.version || '-'); set('updated', ageText(s.updated_at));
  const health = Number(s.health ?? 0); const badge=document.getElementById('healthBadge'); badge.textContent='Health '+health+'%'; badge.style.background=healthColor(health);
  set('mode', s.mode || '-'); set('iface', 'Iface '+(s.iface || '-'));
  const gw=document.getElementById('gateway'); gw.textContent=boolText(!!s.gateway); gw.className='value '+cls(!!s.gateway); set('gatewayDetail','Ping '+(s.gateway_ping ?? s.last_ping ?? '-')+' ms');
  const net=document.getElementById('internet'); net.textContent=boolText(!!s.internet); net.className='value '+cls(!!s.internet); set('internetDetail','Ping '+(s.internet_ping ?? '-')+' ms');
  set('cpu','CPU '+(s.cpu ?? '-')+'%'); set('systemDetail','RAM '+(s.ram ?? '-')+'% · Temp '+(s.temp ?? '-')+'C');
  set('rssi',(s.rssi ?? '-')+' dBm'); set('wifiDetail','IP '+(s.ip || '-')+' · '+rssiQuality(s.rssi));
  set('retry','Retry '+(s.retry ?? '-')); set('watchdogDetail','Failover '+(s.failover ?? '-')+' · Restore '+(s.restore ?? '-'));
  set('lastEvent',s.last_event || '-'); set('lastEventAt',ageText(s.last_event_at));
  const list=document.getElementById('events'); const items=(ev.events||[]).slice(-20).reverse(); list.innerHTML=items.length?items.map(x=>'<li>'+String(x).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))+'</li>').join(''):'<li>No events</li>';
}
refresh(); setInterval(refresh,2000);
</script>
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
            return html_response(self, html_page())
        self.send_error(404)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"NetWatchDog dashboard listening on {HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
