import { useState } from 'react';
import { Icon, Dot, FileIcon, Confidence, StatusBadge, Type } from './atoms.jsx';
import {
  FILTERS, batchable, BATCH_LEVELS, groupByEvent, groupByStatus, folderTree, countFiles, highFindings, statusOf, initials, plural, flagTitle, cls, pct,
} from './model.js';

/* ---------------------------------------------------------------- Overview */
export function Overview({ d, go, startTour }) {
  const high = highFindings(d);
  const clients = new Set(d.events.map((e) => e.client)).size;
  const stats = [
    { n: d.batch.documents, l: 'Documents', s: `${d.batch.auto_filed} proposed for filing`, to: 'events' },
    { n: d.events.length, l: 'Advice events', s: plural(clients, 'client', 'clients'), to: 'events' },
    { n: d.batch.needs_review, l: 'Need review', s: 'refused, with a reason', to: 'review', c: d.batch.needs_review ? 'warn' : '', dot: 'warn' },
    { n: high, l: 'Worth checking', s: 'for a person to look at', to: 'events', c: high ? 'bad' : '', dot: 'bad' },
  ];
  return (
    <div className="pad">
      <p className="eyebrow">{d.dataset_label} · {d.batch.documents} files</p>
      <h1>{d.dataset === 'public' ? 'Real published PDFs and a tool that won’t guess' : 'A messy client folder in, a proposed filing out'}</h1>
      <p className="lede">For each document the tool decides what it is, which client and which{' '}
        <em>advice event</em> it belongs to. Then it proposes where to file it
        or refuses and says why. It never files silently.</p>
      {d.dataset_note && <div className="box sub set-note"><Icon id="info" /><span>{d.dataset_note}</span></div>}
      <button className="btn primary tour-cta" onClick={startTour}><Icon id="play" />Take the 1-minute tour</button>
      <div className="stats">
        {stats.map((t) => (
          <button key={t.l} className={`stat ${t.c || ''}`} onClick={() => go(t.to)}>
            <span className="l">{t.dot && <Dot s={t.dot} />}{t.l}</span>
            <span className="n">{t.n}</span>
            <span className="s">{t.s}</span>
          </button>
        ))}
      </div>
      <div className="box sub scheme-box">
        <span className="ic"><Icon id="folder" /></span>
        <div><b>{d.profile_name}</b><span>{d.profile_description}</span></div>
      </div>
      <div className="legend">
        <span><Dot s="ok" />Confident</span>
        <span><Dot s="warn" />Needs review</span>
        <span><Dot s="bad" />Worth checking</span>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Advice events */
function DocRow({ x, selected, onSelect, threshold, decision }) {
  return (
    <tr className="doc" aria-selected={selected === x.doc_id} onClick={() => onSelect(x.doc_id)} data-doc={x.doc_id}>
      <td>
        <div className="name"><FileIcon doc={x} />
          <span style={{ minWidth: 0 }} title={x.source_name}><b>{x.source_name.split('/').pop()}</b><small>{x.date || 'undated'}</small></span>
        </div>
      </td>
      <td className="col-type"><Type>{x.type_label}</Type></td>
      <td className="col-client">{x.client || 'none'}</td>
      <td className="col-conf"><Confidence doc={x} threshold={threshold} /></td>
      <td className="col-status">{decision ? <Decided k={decision} /> : <StatusBadge doc={x} />}</td>
      <td className="col-why">
        <button className="why-btn" title="Why it was filed here, and how sure the tool is"
          onClick={(e) => { e.stopPropagation(); onSelect(x.doc_id); }}>
          <Icon id="info" /><span className="lbl">Why?</span></button>
      </td>
    </tr>
  );
}

export const Decided = ({ k }) => (
  <span className={`badge ${k === 'approve' ? 'filed' : 'bad'}`}><Icon id={k === 'approve' ? 'check' : 'x'} />
    {k === 'approve' ? 'Filed (demo)' : 'Rejected'}</span>
);

function BatchBar({ d, decisions, onBatch }) {
  const [level, setLevel] = useState(BATCH_LEVELS[0]);
  const ready = d.documents.filter((x) => batchable(x) && x.confidence >= level && !decisions[x.doc_id]);
  const oneByOne = d.documents.filter((x) => !batchable(x) && !decisions[x.doc_id]).length;
  return (
    <div className="batch">
      <div className="batch-tx">
        <b>Approve the confident ones together</b>
        <span>Placed, nothing held and nothing to check, at or above
          <span className="select inline"><select aria-label="Confidence level" value={level} onChange={(e) => setLevel(+e.target.value)}>
            {BATCH_LEVELS.map((l) => <option key={l} value={l}>{pct(l)}%</option>)}
          </select><Icon id="down" /></span>.
          {oneByOne > 0 && <> {plural(oneByOne, 'other needs', 'others need')} a person one by one.</>}</span>
      </div>
      <button className="btn primary" disabled={!ready.length} onClick={() => onBatch(ready.map((x) => x.doc_id), level)}>
        <Icon id="check" />{ready.length ? `Approve and file ${ready.length}` : 'Nothing left to batch'}</button>
    </div>
  );
}

function GroupRow({ avatar, title, meta, tag, count }) {
  return (
    <tr className="grp"><td colSpan={6}><div className="grp-in">
      {avatar}<b>{title}</b><span className="m">{meta}</span>{tag && <Type>{tag}</Type>}
      <span className="ct">{plural(count, 'document', 'documents')}</span>
    </div></td></tr>
  );
}

const STATUS_META = {
  'Needs review': 'held, the tool will not file these',
  'Worth checking': 'a compliance point for a person to look at',
  Note: 'a minor point, can still be filed',
  Confident: 'nothing to check',
};

export function Events({ d, selected, onSelect, decisions, onBatch }) {
  const [filter, setFilter] = useState('all');
  const [by, setBy] = useState('event');
  const keep = FILTERS.find((f) => f.key === filter).test;
  const { groups, loose } = groupByEvent(d, keep);
  const byStatus = groupByStatus(d, keep);
  const empty = !groups.length && !loose.length;
  const t = d.confidence_threshold;
  const row = (x) => <DocRow key={x.doc_id} x={x} selected={selected} onSelect={onSelect} threshold={t} decision={decisions[x.doc_id]} />;
  return (
    <>
      <BatchBar d={d} decisions={decisions} onBatch={onBatch} />
      <div className="tabs" role="tablist">
        {FILTERS.map((f) => (
          <button key={f.key} className="tab" role="tab" aria-selected={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label}<b>{d.documents.filter(f.test).length}</b>
          </button>
        ))}
        <span className="grow" />
        <div className="seg" role="group" aria-label="Group by">
          <span className="seg-l">Group by</span>
          <button aria-pressed={by === 'event'} onClick={() => setBy('event')}>Advice event</button>
          <button aria-pressed={by === 'status'} onClick={() => setBy('status')}>Status</button>
        </div>
      </div>
      <div className="scale" role="note">
        <span className="scale-l">Confidence scale</span>
        <span className="scale-k">0%</span>
        <span className="scale-bar" aria-hidden="true">
          <i style={{ width: `${pct(t)}%` }} className="below" /><i className="above" />
          <b className="tick" style={{ left: `${pct(t)}%` }} />
        </span>
        <span className="scale-k">100%</span>
        <span className="scale-t">The line is {pct(t)}%. Below it the tool will not file the document and holds it for a person.</span>
        <span className="scale-note">Confidence is how sure it is of the document type. Worth checking is separate: a compliance point for a person to look at, even at 100%.</span>
      </div>
      <table className="table">
        <thead><tr><th>Name</th><th className="col-type">Type</th><th className="col-client">Client</th><th className="col-conf">Confidence</th><th className="col-status">Status</th><th className="col-why"><span className="sr">Explain</span></th></tr></thead>
        <tbody>
          {by === 'status' && byStatus.map(({ label, docs }) => [
            <GroupRow key={label}
              avatar={<Dot s={statusOf(docs[0])} />}
              title={label} meta={STATUS_META[label]} count={docs.length} />,
            ...docs.map(row),
          ])}
          {by === 'event' && groups.map(({ ev, docs }) => [
            <GroupRow key={ev.event_id}
              avatar={<span className="av">{initials(ev.client)}</span>}
              title={ev.client}
              meta={`${ev.subject} · ${ev.date || 'undated'}${ev.sub_kind ? ' · ' + ev.sub_kind : ''}`}
              tag={ev.record_label} count={docs.length} />,
            ...docs.map(row),
          ])}
          {by === 'event' && loose.length > 0 && [
            <GroupRow key="loose"
              avatar={<span className="av" style={{ background: 'var(--sel)', color: 'var(--mute)' }}><Icon id="folder" /></span>}
              title="Outside any advice event"
              meta="licensee material, client-level documents and anything not placed" count={loose.length} />,
            ...loose.map(row),
          ]}
          {empty && <tr><td colSpan={6} className="empty">No documents match this filter.</td></tr>}
        </tbody>
      </table>
    </>
  );
}

/* ---------------------------------------------------------------- Needs review */
export function Review({ d, selected, onSelect }) {
  const held = d.documents.filter((x) => x.needs_review);
  return (
    <>
      <p className="intro-line">Documents the tool refused to place. Each one waits for a person; nothing here is filed.</p>
      <div className="rv-list">
        {!held.length && <div className="empty">Nothing needs review in this batch.</div>}
        {held.map((x) => {
          const f = x.flags[0];
          return (
            <div key={x.doc_id} className={`rv ${statusOf(x) === 'bad' ? 'bad' : ''}`} tabIndex={0}
              aria-selected={selected === x.doc_id} onClick={() => onSelect(x.doc_id)}
              onKeyDown={(e) => e.key === 'Enter' && onSelect(x.doc_id)} data-doc={x.doc_id}>
              <span className="ic"><Icon id="alert" /></span>
              <div className="tx">
                <b>{x.source_name}</b><span className="m">{x.type_label} · {x.client || 'no client'} · {x.date || 'undated'}</span>
                {f && <p><strong>{flagTitle(f.id)}.</strong> {f.message}</p>}
              </div>
              <button className="btn sm">Review</button>
            </div>
          );
        })}
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- Filing log */
// Every approval, newest first, grouped by the click that made it. Nothing is
// deleted: an undone batch stays in the log, marked undone.
export function Log({ d, log, selected, onSelect, onUndo }) {
  const byId = Object.fromEntries(d.documents.map((x) => [x.doc_id, x]));
  return (
    <div className="pad log">
      <p className="intro-line">Every approval, grouped by the click that made it. Open a document to see why it was filed there.
        In this demo the log lives in this browser tab only.</p>
      {!log.length && <div className="box sub empty">Nothing filed yet. Approve the confident ones on Advice events, or decide one at a time in a document’s panel.</div>}
      {log.slice().reverse().map((e) => (
        <div key={e.id} className={`box log-entry ${e.undone ? 'undone' : ''}`}>
          <div className="log-head">
            <b>{e.kind === 'batch' ? `Batch: ${plural(e.ids.length, 'document', 'documents')} at or above ${pct(e.level)}%` : `${e.decision === 'approve' ? 'Approved' : 'Rejected'} one by one`}</b>
            <span className="m">{e.at}{e.undone ? ' · undone' : ''}</span>
            <span className="grow" />
            {!e.undone && <button className="link-btn" onClick={() => onUndo(e.id)}>Undo</button>}
          </div>
          <ul>
            {e.ids.map((id) => {
              const x = byId[id];
              return x && (
                <li key={id}>
                  <button className="log-doc" aria-selected={selected === id} data-doc={id} onClick={() => onSelect(id)}>
                    <span className="nm"><b>{x.source_name}</b><Type>{x.type_label}</Type><span className="pc">{pct(x.confidence)}%</span></span>
                    <span className="to">{e.decision === 'approve' ? <>&rarr; {(x.destination || {}).path}</> : 'not filed'}</span>
                    <span className="why">{(x.destination || {}).rationale || x.attachment_reason}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- Folder tree */
function Folder({ name, node, selected, onSelect, decisions }) {
  const [open, setOpen] = useState(true);
  return (
    <li className={open ? '' : 'closed'}>
      <button className="tr" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="tw"><Icon id="down" /></span><span className="fo"><Icon id="folder" /></span>
        <span className="nm">{name}</span><span className="ct">{countFiles(node)}</span>
      </button>
      <Branch node={node} selected={selected} onSelect={onSelect} decisions={decisions} />
    </li>
  );
}

function Branch({ node, selected, onSelect, decisions }) {
  const files = node.files.slice().sort((a, b) =>
    ((a.destination || {}).filename || '').localeCompare((b.destination || {}).filename || ''));
  return (
    <ul className="tn">
      {Object.keys(node.dirs).sort().map((k) => (
        <Folder key={k} name={k} node={node.dirs[k]} selected={selected} onSelect={onSelect} decisions={decisions} />
      ))}
      {files.map((x) => (
        <li key={x.doc_id}>
          <button className="tr" aria-selected={selected === x.doc_id} onClick={() => onSelect(x.doc_id)} title={x.source_name} data-doc={x.doc_id}>
            <span className="fl"><Icon id="file" /></span>
            <span className="nm">{(x.destination || {}).filename || x.source_name}</span>
            <span className="ty">{decisions[x.doc_id] === 'approve' && <span className="filed-tag"><Icon id="check" />Filed</span>}
              <Type>{x.type_label}</Type><i className={`dot ${cls(statusOf(x))}`} /></span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function Tree({ d, selected, onSelect, decisions }) {
  return (
    <div className="tree-wrap">
      <div className="box sub tree-note"><Icon id="info" />
        <span><b>{d.profile_name}.</b> {d.profile_description}</span></div>
      {/* key on the profile so folders re-open when the scheme changes */}
      <div className="box tree" key={d.filing_profile}><Branch node={folderTree(d)} selected={selected} onSelect={onSelect} decisions={decisions} /></div>
    </div>
  );
}

/* ---------------------------------------------------------------- About */
const STEPS = [
  ['Read', 'Text is pulled from every file in the folder, scanned or digital. Its extraction quality is scored.'],
  ['Identify', 'Each document is typed (SOA, ROA, FSG, Fact Find, Risk Profile…), dated and matched to a client and advice event.'],
  ['Check', 'Rules from the knowledge base look for gaps and mismatches a person should check, such as a risk profile that does not match the SOA.'],
  ['Propose', 'A destination is proposed under the firm’s own filing scheme. If the tool is unsure it refuses and says why.'],
  ['Ask a person', 'A human approves every suggestion. It never files silently.'],
];

export function About({ whyLocal }) {
  return (
    <div className="pad about">
      <p className="eyebrow">Why I built this</p>
      <h1>Big advice software is clunky and expensive</h1>
      <div className="box why">
        <p>Working around Australian advice firms, I kept hearing the same thing: the big
          platforms are clunky and expensive and built for large licensees. Most practices are
          small, with two or three advisers. They still file client documents by hand.</p>
        <p>Those platforms <em>store</em> documents. None of them <em>reads</em> one and says
          “this is an ROA for this client, from this piece of advice”. When a record is filed in
          the wrong place the firm loses time and carries a compliance risk. It has to
          be able to produce the right document when asked.</p>
        <p>So this is deliberately small. It does one job and sits on top of the system a firm
          already uses instead of replacing it. Every decision stays with a person.</p>
      </div>

      <p className="eyebrow">How it works</p>
      <h1>Five steps. The last one is always a person.</h1>
      <ol className="steps">
        {STEPS.map(([k, p], i) => <li key={k}><div className="k"><i>{i + 1}</i>{k}</div><p>{p}</p></li>)}
      </ol>
      <div className="box">
        <h3><Icon id="lock" />Built with privacy in mind</h3>
        <p>Client files are confidential. A hosted version of the tool would mean uploading them to somebody else’s computer. That is a data-residency decision for the licensee, not a deployment choice.</p>
        <p>That is why the design keeps documents on the firm’s own computer. This page is a prototype demo on demo and publicly published documents. It has no upload control because there is nowhere for one to go. <a href={whyLocal}>Read more&nbsp;&rarr;</a></p>
      </div>
      <div className="box">
        <h3><Icon id="folder" />Fits the firm’s existing system</h3>
        <p>Changing the filing scheme changes the folders and nothing else. The classification, the advice events and the points to check are identical. That is what lets the tool fit a firm’s existing system instead of replacing it.</p>
      </div>
    </div>
  );
}
