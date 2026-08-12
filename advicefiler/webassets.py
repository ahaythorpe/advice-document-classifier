"""Shared styling and rendering for the review UI and the demonstration page.

One design, two consumers, so they cannot drift.

The first version showed everything at once — every chip, every flag in full,
the whole destination path, on every row. Ten documents produced a wall of text
and nothing stood out, which is the opposite of what a review queue is for.

The rewrite is built on one idea: **a reviewer's first pass asks only "which of
these need me?"** So the collapsed row answers exactly that — a status dot, the
name, the type, and how sure the tool is — and everything else waits behind a
click. Detail is available, not imposed.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Theme: system by default, explicitly overridable, remembered.
# ---------------------------------------------------------------------------

THEME_HEAD = """
<script>
(function(){var t=localStorage.getItem('theme');
if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);})();
</script>
"""

THEME_JS = r"""
function themeNow(){
  return document.documentElement.getAttribute('data-theme')
    || (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
}
function paintThemeButton(){
  var b=document.getElementById('theme'); if(!b) return;
  var stored=localStorage.getItem('theme');
  b.textContent = stored==='light'?'Light' : stored==='dark'?'Dark' : 'Auto';
  b.title='Theme: '+(stored||'follows your system')+' — click to change';
}
function cycleTheme(){
  var stored=localStorage.getItem('theme');
  var next = stored==null ? (themeNow()==='dark'?'light':'dark')
           : stored==='dark' ? 'light' : null;
  if(next){ localStorage.setItem('theme',next);
            document.documentElement.setAttribute('data-theme',next); }
  else { localStorage.removeItem('theme');
         document.documentElement.removeAttribute('data-theme'); }
  paintThemeButton();
}
"""

# ---------------------------------------------------------------------------
# One stylesheet. Both palettes defined on :root so neither depends on a media
# query alone, and the explicit override wins in both directions.
# ---------------------------------------------------------------------------

CSS = r"""
:root{
  --bg:#fcfcfb; --panel:#fff; --fg:#191917; --mute:#77776f; --faint:#9a9a92;
  --line:#e9e9e4; --hair:#f2f2ee;
  --accent:#31558c; --ok:#3a7d5a; --warn:#b07d1a; --bad:#b2423c;
  --okbg:#eff6f2; --warnbg:#fcf6e8; --badbg:#fcf0ef;
  --shadow:0 1px 2px rgba(0,0,0,.04);
}
:root[data-theme="dark"]{
  --bg:#141417; --panel:#1b1b1f; --fg:#eaeae6; --mute:#9c9c96; --faint:#75756f;
  --line:#2a2a30; --hair:#232329;
  --accent:#8fb0e6; --ok:#79c19a; --warn:#dcac5e; --bad:#e58e88;
  --okbg:#1a2620; --warnbg:#2a2317; --badbg:#2c1d1c;
  --shadow:none;
}
@media(prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#141417; --panel:#1b1b1f; --fg:#eaeae6; --mute:#9c9c96; --faint:#75756f;
    --line:#2a2a30; --hair:#232329;
    --accent:#8fb0e6; --ok:#79c19a; --warn:#dcac5e; --bad:#e58e88;
    --okbg:#1a2620; --warnbg:#2a2317; --badbg:#2c1d1c;
    --shadow:none;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.55 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:860px;margin:0 auto;padding:0 22px}

/* header ------------------------------------------------------------------ */
.top{border-bottom:1px solid var(--line);background:var(--bg);
  position:sticky;top:0;z-index:10}
.top .wrap{display:flex;align-items:center;gap:14px;height:58px}
.brand{font-size:15px;font-weight:600;letter-spacing:-.01em;margin:0}
.grow{flex:1}
.ghost{font:inherit;font-size:13px;padding:5px 11px;border-radius:7px;
  border:1px solid var(--line);background:transparent;color:var(--mute);cursor:pointer}
.ghost:hover{color:var(--fg);border-color:var(--faint)}

/* intro ------------------------------------------------------------------- */
.intro{padding:34px 0 6px}
.intro h1{font-size:25px;margin:0 0 10px;font-weight:600;letter-spacing:-.022em}
.intro p{color:var(--mute);margin:0;max-width:60ch}
.notice{background:var(--warnbg);border-bottom:1px solid var(--line);
  padding:9px 0;font-size:13px;color:var(--fg)}
.notice .wrap{display:flex;gap:8px;align-items:baseline}

/* summary ----------------------------------------------------------------- */
.summary{display:flex;gap:30px;flex-wrap:wrap;padding:24px 0 6px;
  border-bottom:1px solid var(--hair);margin-bottom:8px}
.summary div b{display:block;font-size:23px;font-weight:600;letter-spacing:-.02em;
  line-height:1.25}
.summary div span{font-size:11px;color:var(--faint);text-transform:uppercase;
  letter-spacing:.07em}

/* section ----------------------------------------------------------------- */
.sec{margin:30px 0 0}
.sec>h2{font-size:12px;font-weight:600;color:var(--faint);margin:0 0 10px;
  text-transform:uppercase;letter-spacing:.08em}
.group{border:1px solid var(--line);border-radius:10px;background:var(--panel);
  margin-bottom:12px;overflow:hidden;box-shadow:var(--shadow)}
.group>header{padding:12px 15px;border-bottom:1px solid var(--hair);
  display:flex;gap:9px;align-items:baseline;flex-wrap:wrap}
.group>header b{font-size:14px;font-weight:600}
.group>header span{font-size:12.5px;color:var(--mute)}

/* row --------------------------------------------------------------------- */
.row{border-bottom:1px solid var(--hair)}
.row:last-child{border-bottom:0}
.head{display:grid;grid-template-columns:9px 1fr auto auto;gap:11px;
  align-items:center;padding:11px 15px;cursor:pointer;user-select:none}
.head:hover{background:var(--hair)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok)}
.dot.warn{background:var(--warn)} .dot.bad{background:var(--bad)}
.title{min-width:0}
.title b{display:block;font-weight:500;font-size:14px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.title span{font-size:12.5px;color:var(--faint)}
.kind{font-size:12px;color:var(--mute);white-space:nowrap}
.conf{width:34px;height:3px;border-radius:2px;background:var(--hair);
  position:relative;overflow:hidden}
.conf i{position:absolute;inset:0 auto 0 0;background:var(--ok);display:block}
.conf.warn i{background:var(--warn)} .conf.bad i{background:var(--bad)}
.chev{color:var(--faint);font-size:11px;transition:transform .12s}
.row.open .chev{transform:rotate(90deg)}

/* detail ------------------------------------------------------------------ */
.detail{display:none;padding:2px 15px 15px 35px}
.row.open .detail{display:block}
.detail dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:4px 14px;
  font-size:13px}
.detail dt{color:var(--faint)}
.detail dd{margin:0}
.path{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;
  color:var(--accent);word-break:break-all}
.note{margin-top:11px;padding:9px 11px;border-radius:7px;font-size:12.5px;
  background:var(--warnbg);border-left:2px solid var(--warn)}
.note.high{background:var(--badbg);border-color:var(--bad)}
.note b{font-weight:600;display:block;margin-bottom:2px}
.note em{font-style:normal;color:var(--mute)}

/* actions ----------------------------------------------------------------- */
.acts{display:flex;gap:7px;margin-top:12px}
.acts button{font:inherit;font-size:12.5px;padding:4px 12px;border-radius:6px;
  border:1px solid var(--line);background:transparent;color:var(--mute);cursor:pointer}
.acts button:hover{color:var(--fg)}
.acts button.yes{border-color:var(--ok);background:var(--ok);color:#fff}
.acts button.no{border-color:var(--bad);background:var(--bad);color:#fff}

/* footer / misc ----------------------------------------------------------- */
pre.tree{border:1px solid var(--line);border-radius:10px;background:var(--panel);
  padding:15px;overflow-x:auto;margin:0;
  font:12px/1.75 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--mute)}
pre.tree b{color:var(--fg);font-weight:500}
footer{border-top:1px solid var(--hair);margin:44px 0 0;padding:20px 0 46px;
  color:var(--faint);font-size:12.5px}
footer a{color:var(--accent)}
select,input{font:inherit;font-size:13.5px;padding:6px 10px;border-radius:7px;
  border:1px solid var(--line);background:var(--panel);color:var(--fg)}
input{min-width:230px}
.msg{padding:11px 13px;border-radius:8px;margin:16px 0;font-size:13px;
  border:1px solid var(--line);background:var(--panel);white-space:pre-wrap}
.msg.err{border-color:var(--bad);color:var(--bad);background:var(--badbg)}
.hint{color:var(--faint);font-size:12.5px}
"""

# ---------------------------------------------------------------------------
# Rendering shared by both pages.
# ---------------------------------------------------------------------------

RENDER_JS = r"""
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// Three states, and only three. A reviewer's first pass is "which need me?",
// so the collapsed row answers that and nothing else.
function statusOf(x){
  if(x.needs_review) return 'bad';
  return x.flags.length ? 'warn' : 'ok';
}
function summarise(x){
  if(x.needs_review) return 'needs review';
  if(x.flags.length) return x.flags.length===1 ? '1 finding'
                                               : x.flags.length+' findings';
  return x.date || '';
}

function rowHtml(x, withActions){
  const s=statusOf(x), d=x.destination||{};
  return `<div class="row" id="row-${x.doc_id}">
    <div class="head" onclick="toggleRow('${x.doc_id}')">
      <span class="dot ${s==='ok'?'':s}"></span>
      <span class="title"><b>${esc(x.source_name)}</b>
        <span>${esc(summarise(x))}</span></span>
      <span class="kind">${esc(x.type_label)}</span>
      <span class="conf ${s==='ok'?'':s}" title="confidence ${x.confidence.toFixed(2)}">
        <i style="width:${Math.round(x.confidence*100)}%"></i></span>
      <span class="chev">&#9656;</span>
    </div>
    <div class="detail">
      <dl>
        ${x.client?`<dt>Client</dt><dd>${esc(x.client)}</dd>`:''}
        ${x.date?`<dt>Dated</dt><dd>${esc(x.date)}</dd>`:''}
        <dt>Confidence</dt><dd>${x.confidence.toFixed(2)}</dd>
        ${x.attachment_reason?`<dt>Grouped</dt><dd>${esc(x.attachment_reason)}</dd>`:''}
        ${d.path?`<dt>Proposed</dt><dd class="path">${esc(d.path)}</dd>`:''}
      </dl>
      ${x.flags.map(f=>`<div class="note ${f.severity==='high'?'high':''}">
        <b>${esc(f.id.replace(/_/g,' '))}</b>${esc(f.message)}
        <em> — ${f.blocks_filing?'blocks filing':'files anyway'}</em></div>`).join('')}
      ${withActions?`<div class="acts">
        <button id="y-${x.doc_id}" onclick="event.stopPropagation();decide('${x.doc_id}','approve')">Approve</button>
        <button id="n-${x.doc_id}" onclick="event.stopPropagation();decide('${x.doc_id}','reject')">Reject</button>
      </div>`:''}
    </div></div>`;
}

function toggleRow(id){ document.getElementById('row-'+id).classList.toggle('open'); }

function groupsHtml(data, withActions){
  const byEvent={}, loose=[];
  data.documents.forEach(x=> x.event_id
    ? (byEvent[x.event_id]=byEvent[x.event_id]||[]).push(x) : loose.push(x));
  let html='';
  data.events.forEach(ev=>{
    html+=`<div class="group"><header><b>${esc(ev.client)}</b>
      <span>${esc(ev.subject)} · ${esc(ev.date||'undated')} · ${esc(ev.record_label)}${
        ev.sub_kind?' · '+esc(ev.sub_kind):''}</span></header>`;
    (byEvent[ev.event_id]||[]).forEach(x=>html+=rowHtml(x, withActions));
    html+='</div>';
  });
  if(loose.length){
    html+=`<div class="group"><header><b>Outside any advice event</b>
      <span>licensee material, client-level documents, and anything not placed</span>
      </header>`;
    loose.forEach(x=>html+=rowHtml(x, withActions));
    html+='</div>';
  }
  return html;
}

function summaryHtml(d){
  const high=d.documents.reduce((n,x)=>n+x.flags.filter(f=>f.severity==='high').length,0);
  const cell=(n,l)=>`<div><b>${n}</b><span>${l}</span></div>`;
  return cell(d.batch.documents,'documents')+cell(d.events.length,'advice events')
    +cell(d.batch.needs_review,'need review')+cell(high,'high findings');
}

function treeText(d){
  const tree={};
  d.documents.forEach(x=>{const f=((x.destination||{}).folder||[]).join('/');
    (tree[f]=tree[f]||[]).push(x)});
  let out='';
  Object.keys(tree).sort().forEach(k=>{
    out+='<b>'+esc(k)+'/</b>\n';
    tree[k].slice().sort((a,b)=>((a.destination||{}).filename||'')
      .localeCompare((b.destination||{}).filename||''))
      .forEach(x=>{out+='    '+esc((x.destination||{}).filename||'')+'\n'});
    out+='\n';
  });
  return out;
}
"""
