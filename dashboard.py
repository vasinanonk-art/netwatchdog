#!/usr/bin/env python3
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from netwatchdog_common import HISTORY_PATH, STATUS_PATH, VERSION, load_config, read_events, read_json, run_cmd

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NetWatchDog</title><style>:root{color-scheme:dark}body{margin:0;background:#0e1117;color:#e6edf3;font:14px system-ui}.wrap{max-width:1180px;margin:auto;padding:18px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:14px 0}.card{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:14px}.big{font-size:28px;font-weight:700}.muted{color:#8b949e}.ok{color:#3fb950}.warn{color:#d29922}.bad{color:#f85149}a{color:#58a6ff;margin-right:12px;text-decoration:none}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #30363d;text-align:left}pre{white-space:pre-wrap;overflow:auto}.bar{height:42px;display:flex;gap:2px;align-items:end}.bar span{display:block;flex:1;background:#58a6ff55;min-width:2px}button{margin:4px 6px 4px 0;padding:9px 12px;border:1px solid #30363d;border-radius:9px;background:#21262d;color:#e6edf3}input{background:#0e1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:8px;min-width:210px}@media(max-width:640px){.top{display:block}.big{font-size:24px}}</style></head><body><div class="wrap"><div class="top"><div><h1>NetWatchDog v5.1</h1><div class="muted">/run/netwatchdog/status.json · NetWatchDog uses 8080 only · 8090 is Smart Condo Dashboard reserved</div></div><nav><a href="/">Home</a><a href="/advanced">Advanced</a><a href="/history">History</a><a href="/service">Service</a><a href="/tools">Tools</a></nav></div><div id="app"></div></div><script>
const path=location.pathname,fmt=t=>t?new Date(t*1000).toLocaleString():'-',fmtTime=t=>t?new Date(t*1000).toLocaleTimeString():'-',esc=x=>String(x??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const cls=s=>s===true||s==='OK'||s==='active'?'ok':(s==='DEGRADED'||s==='missing'||s===null?'warn':'bad');
const pct=v=>{if(v===null||v===undefined)return '-';let n=Number(v);if(!Number.isFinite(n))return '-';if(n>0&&n<1)return '<1%';return (Number.isInteger(n)?n:n.toFixed(1))+'%'};
async function api(p,o){let r=await fetch(p,o);return await r.json()}function card(t,v,c=''){return `<div class="card"><div class="muted">${t}</div><div class="big ${c}">${esc(v??'-')}</div></div>`}
function bars(h,k){let vals=h.slice(-120),mx=Math.max(1,...vals.map(x=>Number(x[k]||0)).filter(Number.isFinite));return `<div class="bar">${vals.map(x=>`<span title="${k}: ${x[k]??'-'}" style="height:${Math.max(2,Math.min(100,Number(x[k]||0)*100/mx))}%"></span>`).join('')}</div>`}
function eventLabel(x){const map={'NET OK':'Internet Restored','NET LOST':'Internet Lost','GW LOST':'Gateway Lost','FAILOVER':'Failover','RESTORED':'Restored','BOOT':'Boot'};return map[x]||x}
async function draw(){let s=await api('/api/status'),h=await api('/api/history'),e=await api('/api/events'),app=document.getElementById('app'),health=s.health||{},m=s.metrics||{},n=s.network||{};
if(path==='/history'){app.innerHTML=`<div class="grid"><div class="card"><b>CPU</b>${bars(h,'cpu')}</div><div class="card"><b>RAM</b>${bars(h,'ram')}</div><div class="card"><b>RSSI</b>${bars(h,'rssi')}</div><div class="card"><b>Gateway Ping</b>${bars(h,'gateway_ms')}</div><div class="card"><b>Internet Ping</b>${bars(h,'internet_ms')}</div><div class="card"><b>Health</b>${bars(h,'health')}</div></div>`;return}
if(path==='/service'){app.innerHTML=`<div class="card"><b>System Control</b><p class="muted">Allowlist only. No arbitrary shell execution. Smart Condo Dashboard / 8090 is blocked.</p><button onclick="act('netwatchdog-oled')">Restart OLED</button><button onclick="act('netwatchdog')">Restart Status Writer</button><button onclick="act('netwatchdog-dashboard')">Restart Dashboard</button><pre id="out"></pre></div><div class="card"><b>Services</b><table>${Object.entries(s.services||{}).map(([k,v])=>`<tr><td>${esc(k)}</td><td class="${cls(v)}">${esc(v)}</td></tr>`).join('')}</table></div>`;return}
if(path==='/tools'){let u=await api('/api/update-info');app.innerHTML=`<div class="grid">${card('Current Commit',u.current)}${card('Latest Commit',u.latest)}${card('Fetch',u.ok?'OK':'FAIL',u.ok?'ok':'bad')}</div><div class="card"><b>Operations</b><p><button onclick="tool('/api/selftest')">Self Test</button><button onclick="tool('/api/backup')">Backup</button><button onclick="tool('/api/update-pull')">Git Pull</button></p><p><input id="rollbackCommit" placeholder="rollback commit sha"><button onclick="rollback()">Rollback</button></p><pre id="toolOut"></pre></div>`;return}
if(path==='/advanced'){app.innerHTML=`<div class="grid">${card('Version',s.version)}${card('Git Commit',s.git_commit)}${card('Uptime',Math.round((s.uptime_sec||0)/60)+' min')}${card('Disk',pct(m.disk))}${card('Route',s.active)}${card('Internet Target',n.internet_target)}</div><div class="card"><b>Raw Status</b><pre>${esc(JSON.stringify(s,null,2))}</pre></div>`;return}
app.innerHTML=`<div class="grid">${card('Health',health.score+'%',cls(health.status))}${card('Status',health.status,cls(health.status))}${card('Active Route',s.active)}${card('CPU',pct(m.cpu))}${card('RAM',pct(m.ram))}${card('Temp',(m.temp??'-')+'°C')}${card('RSSI',(n.usb&&n.usb.signal_dbm)||'-')}${card('Internet',n.internet_ms===null?'Lost':n.internet_ms+' ms',n.internet_ms===null?'bad':'ok')}</div><div class="grid"><div class="card"><b>Health Detail</b><ul>${(health.reasons||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div><div class="card"><b>Recent Events</b><table>${e.slice(-10).reverse().map(x=>`<tr><td>${fmtTime(x.ts)}</td><td>${esc(eventLabel(x.event))}</td><td class="muted">${esc(x.detail||'')}</td></tr>`).join('')}</table></div></div>`}
async function act(service){document.getElementById('out').textContent='Running...';document.getElementById('out').textContent=JSON.stringify(await api('/api/restart?service='+encodeURIComponent(service),{method:'POST'}),null,2)}
async function tool(path){document.getElementById('toolOut').textContent='Running...';document.getElementById('toolOut').textContent=JSON.stringify(await api(path,{method:'POST'}),null,2)}
async function rollback(){let c=document.getElementById('rollbackCommit').value.trim();document.getElementById('toolOut').textContent=JSON.stringify(await api('/api/rollback?commit='+encodeURIComponent(c),{method:'POST'}),null,2)}
draw();setInterval(draw,5000);
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None: return
    def send_json(self, payload: object, code: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode(); self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def ctl(self, args: list[str], timeout: int = 120) -> dict:
        code, out = run_cmd(["/usr/local/bin/netwatchdogctl"] + args, timeout)
        try: payload = json.loads(out) if out else {}
        except json.JSONDecodeError: payload = {"output": out}
        payload.setdefault("ok", code == 0); return payload
    def do_GET(self) -> None:
        p = urlparse(self.path).path
        if p == "/api/status": self.send_json(read_json(STATUS_PATH, {"version": VERSION, "health": {"score": 0, "status": "CRITICAL", "reasons": ["Status not ready"]}})); return
        if p == "/api/history": self.send_json(read_json(HISTORY_PATH, [])); return
        if p == "/api/events": self.send_json(read_events(50)); return
        if p == "/api/update-info": self.send_json(self.ctl(["update", "info"], 90)); return
        if p in {"/", "/advanced", "/history", "/service", "/tools"}:
            data = HTML.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_json({"error": "not found"}, 404)
    def do_POST(self) -> None:
        parsed = urlparse(self.path); q = parse_qs(parsed.query)
        if parsed.path == "/api/restart":
            service = q.get("service", [""])[0]; allowed = set(load_config()["watchdog"].get("control_services", []))
            if service not in allowed or service.startswith("smart-condo-dashboard"): self.send_json({"ok": False, "error": "service not allowed"}, 403); return
            code, out = run_cmd(["systemctl", "restart", service], 20); self.send_json({"ok": code == 0, "service": service, "output": out}); return
        if parsed.path == "/api/selftest": self.send_json(self.ctl(["selftest"], 60)); return
        if parsed.path == "/api/backup": self.send_json(self.ctl(["backup"], 60)); return
        if parsed.path == "/api/update-pull": self.send_json(self.ctl(["update", "pull"], 180)); return
        if parsed.path == "/api/rollback": self.send_json(self.ctl(["rollback", q.get("commit", [""])[0]], 90)); return
        self.send_json({"error": "not found"}, 404)

def main() -> None:
    cfg = load_config()["dashboard"]; ThreadingHTTPServer((str(cfg["host"]), int(cfg["port"])), Handler).serve_forever()
if __name__ == "__main__": main()
