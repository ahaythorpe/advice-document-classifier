#!/usr/bin/env python3
"""Build the static demonstration site.

    python3 build_web.py && vercel deploy web --prod

Runs the pipeline over the synthetic samples once per filing profile and writes
the results as JSON beside a single HTML page. The output is entirely static:
no server, no API, no upload control.

That is the point. A hosted version of the real tool would mean uploading client
files to somebody else's computer, which is a data-residency decision for the
licensee rather than a deployment choice (docs/DEPLOYMENT.md). So the public
version is a demonstration on fabricated documents with nowhere to put a real
one — not a disabled upload button, no upload button.
"""

from __future__ import annotations

import json
import os
import shutil

from advicefiler import extract, integrate, pipeline
from advicefiler.kb import KnowledgeBase
from advicefiler.profiles import FilingProfile, available

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "web")

PAGE = r"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Advice Document Filing — demonstration</title>
<meta name="description" content="Classifies and files Australian financial-advice documents into a client and advice-event tree, flagging anything it cannot confidently place.">
<style>
:root{--bg:#fbfbfa;--fg:#1c1c1a;--mute:#6b6b64;--line:#e4e4df;--card:#fff;
--ok:#2f6f4f;--warn:#8a5a12;--bad:#a02c2c;--accent:#2b4c7e;--chip:#f1f1ee;
--band:#fff8e6;--bandline:#e8d9ae}
@media(prefers-color-scheme:dark){:root{--bg:#151519;--fg:#e9e9e5;--mute:#9b9b95;
--line:#2d2d33;--card:#1d1d22;--ok:#7fc79b;--warn:#e0b062;--bad:#e88b8b;
--accent:#8fb2e8;--chip:#26262c;--band:#2a2317;--bandline:#4a3c1e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,sans-serif}
.band{background:var(--band);border-bottom:1px solid var(--bandline);
padding:9px 24px;font-size:13px;text-align:center}
header{padding:30px 24px 8px;max-width:1080px;margin:0 auto}
h1{font-size:26px;margin:0 0 8px;font-weight:600;letter-spacing:-.02em}
.lede{color:var(--mute);max-width:64ch;margin:0 0 18px}
main{padding:0 24px 60px;max-width:1080px;margin:0 auto}
.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:22px 0 6px;
padding:14px 16px;border:1px solid var(--line);border-radius:11px;background:var(--card)}
label{font-size:13px;color:var(--mute)}
select{font:inherit;padding:6px 10px;border-radius:7px;border:1px solid var(--line);
background:var(--bg);color:var(--fg)}
.pdesc{font-size:13px;color:var(--mute);flex-basis:100%;margin:0}
.stats{display:flex;gap:26px;flex-wrap:wrap;margin:22px 0}
.stat b{display:block;font-size:26px;font-weight:600;letter-spacing:-.02em}
.stat span{color:var(--mute);font-size:11.5px;text-transform:uppercase;letter-spacing:.06em}
h2{font-size:15px;margin:32px 0 10px;font-weight:600;letter-spacing:-.01em}
h2 small{color:var(--mute);font-weight:400;letter-spacing:0}
.event{border:1px solid var(--line);border-radius:11px;background:var(--card);
margin:12px 0;overflow:hidden}
.event>h3{margin:0;padding:13px 16px;font-size:14px;font-weight:600;
border-bottom:1px solid var(--line)}
.event>h3 small{color:var(--mute);font-weight:400;margin-left:8px}
.doc{padding:12px 16px;border-bottom:1px solid var(--line)}
.doc:last-child{border-bottom:0}
.doc.rev{background:color-mix(in srgb,var(--bad) 6%,transparent)}
.name{font-weight:550}
.meta{margin-top:4px}
.chip{display:inline-block;padding:1.5px 9px;border-radius:20px;background:var(--chip);
font-size:11.5px;color:var(--mute);margin:0 5px 3px 0}
.why{font-size:13px;margin-top:5px;color:var(--mute)}
.flag{font-size:12.5px;margin-top:7px;padding:7px 10px;border-radius:7px;
border-left:3px solid var(--warn);background:color-mix(in srgb,var(--warn) 9%,transparent)}
.flag.high{border-color:var(--bad);background:color-mix(in srgb,var(--bad) 9%,transparent)}
.flag b{font-weight:600}
.dest{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;
color:var(--accent);margin-top:6px;word-break:break-all}
pre.tree{border:1px solid var(--line);border-radius:11px;background:var(--card);
padding:16px;overflow-x:auto;font:12.5px/1.7 ui-monospace,SFMono-Regular,Menlo,monospace}
footer{border-top:1px solid var(--line);margin-top:44px;padding-top:20px;
color:var(--mute);font-size:13px}
a{color:var(--accent)}
</style>
<div class="band"><b>Demonstration.</b> Every document below is fabricated.
The real tool runs locally on an adviser's machine and never uploads anything —
this page has no upload control because there is nowhere for a client file to go.</div>
<header>
  <h1>Advice Document Filing</h1>
  <p class="lede">Someone at an Australian advice firm drops a messy client folder in.
  For each document the tool decides what it is, which client and which
  <em>advice event</em> it belongs to, and proposes where to file it — or refuses,
  and says why. It never files silently.</p>
</header>
<main>
  <div class="controls">
    <label for="profile">Filing scheme</label>
    <select id="profile"></select>
    <p class="pdesc" id="pdesc"></p>
  </div>
  <div class="stats" id="stats"></div>

  <h2>Advice events <small>— one advisory decision and everything behind it</small></h2>
  <div id="events"></div>

  <h2>Proposed folder tree <small>— a proposal a human approves, edits or rejects</small></h2>
  <pre class="tree" id="tree"></pre>

  <footer>
    Knowledge base v<span id="kbv"></span> · Australia, Corporations Act 2001, ASIC ·
    <a href="https://github.com/ahaythorpe/advice-document-classifier">source on GitHub</a><br>
    Not legal advice. Switching the filing scheme changes the folders and nothing
    else — the classification, the advice events and the flags are identical,
    which is what lets the tool fit a firm's existing system instead of replacing it.
  </footer>
</main>
<script>
const DATA = __DATA__;
const $=s=>document.querySelector(s);
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const names=Object.keys(DATA);

$('#profile').innerHTML=names.map(n=>`<option value="${n}">${esc(DATA[n].profile_name)}</option>`).join('');
$('#profile').onchange=e=>render(e.target.value);

function stat(n,l){return `<div class="stat"><b>${n}</b><span>${l}</span></div>`}

function docCard(x){
  const d=x.destination||{};
  return `<div class="doc ${x.needs_review?'rev':''}">
    <div class="name">${esc(x.source_name)}</div>
    <div class="meta"><span class="chip">${esc(x.type_label)}</span>
      <span class="chip">confidence ${x.confidence.toFixed(2)}</span>
      ${x.client?`<span class="chip">${esc(x.client)}</span>`:''}
      ${x.date?`<span class="chip">${esc(x.date)}</span>`:''}
      ${x.needs_review?`<span class="chip" style="color:var(--bad)">needs review</span>`:''}</div>
    ${x.attachment_reason?`<div class="why">${esc(x.attachment_reason)}</div>`:''}
    ${x.flags.map(f=>`<div class="flag ${esc(f.severity)}"><b>${esc(f.id)}</b> · ${f.blocks_filing?'blocks filing':'files anyway'}<br>${esc(f.message)}</div>`).join('')}
    ${d.path?`<div class="dest">${esc(d.path)}</div>`:''}
  </div>`;
}

function render(name){
  const d=DATA[name];
  $('#pdesc').textContent=d.profile_description;
  $('#kbv').textContent=d.knowledge_base_version;
  const high=d.documents.reduce((n,x)=>n+x.flags.filter(f=>f.severity==='high').length,0);
  $('#stats').innerHTML=stat(d.batch.documents,'documents')+stat(d.events.length,'advice events')
    +stat(d.batch.auto_filed,'placed')+stat(d.batch.needs_review,'need review')+stat(high,'high flags');

  const byEvent={},loose=[];
  d.documents.forEach(x=>x.event_id?(byEvent[x.event_id]=byEvent[x.event_id]||[]).push(x):loose.push(x));
  let html='';
  d.events.forEach(ev=>{
    html+=`<div class="event"><h3>${esc(ev.client)} — ${esc(ev.subject)}
      <small>${esc(ev.date||'undated')} · ${esc(ev.record_label)}${ev.sub_kind?' · '+esc(ev.sub_kind):''}</small></h3>`;
    (byEvent[ev.event_id]||[]).forEach(x=>html+=docCard(x)); html+='</div>';
  });
  if(loose.length){
    html+=`<div class="event"><h3>Not part of an advice event
      <small>licensee material, client-level documents, and anything that could not be placed</small></h3>`;
    loose.forEach(x=>html+=docCard(x)); html+='</div>';
  }
  $('#events').innerHTML=html;

  const tree={};
  d.documents.forEach(x=>{const p=(x.destination||{}).folder||[];(tree[p.join('/')]=tree[p.join('/')]||[]).push(x)});
  let out='';
  Object.keys(tree).sort().forEach(k=>{
    out+=k+'/\n';
    tree[k].sort((a,b)=>((a.destination||{}).filename||'').localeCompare((b.destination||{}).filename||''))
      .forEach(x=>{out+='    '+((x.destination||{}).filename||'')+'\n'});
  });
  $('#tree').textContent=out;
}
render(names[0]);
</script>
</html>
"""


def build() -> None:
    kb = KnowledgeBase.load()
    with open(os.path.join(HERE, "sample_documents.json")) as fh:
        records = json.load(fh)["documents"]

    payload = {}
    for name in available():
        profile = FilingProfile.load(name)
        documents = extract.from_sample_records(records)
        result = pipeline.run(kb, documents, profile=profile)
        data = integrate.manifest(result)
        # Nothing about the machine that built this belongs in a public page.
        for doc in data["documents"]:
            doc.pop("source_path", None)
        data["batch"].pop("unreadable", None)
        data["generated"] = None
        data["profile_name"] = profile.name
        data["profile_description"] = profile.description
        payload[name] = data

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    with open(os.path.join(OUT, "index.html"), "w") as fh:
        fh.write(PAGE.replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
    with open(os.path.join(OUT, "vercel.json"), "w") as fh:
        json.dump({
            "$schema": "https://openapi.vercel.sh/vercel.json",
            "headers": [{
                "source": "/(.*)",
                "headers": [
                    {"key": "X-Content-Type-Options", "value": "nosniff"},
                    {"key": "X-Frame-Options", "value": "DENY"},
                    {"key": "Referrer-Policy", "value": "no-referrer"},
                    {"key": "Content-Security-Policy",
                     "value": "default-src 'none'; style-src 'unsafe-inline'; "
                              "script-src 'unsafe-inline'; base-uri 'none'; "
                              "form-action 'none'; frame-ancestors 'none'"},
                ],
            }],
        }, fh, indent=2)

    size = os.path.getsize(os.path.join(OUT, "index.html"))
    print("web/index.html  %.1f KB, %d filing profiles, no server, no upload"
          % (size / 1024.0, len(payload)))


if __name__ == "__main__":
    build()
