"""A local review UI — build step 5, in its first usable form.

    python3 -m advicefiler.ui --demo          # synthetic samples, click around
    python3 -m advicefiler.ui --input input/smith

Runs on 127.0.0.1 only. Documents are read from the local disk and stay there;
nothing is uploaded anywhere, because the whole posture of this tool is that
client files do not leave the building.

That is also why this is a *local* server rather than a hosted app. A hosted
version would mean uploading client PII to somebody else's computer, which is a
data-residency decision for the licensee (SYSTEM.md section 10), not a
deployment choice. See docs/DEPLOYMENT.md.

Standard library only, so it runs anywhere Python does.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from typing import Any, Dict, List, Optional

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:  # pragma: no cover
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer  # type: ignore

from . import extract, integrate, pipeline
from .classify import KeywordClassifier
from .clients import ClientRegister
from .kb import KnowledgeBase
from .profiles import FilingProfile, available

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAGE = r"""<!doctype html>
<meta charset="utf-8">
<title>Advice Document Filing</title>
<style>
:root{--bg:#fbfbfa;--fg:#1c1c1a;--mute:#6b6b64;--line:#e2e2dd;--card:#fff;
--ok:#2f6f4f;--warn:#8a5a12;--bad:#a02c2c;--accent:#2b4c7e;--chip:#f1f1ee}
@media(prefers-color-scheme:dark){:root{--bg:#16161a;--fg:#e8e8e4;--mute:#9a9a94;
--line:#2e2e34;--card:#1e1e23;--ok:#7fc79b;--warn:#e0b062;--bad:#e88b8b;
--accent:#8fb2e8;--chip:#26262c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{padding:18px 26px;border-bottom:1px solid var(--line);display:flex;
gap:18px;align-items:center;flex-wrap:wrap;position:sticky;top:0;background:var(--bg);z-index:5}
h1{font-size:17px;margin:0;font-weight:600;letter-spacing:-.01em}
.sub{color:var(--mute);font-size:13px}
main{padding:22px 26px;max-width:1180px}
button{font:inherit;padding:7px 14px;border-radius:7px;border:1px solid var(--line);
background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--accent)}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
button.danger{border-color:var(--bad);color:var(--bad)}
button:disabled{opacity:.45;cursor:not-allowed}
input,select{font:inherit;padding:6px 9px;border-radius:7px;border:1px solid var(--line);
background:var(--card);color:var(--fg);min-width:220px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.stats{display:flex;gap:24px;flex-wrap:wrap;margin:18px 0 8px}
.stat b{display:block;font-size:24px;font-weight:600;letter-spacing:-.02em}
.stat span{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.event{border:1px solid var(--line);border-radius:11px;background:var(--card);
margin:14px 0;overflow:hidden}
.event>h3{margin:0;padding:13px 16px;font-size:14px;font-weight:600;
border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:baseline}
.event>h3 small{color:var(--mute);font-weight:400}
.doc{padding:12px 16px;border-bottom:1px solid var(--line);display:grid;
grid-template-columns:1fr auto;gap:12px;align-items:start}
.doc:last-child{border-bottom:0}
.doc.rev{background:color-mix(in srgb,var(--bad) 6%,transparent)}
.name{font-weight:550}
.meta{color:var(--mute);font-size:13px;margin-top:3px}
.why{font-size:13px;margin-top:5px;color:var(--mute)}
.chip{display:inline-block;padding:1px 8px;border-radius:20px;background:var(--chip);
font-size:11.5px;color:var(--mute);margin-right:5px;letter-spacing:.02em}
.flag{font-size:12.5px;margin-top:6px;padding:6px 9px;border-radius:7px;
border-left:3px solid var(--warn);background:color-mix(in srgb,var(--warn) 8%,transparent)}
.flag.high{border-color:var(--bad);background:color-mix(in srgb,var(--bad) 8%,transparent)}
.flag b{font-weight:600}
.dest{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;
color:var(--accent);margin-top:5px;word-break:break-all}
.acts{display:flex;flex-direction:column;gap:5px;min-width:112px}
.acts button{padding:5px 10px;font-size:13px}
.on-approve{background:var(--ok);color:#fff;border-color:var(--ok)}
.on-reject{background:var(--bad);color:#fff;border-color:var(--bad)}
.bar{position:sticky;bottom:0;background:var(--card);border-top:1px solid var(--line);
padding:13px 26px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.msg{padding:11px 14px;border-radius:8px;margin:12px 0;font-size:13.5px;
border:1px solid var(--line);background:var(--card);white-space:pre-wrap}
.msg.err{border-color:var(--bad);color:var(--bad)}
.hint{color:var(--mute);font-size:12.5px}
code{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;background:var(--chip);
padding:1px 5px;border-radius:4px}
</style>
<header>
  <h1>Advice Document Filing</h1>
  <span class="sub" id="ctx">local · nothing leaves this machine</span>
  <span style="flex:1"></span>
  <div class="row">
    <input id="input" placeholder="folder of documents" size="34">
    <select id="profile"></select>
    <button class="primary" id="run">Read documents</button>
  </div>
</header>
<main>
  <div id="msg"></div>
  <div class="stats" id="stats"></div>
  <div id="body"></div>
</main>
<div class="bar" id="bar" style="display:none">
  <button id="approveAll">Approve everything filable</button>
  <span class="hint">reviewed items stay rejected</span>
  <span style="flex:1"></span>
  <input id="dest" placeholder="destination folder" size="30">
  <button id="dry">Dry run</button>
  <button class="danger" id="commit">File them</button>
</div>
<script>
let DATA=null, DEC={};
const $=s=>document.querySelector(s);
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function api(path,body){
  const r=await fetch(path,{method:body?'POST':'GET',
    headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):null});
  const j=await r.json();
  if(!r.ok) throw new Error(j.error||'request failed');
  return j;
}
function say(t,bad){ $('#msg').innerHTML = t? `<div class="msg ${bad?'err':''}">${esc(t)}</div>`:''; }

api('/api/config').then(c=>{
  $('#profile').innerHTML=c.profiles.map(p=>`<option value="${p}" ${p==c.profile?'selected':''}>${p}</option>`).join('');
  $('#input').value=c.input||''; $('#dest').value=c.dest||'';
  if(c.demo){ say('Demo mode: ten synthetic documents, including a deliberately illegible scan and an authority to proceed with no advice record behind it. Nothing here is a real client.'); run(); }
});

async function run(){
  say('reading…'); $('#run').disabled=true;
  try{
    DATA=await api('/api/run',{input:$('#input').value,profile:$('#profile').value});
    DEC={}; DATA.documents.forEach(d=>DEC[d.doc_id]=d.needs_review?'reject':'pending');
    render(); say('');
  }catch(e){ say(e.message,true); DATA=null; $('#body').innerHTML=''; $('#stats').innerHTML=''; }
  $('#run').disabled=false;
}
$('#run').onclick=run;

function stat(n,l){ return `<div class="stat"><b>${n}</b><span>${l}</span></div>`; }

function render(){
  const d=DATA, b=d.batch;
  $('#ctx').textContent=`${d.filing_profile} · knowledge base v${d.knowledge_base_version} · nothing leaves this machine`;
  $('#stats').innerHTML=stat(b.documents,'documents')+stat(d.events.length,'advice events')
    +stat(b.auto_filed,'placed')+stat(b.needs_review,'need review')
    +stat(d.documents.reduce((n,x)=>n+x.flags.filter(f=>f.severity=='high').length,0),'high flags');

  const byEvent={}; const loose=[];
  d.documents.forEach(x=> x.event_id ? (byEvent[x.event_id]=byEvent[x.event_id]||[]).push(x) : loose.push(x));

  let html='';
  d.events.forEach(ev=>{
    html+=`<div class="event"><h3>${esc(ev.client)} — ${esc(ev.subject)}
      <small>${esc(ev.date||'undated')} · ${esc(ev.record_label)}${ev.sub_kind?' · '+esc(ev.sub_kind):''}</small></h3>`;
    (byEvent[ev.event_id]||[]).forEach(x=>html+=doc(x));
    html+=`</div>`;
  });
  if(loose.length){
    html+=`<div class="event"><h3>Not part of an advice event <small>licensee material, client-level documents, and anything that could not be placed</small></h3>`;
    loose.forEach(x=>html+=doc(x)); html+=`</div>`;
  }
  $('#body').innerHTML=html; $('#bar').style.display='flex'; paint();
}

function doc(x){
  const dest=x.destination||{};
  return `<div class="doc ${x.needs_review?'rev':''}" id="d-${x.doc_id}">
    <div>
      <div class="name">${esc(x.source_name)}</div>
      <div class="meta"><span class="chip">${esc(x.type_label)}</span>
        <span class="chip">confidence ${x.confidence.toFixed(2)}</span>
        ${x.client?`<span class="chip">${esc(x.client)}</span>`:''}
        ${x.date?`<span class="chip">${esc(x.date)}</span>`:''}</div>
      ${x.attachment_reason?`<div class="why">${esc(x.attachment_reason)}</div>`:''}
      ${x.flags.map(f=>`<div class="flag ${f.severity}"><b>${esc(f.id)}</b>${f.blocks_filing?' · blocks filing':' · files anyway'}<br>${esc(f.message)}</div>`).join('')}
      ${dest.path?`<div class="dest">${esc(dest.path)}</div>`:''}
    </div>
    <div class="acts">
      <button onclick="setDec('${x.doc_id}','approve')" id="a-${x.doc_id}">Approve</button>
      <button onclick="setDec('${x.doc_id}','reject')" id="r-${x.doc_id}">Reject</button>
    </div></div>`;
}

function setDec(id,v){ DEC[id]=DEC[id]===v?'pending':v; paint(); }
function paint(){
  DATA.documents.forEach(x=>{
    const v=DEC[x.doc_id];
    const a=document.getElementById('a-'+x.doc_id), r=document.getElementById('r-'+x.doc_id);
    if(!a) return;
    a.className=v==='approve'?'on-approve':''; r.className=v==='reject'?'on-reject':'';
  });
  const n=Object.values(DEC).filter(v=>v==='approve').length;
  $('#dry').textContent=`Dry run (${n})`; $('#commit').textContent=`File them (${n})`;
  $('#commit').disabled=$('#dry').disabled=(n===0);
}
$('#approveAll').onclick=()=>{ DATA.documents.forEach(x=>{ if(!x.needs_review) DEC[x.doc_id]='approve'; }); paint(); };

async function apply(commit){
  say(commit?'filing…':'rehearsing…');
  try{
    const r=await api('/api/apply',{input:$('#input').value,profile:$('#profile').value,
      dest:$('#dest').value,commit:commit,decisions:DEC});
    say(r.summary+'\n\n'+r.detail.join('\n'));
  }catch(e){ say(e.message,true); }
}
$('#dry').onclick=()=>apply(false);
$('#commit').onclick=()=>{ if(confirm('Copy the approved documents into the destination folder?')) apply(true); };
</script>
"""


class State(object):
    def __init__(self, kb, demo, input_dir, dest, clients_path):
        self.kb = kb
        self.demo = demo
        self.input_dir = input_dir
        self.dest = dest
        self.clients_path = clients_path


def _load(state: State, input_dir: str, profile_name: str):
    profile = FilingProfile.load(profile_name)
    if state.demo and not input_dir:
        with open(os.path.join(ROOT, "sample_documents.json")) as fh:
            documents = extract.from_sample_records(json.load(fh)["documents"])
        failures = []
    else:
        if not input_dir:
            raise ValueError("choose a folder of documents to read")
        if not os.path.isdir(input_dir):
            raise ValueError("not a folder: %s" % input_dir)
        documents, failures = extract.extract_directory(input_dir)
        if not documents:
            raise ValueError("no readable documents in %s (supported: %s)"
                             % (input_dir, ", ".join(extract.SUPPORTED_SUFFIXES)))
    register = None
    if state.clients_path:
        register = ClientRegister.load(state.clients_path, state.kb)
    return pipeline.run(state.kb, documents,
                        classifier=KeywordClassifier(state.kb),
                        extraction_failures=failures, profile=profile,
                        register=register)


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):      # keep the console for real output
            pass

        def _send(self, code, body, content_type="application/json"):
            raw = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            # A local-only tool still should not be reachable from a web page.
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self._send(200, PAGE, "text/html")
            if self.path == "/api/config":
                return self._send(200, json.dumps({
                    "profiles": available(), "profile": "nested-default",
                    "input": state.input_dir or "", "dest": state.dest or "",
                    "demo": state.demo}))
            return self._send(404, json.dumps({"error": "not found"}))

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")

        def do_POST(self):
            try:
                payload = self._body()
                if self.path == "/api/run":
                    result = _load(state, payload.get("input", ""),
                                   payload.get("profile") or "nested-default")
                    return self._send(200, json.dumps(integrate.manifest(result)))
                if self.path == "/api/apply":
                    return self._send(200, json.dumps(self._apply(payload)))
                return self._send(404, json.dumps({"error": "not found"}))
            except Exception as exc:       # surfaced in the page, not swallowed
                return self._send(400, json.dumps({"error": str(exc)}))

        def _apply(self, payload):
            dest = (payload.get("dest") or "").strip()
            if not dest:
                raise ValueError("choose a destination folder first")
            result = _load(state, payload.get("input", ""),
                           payload.get("profile") or "nested-default")
            decisions = payload.get("decisions") or {}
            approvals = {k: {"decision": v} for k, v in decisions.items()}

            issues = integrate.preflight(result, dest)
            errors = [i for i in issues if i.level == "error"]
            if errors:
                raise ValueError("preflight failed:\n" +
                                 "\n".join("  " + i.message for i in errors))

            commit = bool(payload.get("commit"))
            applied = integrate.LocalFolderDestination(dest).apply(
                result.plan, approvals, dry_run=not commit)
            detail = ["%-13s %s" % (i.action, i.destination or i.source)
                      for i in applied.items if i.action in ("filed", "failed")]
            if not commit:
                detail.append("")
                detail.append("Nothing was written. Use 'File them' to copy them across.")
            return {"summary": applied.summary(), "detail": detail}

    return Handler


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Local review UI for advice filing.")
    parser.add_argument("--demo", action="store_true",
                        help="start with the ten synthetic sample documents")
    parser.add_argument("--input", help="folder of documents to read")
    parser.add_argument("--dest", help="pre-fill the destination folder")
    parser.add_argument("--clients", help="the firm's existing client register")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    if not args.demo and not args.input:
        args.demo = True

    state = State(KnowledgeBase.load(), args.demo, args.input, args.dest,
                  args.clients)
    # Otherwise a restart within the TIME_WAIT window fails with "address
    # already in use", which during development is every restart.
    HTTPServer.allow_reuse_address = True
    # 127.0.0.1, never 0.0.0.0: this must not be reachable from the network.
    server = HTTPServer(("127.0.0.1", args.port), make_handler(state))
    url = "http://127.0.0.1:%d/" % args.port
    print("Advice document filing — %s" % url)
    print("Local only. Documents are read from this machine and stay on it.")
    print("Ctrl-C to stop.")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
