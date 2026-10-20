import { useState } from 'react';
import { Icon, Dot, FileIcon, Confidence, StatusBadge, Type } from './atoms.jsx';
import {
  FILTERS, groupByEvent, folderTree, countFiles, highFindings, statusOf, initials, plural, flagTitle, cls,
} from './model.js';

/* ---------------------------------------------------------------- Overview */
export function Overview({ d, go }) {
  const high = highFindings(d);
  const clients = new Set(d.events.map((e) => e.client)).size;
  const stats = [
    { n: d.batch.documents, l: 'Documents', s: `${d.batch.auto_filed} proposed for filing`, to: 'events' },
    { n: d.events.length, l: 'Advice events', s: plural(clients, 'client', 'clients'), to: 'events' },
    { n: d.batch.needs_review, l: 'Need review', s: 'refused, with a reason', to: 'review', c: d.batch.needs_review ? 'warn' : '', dot: 'warn' },
    { n: high, l: 'High findings', s: 'compliance flags', to: 'events', c: high ? 'bad' : '', dot: 'bad' },
  ];
  return (
    <div className="pad">
      <p className="eyebrow">Sample client folder · {d.batch.documents} files</p>
      <h1>A messy client folder in, a proposed filing out</h1>
      <p className="lede">For each document the tool decides what it is, which client and which{' '}
        <em>advice event</em> it belongs to, and proposes where to file it — or
        refuses, and says why. It never files silently.</p>
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
        <span><Dot s="bad" />High-severity finding</span>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Advice events */
function DocRow({ x, selected, onSelect }) {
  return (
    <tr className="doc" aria-selected={selected === x.doc_id} onClick={() => onSelect(x.doc_id)} data-doc={x.doc_id}>
      <td>
        <div className="name"><FileIcon doc={x} />
          <span style={{ minWidth: 0 }}><b>{x.source_name}</b><small>{x.date || 'undated'}</small></span>
        </div>
      </td>
      <td className="col-type"><Type>{x.type_label}</Type></td>
      <td className="col-client">{x.client || '—'}</td>
      <td className="col-conf"><Confidence doc={x} /></td>
      <td className="col-status"><StatusBadge doc={x} /></td>
    </tr>
  );
}

function GroupRow({ avatar, title, meta, tag, count }) {
  return (
    <tr className="grp"><td colSpan={5}><div className="grp-in">
      {avatar}<b>{title}</b><span className="m">{meta}</span>{tag && <Type>{tag}</Type>}
      <span className="ct">{plural(count, 'document', 'documents')}</span>
    </div></td></tr>
  );
}

export function Events({ d, selected, onSelect }) {
  const [filter, setFilter] = useState('all');
  const keep = FILTERS.find((f) => f.key === filter).test;
  const { groups, loose } = groupByEvent(d, keep);
  const empty = !groups.length && !loose.length;
  return (
    <>
      <div className="tabs" role="tablist">
        {FILTERS.map((f) => (
          <button key={f.key} className="tab" role="tab" aria-selected={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label}<b>{d.documents.filter(f.test).length}</b>
          </button>
        ))}
      </div>
      <table className="table">
        <thead><tr><th>Name</th><th className="col-type">Type</th><th className="col-client">Client</th><th className="col-conf">Confidence</th><th className="col-status">Status</th></tr></thead>
        <tbody>
          {groups.map(({ ev, docs }) => [
            <GroupRow key={ev.event_id}
              avatar={<span className="av">{initials(ev.client)}</span>}
              title={ev.client}
              meta={`${ev.subject} · ${ev.date || 'undated'}${ev.sub_kind ? ' · ' + ev.sub_kind : ''}`}
              tag={ev.record_label} count={docs.length} />,
            ...docs.map((x) => <DocRow key={x.doc_id} x={x} selected={selected} onSelect={onSelect} />),
          ])}
          {loose.length > 0 && [
            <GroupRow key="loose"
              avatar={<span className="av" style={{ background: 'var(--sel)', color: 'var(--mute)' }}><Icon id="folder" /></span>}
              title="Outside any advice event"
              meta="licensee material, client-level documents, and anything not placed" count={loose.length} />,
            ...loose.map((x) => <DocRow key={x.doc_id} x={x} selected={selected} onSelect={onSelect} />),
          ]}
          {empty && <tr><td colSpan={5} className="empty">No documents match this filter.</td></tr>}
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

/* ---------------------------------------------------------------- Folder tree */
function Folder({ name, node, selected, onSelect }) {
  const [open, setOpen] = useState(true);
  return (
    <li className={open ? '' : 'closed'}>
      <button className="tr" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="tw"><Icon id="down" /></span><span className="fo"><Icon id="folder" /></span>
        <span className="nm">{name}</span><span className="ct">{countFiles(node)}</span>
      </button>
      <Branch node={node} selected={selected} onSelect={onSelect} />
    </li>
  );
}

function Branch({ node, selected, onSelect }) {
  const files = node.files.slice().sort((a, b) =>
    ((a.destination || {}).filename || '').localeCompare((b.destination || {}).filename || ''));
  return (
    <ul className="tn">
      {Object.keys(node.dirs).sort().map((k) => (
        <Folder key={k} name={k} node={node.dirs[k]} selected={selected} onSelect={onSelect} />
      ))}
      {files.map((x) => (
        <li key={x.doc_id}>
          <button className="tr" aria-selected={selected === x.doc_id} onClick={() => onSelect(x.doc_id)} title={x.source_name} data-doc={x.doc_id}>
            <span className="fl"><Icon id="file" /></span>
            <span className="nm">{(x.destination || {}).filename || x.source_name}</span>
            <span className="ty"><Type>{x.type_label}</Type><i className={`dot ${cls(statusOf(x))}`} /></span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function Tree({ d, selected, onSelect }) {
  return (
    <div className="tree-wrap">
      <div className="box sub tree-note"><Icon id="info" />
        <span><b>{d.profile_name}</b> — {d.profile_description}</span></div>
      {/* key on the profile so folders re-open when the scheme changes */}
      <div className="box tree" key={d.filing_profile}><Branch node={folderTree(d)} selected={selected} onSelect={onSelect} /></div>
    </div>
  );
}

/* ---------------------------------------------------------------- About */
const STEPS = [
  ['Read', 'Text is pulled from every file in the folder, scanned or digital, and its extraction quality is scored.'],
  ['Identify', 'Each document is typed (SOA, ROA, FSG, Fact Find, Risk Profile…), dated, and matched to a client and advice event.'],
  ['Check', 'Compliance rules from the knowledge base run across the event, flagging gaps and mismatches by severity.'],
  ['Propose', 'A destination is proposed under the firm’s own filing scheme, or the tool refuses and says why.'],
  ['Ask a person', 'A human approves every suggestion. It never files silently.'],
];

export function About({ whyLocal }) {
  return (
    <div className="pad about">
      <p className="eyebrow">How it works</p>
      <h1>Five steps, and the last one is always a person</h1>
      <ol className="steps">
        {STEPS.map(([k, p], i) => <li key={k}><div className="k"><i>{i + 1}</i>{k}</div><p>{p}</p></li>)}
      </ol>
      <div className="box">
        <h3><Icon id="lock" />Why it runs locally</h3>
        <p>Client files are confidential. A hosted version of the tool would mean uploading them to somebody else’s computer, which is a data-residency decision for the licensee rather than a deployment choice.</p>
        <p>So firms piloting the tool run it as a desktop app on their own computers, and confidential documents never leave the firm. This page is a demonstration on fabricated documents: it has no upload control because there is nowhere for one to go. <a href={whyLocal}>Why local&nbsp;&rarr;</a></p>
      </div>
      <div className="box">
        <h3><Icon id="folder" />Fits the firm’s existing system</h3>
        <p>Changing the filing scheme changes the folders and nothing else — the classification, the advice events and the findings are identical. That is what lets the tool fit a firm’s existing system instead of replacing it.</p>
      </div>
    </div>
  );
}
