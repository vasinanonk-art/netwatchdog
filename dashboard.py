#!/usr/bin/env python3
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from netwatchdog_common import HISTORY_PATH, STATUS_PATH, VERSION, load_config, read_events, read_json, run_cmd

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NetWatchDog</title><style>:root{color-scheme:dark}body{margin:0;background:#0e1117;color:#e6edf3;font:14px system-ui}.wrap{max-width:1180px;margin:auto;padding:18px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:14px 0}.card{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:14px}.big{font-size:28px;font-weight:700}.muted{color:#8b949e}.ok{color:#3fb950}.warn{color:#d29922}.bad{color:#f85149}a{color:#58a6ff;margin-right:12px;text-decoration:none}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #30363d;text-align:left}pre{white-space:pre-wrap;overflow:auto}.bar{height:42px;display:flex;gap:2px;align-items:end}.bar span{display:block;flex:1;background:#58a6ff55;min-width:2px}button{margin:4px 6px 4px 0;padding:9px 12px;border:1px solid #30363d;border-radius:9px;background:#21262d;color:#e6edf3}@media(max-width:640px){.top{display:block}.big{font-size:24px}}</style></head><body><div class="wrap"><div class="top"><div><h1>NetWatchDog v5.1</h1><div class="muted">/run/netwatchdog/status.json</div></div><nav><a href="/">Home</a><a href="/advanced">Advanced</a><a href="/history">History</a><a href="/service">Service</a></nav></div><div id="app"></div></div><script>
const path=location.pathname;
const fmt=t=>t?new Date(t*1000).toLocaleString():'-';
const fmtTime=t=>t?new Date(t*1000).toLocaleTimeString():'-';
const cls=s=>s==='OK'||s==='active'?'ok':(s==='DEGRADED'||s==='missing'?'warn':'bad');
const pct=v=>{if(v===null||v===undefined)return '-';let n=Number(v);if(!Number.isFinite(n))return '-';if(n>0&&n<1)return '<1%';return (Number.isInteger(n)?n:n.toFixed(1))+'%'};
async function api(p,o){let r=await fetch(p,o);return await r.json()}
function card(t,v,c=''){return `<div class="card"><div class="muted">${t}</div><div class="big ${c}">${v??'-'}</div></div>`}
function bars(h,k){return `<div class="bar">${h.slice(-80).map(x=>`<span title="${k}: ${x[k]??'-'}" style="height:${Math.max(2,Math.min(100,Number(x[k]||0)))}%"></span>`).join('')}</div>`}
function eventLabel(x){const map={'NET OK':'Internet Restored','NET LOST':'Internet Lost','GW LOST':'Gateway Lost','FAILOVER':'Failover','RESTORED':'Restored','BOOT':'Boot'};return map[x]||x}
async function draw(){let s=await api('/api/status'),h=await api('/api/history'),e=await api('/api/events'),app=document.getElementById('app'),health=s.health||{},m=s.metrics||{},n=s.network||{};if(path==='/history'){app.innerHTML=`<div class="grid"><div class="card"><b>CPU</b>${bars(h,'cpu')}</div><div class="card"><b>RAM</b>${bars(h,'ram')}</div><div class="card"><b>RSSI</b>${bars(h,'rssi')}</div><div class="card"><b>Gateway Ping</b>${bars(h,'gateway_ms')}</div><div class="card"><b>Internet Ping</b>${bars(h,'internet_ms')}</div><div class="card"><b>Health</b>${bars(h,'health')}</div></div>`;return}if(path==='/service'){app.innerHTML=`<div class="card"><b>System Control</b><p class="muted">Allowlist only. No arbitrary shell execution.</p><button onclick="act('netwatchdog-oled')">Restart OLED</button><button onclick="act('netwatchdog')">Restart Status Writer</button><button onclick="act('netwatchdog-dashboard')">Restart Dashboard</button><pre id="out"></pre></div><div class="card"><b>Services</b><table>${Object.entries(s.services||{}).map(([k,v])=>`<tr><td>${k}</td><td class="${cls(v)}">${v}</td></tr>`).join('')}</table></div>`;return}if(path==='/advanced'){app.innerHTML=`<div class="grid">${card('Version',s.version)}${card('Git Commit',s.git_commit)}${card('Uptime',Math.round((s.uptime_sec||0)/60)+' min')}${card('Disk',pct(m.disk))}</div><div class="card"><b>Raw Status</b><pre>${JSON.stringify(s,null,2)}</pre></div>`;return}app.innerHTML=`<div class="grid">${card('Health',health.score+'%',cls(health.status))}${card('Status',health.status,cls(health.status))}${card('Active Route',s.active)}${card('CPU',pct(m.cpu))}${card('RAM',pct(m.ram))}${card('Temp',(m.temp??'-')+'°C')}${card('RSSI',(n.usb&&n.usb.signal_dbm)||'-')}${card('Internet',n.internet_ms===null?'Lost':n.internet_ms+' ms',n.internet_ms===null?'bad':'ok')}</div><div class="grid"><div class="card"><b>Health Detail</b><ul>${(health.reasons||[]).map(x=>`<li>${x}</li>`).join('')}</ul></div><div class="card"><b>Recent Events</b><table>${e.slice(-10).reverse().map(x=>`<tr><td>${fmtTime(x.ts)}</td><td>${eventLabel(x.event)}</td><td class="muted">${x.detail||''}</td></tr>`).join('')}</table></div></div>`}
async function act(service){document.getElementById('out').textContent='Running...';document.getElementById('out').textContent=JSON.stringify(await api('/api/restart?service='+encodeURIComponent(service),{method:'POST'}),null,2)}draw();setInterval(draw,5000);
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None: return
    def send_json(self, payload: object, code: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode(); self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self) -> None:
        p = urlparse(self.path).path
        if p == "/api/status": self.send_json(read_json(STATUS_PATH, {"version": VERSION, "health": {"score": 0, "status": "CRITICAL", "reasons": ["Status not ready"]}})); return
        if p == "/api/history": self.send_json(read_json(HISTORY_PATH, [])); return
        if p == "/api/events": self.send_json(read_events(50)); return
        if p in {"/", "/advanced", "/history", "/service"}:
            data = HTML.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_json({"error": "not found"}, 404)
    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/restart": self.send_json({"error": "not found"}, 404); return
        service = parse_qs(parsed.query).get("service", [""])[0]; allowed = set(load_config()["watchdog"].get("control_services", []))
        if service not in allowed: self.send_json({"ok": False, "error": "service not allowed"}, 403); return
        code, out = run_cmd(["systemctl", "restart", service], 20); self.send_json({"ok": code == 0, "service": service, "output": out})

def main() -> None:
    cfg = load_config()["dashboard"]; ThreadingHTTPServer((str(cfg["host"]), int(cfg["port"])), Handler).serve_forever()
if __name__ == "__main__": main()
