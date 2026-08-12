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
from .webassets import CSS, RENDER_JS, THEME_HEAD, THEME_JS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAGE = r"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Advice Document Filing</title>
__THEME_HEAD__
<style>__CSS__
/* app-specific ------------------------------------------------------------ */
.setup{border:1px solid var(--line);border-radius:10px;background:var(--panel);
  padding:16px;margin:22px 0 4px;box-shadow:var(--shadow)}
.setup h2{font-size:12px;font-weight:600;color:var(--faint);margin:0 0 12px;
  text-transform:uppercase;letter-spacing:.08em}
.field{display:grid;grid-template-columns:120px 1fr;gap:12px;align-items:center;
  margin-bottom:9px}
.field label{font-size:13px;color:var(--mute)}
.field input,.field select{width:100%}
.field .sub{grid-column:2;font-size:12px;color:var(--faint);margin-top:-3px}
.go{font:inherit;font-size:13.5px;font-weight:500;padding:8px 18px;border-radius:7px;
  border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer}
.go:disabled{opacity:.5;cursor:not-allowed}
.setup .actions{display:flex;gap:10px;align-items:center;margin-top:14px}
.empty{text-align:center;color:var(--faint);padding:60px 20px;font-size:14px}
.groupacts{margin-left:auto;display:flex;gap:6px}
.groupacts button{font:inherit;font-size:12px;padding:3px 10px;border-radius:6px;
  border:1px solid var(--line);background:transparent;color:var(--mute);cursor:pointer}
.groupacts button:hover{color:var(--fg);border-color:var(--faint)}
.bar{position:sticky;bottom:0;background:var(--panel);border-top:1px solid var(--line);
  padding:12px 0;margin-top:26px}
.bar .wrap{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.count{font-size:13px;color:var(--mute)}
.count b{color:var(--fg);font-weight:600}
</style>
<div class="top"><div class="wrap">
  <p class="brand">Advice Document Filing</p>
  <span class="hint" id="ctx">local · nothing leaves this machine</span>
  <span class="grow"></span>
  <button class="ghost" id="theme" onclick="cycleTheme()">Auto</button>
</div></div>

<div class="wrap">
  <div class="setup" id="setup">
    <h2>Documents</h2>
    <div class="field"><label for="input">Folder</label>
      <input id="input" placeholder="/Users/you/Documents/smith-family" spellcheck="false"></div>
    <div class="field"><span></span><span class="sub" id="inputhint">
      Leave empty to use the ten built-in sample documents.</span></div>
    <div class="field"><label for="profile">Filing scheme</label>
      <select id="profile"></select></div>
    <div class="field"><span></span><span class="sub" id="pdesc"></span></div>
    <div class="actions">
      <button class="go" id="run">Read documents</button>
      <span class="hint">Nothing is written until you choose to file.</span>
    </div>
  </div>

  <div id="msg"></div>
  <div class="summary" id="summary" style="display:none"></div>
  <div id="body"><div class="empty" id="empty">
    Choose a folder and read it, or press <b>Read documents</b> for the samples.
  </div></div>
</div>

<div class="bar" id="bar" style="display:none"><div class="wrap">
  <span class="count"><b id="napprove">0</b> approved · <b id="nreject">0</b> rejected
    · <b id="npending">0</b> undecided</span>
  <span class="grow"></span>
  <input id="dest" placeholder="destination folder" spellcheck="false">
  <button class="ghost" id="dry">Dry run</button>
  <button class="go" id="commit">File them</button>
</div></div>

<script>
__THEME_JS__
__RENDER_JS__

let DATA=null, DEC={};
const $=s=>document.querySelector(s);
paintThemeButton();

async function api(path,body){
  const r=await fetch(path,{method:body?'POST':'GET',
    headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):null});
  const j=await r.json();
  if(!r.ok) throw new Error(j.error||'request failed');
  return j;
}
function say(t,bad){ $('#msg').innerHTML = t?`<div class="msg ${bad?'err':''}">${esc(t)}</div>`:''; }

let PROFILES={};
api('/api/config').then(c=>{
  PROFILES=c.descriptions||{};
  $('#profile').innerHTML=c.profiles.map(p=>
    `<option value="${p}" ${p===c.profile?'selected':''}>${esc(p)}</option>`).join('');
  $('#input').value=c.input||''; $('#dest').value=c.dest||'';
  describe();
  if(c.demo) run();
});
function describe(){ $('#pdesc').textContent=PROFILES[$('#profile').value]||''; }
$('#profile').onchange=()=>{ describe(); if(DATA) run(); };

async function run(){
  say(''); $('#run').disabled=true; $('#run').textContent='Reading…';
  try{
    DATA=await api('/api/run',{input:$('#input').value,profile:$('#profile').value});
    DEC={}; DATA.documents.forEach(d=>DEC[d.doc_id]=d.needs_review?'reject':'pending');
    render();
  }catch(e){
    say(e.message,true); DATA=null; $('#body').innerHTML=''; 
    $('#summary').style.display='none'; $('#bar').style.display='none';
  }
  $('#run').disabled=false; $('#run').textContent='Read documents';
}
$('#run').onclick=run;

function render(){
  const d=DATA;
  $('#ctx').textContent=`${d.filing_profile} · knowledge base v${d.knowledge_base_version}`;
  $('#summary').innerHTML=summaryHtml(d); $('#summary').style.display='flex';
  $('#body').innerHTML=groupsHtml(d,true);
  // Judging a whole advice event at once is the unit that makes sense: is this
  // the March super advice and everything behind it, yes or no.
  document.querySelectorAll('.group').forEach(g=>{
    const ids=[...g.querySelectorAll('.row')].map(r=>r.id.slice(4));
    const bar=document.createElement('span'); bar.className='groupacts';
    bar.innerHTML=`<button>Approve all</button>`;
    bar.firstChild.onclick=()=>{ids.forEach(i=>{
      const doc=DATA.documents.find(x=>x.doc_id===i);
      if(doc && !doc.needs_review) DEC[i]='approve';}); paint();};
    g.querySelector('header').appendChild(bar);
  });
  $('#bar').style.display='block'; paint();
}

function decide(id,v){ DEC[id]=DEC[id]===v?'pending':v; paint(); }
function paint(){
  let a=0,r=0,p=0;
  DATA.documents.forEach(x=>{
    const v=DEC[x.doc_id]; v==='approve'?a++:v==='reject'?r++:p++;
    const y=document.getElementById('y-'+x.doc_id), n=document.getElementById('n-'+x.doc_id);
    if(y){ y.className=v==='approve'?'yes':''; n.className=v==='reject'?'no':''; }
  });
  $('#napprove').textContent=a; $('#nreject').textContent=r; $('#npending').textContent=p;
  $('#dry').disabled=$('#commit').disabled=(a===0);
  $('#commit').textContent=a?`File ${a}`:'File them';
}

async function apply(commit){
  say(commit?'Filing…':'Rehearsing…');
  try{
    const res=await api('/api/apply',{input:$('#input').value,profile:$('#profile').value,
      dest:$('#dest').value,commit:commit,decisions:DEC});
    say(res.summary+(res.detail.length?'\n\n'+res.detail.join('\n'):''));
  }catch(e){ say(e.message,true); }
  window.scrollTo({top:0,behavior:'smooth'});
}
$('#dry').onclick=()=>apply(false);
$('#commit').onclick=()=>{
  if(confirm('Copy the approved documents into the destination folder?')) apply(true); };
</script>
</html>
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
                page = (PAGE.replace("__THEME_HEAD__", THEME_HEAD)
                            .replace("__CSS__", CSS)
                            .replace("__THEME_JS__", THEME_JS)
                            .replace("__RENDER_JS__", RENDER_JS))
                return self._send(200, page, "text/html")
            if self.path == "/api/config":
                descriptions = {}
                for name in available():
                    descriptions[name] = FilingProfile.load(name).description
                return self._send(200, json.dumps({
                    "profiles": available(), "profile": "nested-default",
                    "descriptions": descriptions,
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
