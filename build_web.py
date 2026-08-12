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
from advicefiler.webassets import CSS, RENDER_JS, THEME_HEAD, THEME_JS

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "web")

PAGE = r"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Advice Document Filing — demonstration</title>
<meta name="description" content="Classifies and files Australian financial-advice documents into a client and advice-event tree, flagging anything it cannot confidently place.">
__THEME_HEAD__
<style>__CSS__
.pick{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:26px 0 0}
.pick label{font-size:13px;color:var(--mute)}
.pick p{flex-basis:100%;margin:0;font-size:12.5px;color:var(--faint);max-width:62ch}
</style>
<div class="notice"><div class="wrap">
  <b>Demonstration.</b><span>Every document below is fabricated. The real tool runs
  on an adviser&rsquo;s own machine and uploads nothing — this page has no upload
  control because there is nowhere for a client file to go.</span>
</div></div>
<div class="top"><div class="wrap">
  <p class="brand">Advice Document Filing</p>
  <span class="grow"></span>
  <a class="ghost" style="text-decoration:none"
     href="https://github.com/ahaythorpe/advice-document-classifier">Source</a>
  <button class="ghost" id="theme" onclick="cycleTheme()">Auto</button>
</div></div>

<div class="wrap">
  <div class="intro">
    <h1>A messy client folder in, a proposed filing out</h1>
    <p>For each document the tool decides what it is, which client and which
    <em>advice event</em> it belongs to, and proposes where to file it — or
    refuses, and says why. It never files silently.</p>
  </div>

  <div class="pick">
    <label for="profile">Filing scheme</label>
    <select id="profile"></select>
    <p id="pdesc"></p>
  </div>

  <div class="summary" id="summary"></div>

  <div class="sec"><h2>Advice events</h2><div id="events"></div></div>
  <div class="sec"><h2>Proposed folder tree</h2><pre class="tree" id="tree"></pre></div>

  <footer>
    Knowledge base v<span id="kbv"></span> · Australia, Corporations Act 2001, ASIC.
    Not legal advice.<br>
    Changing the filing scheme changes the folders and nothing else — the
    classification, the advice events and the findings are identical. That is what
    lets the tool fit a firm&rsquo;s existing system instead of replacing it.
  </footer>
</div>

<script>
__THEME_JS__
__RENDER_JS__
const DATA = __DATA__;
const $=s=>document.querySelector(s);
const names=Object.keys(DATA);
paintThemeButton();

$('#profile').innerHTML=names.map(n=>
  `<option value="${n}">${esc(DATA[n].profile_name)}</option>`).join('');
$('#profile').onchange=e=>render(e.target.value);

function render(name){
  const d=DATA[name];
  $('#pdesc').textContent=d.profile_description;
  $('#kbv').textContent=d.knowledge_base_version;
  $('#summary').innerHTML=summaryHtml(d);
  $('#events').innerHTML=groupsHtml(d,false);
  $('#tree').innerHTML=treeText(d);
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
        page = (PAGE.replace("__THEME_HEAD__", THEME_HEAD)
                    .replace("__CSS__", CSS)
                    .replace("__THEME_JS__", THEME_JS)
                    .replace("__RENDER_JS__", RENDER_JS)
                    .replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
        fh.write(page)
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
