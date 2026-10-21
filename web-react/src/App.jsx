import { useEffect, useRef, useState } from 'react';
import { Icon } from './atoms.jsx';
import Inspector from './Inspector.jsx';
import Tour, { STEPS as TOUR } from './Tour.jsx';
import Welcome from './Welcome.jsx';
import { Overview, Events, Review, Tree, About } from './views.jsx';
import { DATASETS, SETS, PROFILES, statusOf, initials } from './model.js';

const REPO = 'https://github.com/ahaythorpe/advice-document-classifier';
const WHY_LOCAL = `${REPO}/blob/main/docs/DEPLOYMENT.md`;
const VIEWS = { overview: 'Overview', events: 'Advice events', review: 'Needs review', tree: 'Folder tree', about: 'About' };
const WITH_INSPECTOR = ['events', 'review', 'tree'];

// The welcome popup shows once per browser; storage is optional, so it may show again.
const welcomed = () => { try { return localStorage.getItem('welcomed') === '1'; } catch { return false; } };
const markWelcomed = () => { try { localStorage.setItem('welcomed', '1'); } catch { /* demo: storage optional */ } };

const viewFromHash = () => (VIEWS[location.hash.slice(1)] ? location.hash.slice(1) : 'overview');

function useTheme() {
  // Light by default; Auto follows the computer's setting.
  const read = () => { try { return localStorage.getItem('theme') || 'light'; } catch { return 'light'; } };
  const [mode, setMode] = useState(read);
  useEffect(() => {
    const el = document.documentElement;
    try { localStorage.setItem('theme', mode); } catch { /* demo: storage optional */ }
    mode === 'auto' ? el.removeAttribute('data-theme') : el.setAttribute('data-theme', mode);
  }, [mode]);
  return [mode, setMode];
}

function useWide() {
  const [wide, setWide] = useState(() => window.innerWidth > 1100);
  useEffect(() => {
    const on = () => setWide(window.innerWidth > 1100);
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, []);
  return wide;
}

export default function App() {
  const [set, setSet] = useState(SETS[0]);
  const [profile, setProfile] = useState(PROFILES[0]);
  const [view, setView] = useState(viewFromHash);
  const [selected, setSelected] = useState(null);
  const [decisions, setDecisions] = useState({});      // in memory only: the demo stores nothing
  const [theme, setTheme] = useTheme();
  const [tour, setTour] = useState(null);           // step index while the tour is open
  const [welcome, setWelcome] = useState(() => !welcomed());
  const wide = useWide();
  const scrollRef = useRef(null);

  const d = DATASETS[set][profile];   // changing the scheme changes the folders and nothing else
  const doc = selected && d.documents.find((x) => x.doc_id === selected);

  useEffect(() => {
    const on = () => setView(viewFromHash());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = 0; }, [view]);

  const step = (n) => {
    const i = d.documents.findIndex((x) => x.doc_id === selected) + n;
    if (d.documents[i]) setSelected(d.documents[i].doc_id);
  };
  useEffect(() => {
    const on = (e) => {
      if (e.target.closest && e.target.closest('select')) return;
      if (e.key === 'Escape') { setSelected(null); setTour(null); if (welcome) closeWelcome(); }
      if (selected && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); step(e.key === 'ArrowDown' ? 1 : -1); }
    };
    document.addEventListener('keydown', on);
    return () => document.removeEventListener('keydown', on);
  });
  useEffect(() => {
    if (!selected) return;
    const el = document.querySelector(`.view:not([hidden]) [data-doc="${selected}"]`);
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
  }, [selected]);

  const go = (v) => { location.hash = v; };
  const tourTo = (i) => {
    const s = TOUR[i];
    setTour(i);
    setSet(SETS[0]);                    // the tour is written about the demo folder
    go(s.view);
    const pick = s.select && s.select(DATASETS[SETS[0]][profile]);
    setSelected(pick ? pick.doc_id : null);
  };
  const endTour = () => { setTour(null); setSelected(null); };
  const closeWelcome = () => { markWelcomed(); setWelcome(false); };
  const decide = (k) => setDecisions((m) => ({ ...m, [selected]: m[selected] === k ? undefined : k }));
  const showInspector = WITH_INSPECTOR.includes(view) && (doc || wide);

  const perClient = {};
  d.documents.forEach((x) => { if (x.client) perClient[x.client] = (perClient[x.client] || 0) + 1; });
  const n = d.batch.documents;
  const ok = d.documents.filter((x) => statusOf(x) === 'ok').length;
  const warn = d.documents.filter((x) => statusOf(x) === 'warn').length;
  const sub = { events: `${d.events.length} events · ${n} documents`, review: `${d.batch.needs_review} held`, tree: 'Proposed filing' }[view] || '';
  const viewProps = { d, selected, onSelect: setSelected };

  return (
    <div className="window" role="application" aria-label="Advice Document Filing (demo only)">
      <div className="ribbon" aria-hidden="true">Demo</div>

      <div className="titlebar">
        <div className="lights" aria-hidden="true"><i /><i /><i /></div>
        <span className="appmark" aria-hidden="true"><Icon id="cabinet" /></span>
        <span className="appname">Advice Document Filing</span>
        <span className="tb-demo">Demo</span>
        <span className="pill" title="An early demo to show the idea."><Icon id="info" /><span className="lbl">Prototype</span></span>
        <span className="grow" />
        <a className="tb-link" href={REPO}><Icon id="code" />Source</a>
        <div className="seg" role="group" aria-label="Theme">
          {['auto', 'light', 'dark'].map((m) => (
            <button key={m} aria-pressed={theme === m} onClick={() => setTheme(m)}>{m[0].toUpperCase() + m.slice(1)}</button>
          ))}
        </div>
      </div>

      <div className="banner" role="note">
        <span className="demo-tag">Demo only</span>
        <div className="msg">
          <b>Prototype demo, shared to show how the idea works.</b>
          <span>Demo and publicly published documents only. Names and details are made up to protect privacy. There is no upload control, so no real client file can be added.</span>
        </div>
        <a href={WHY_LOCAL}>Read more&nbsp;&rarr;</a>
      </div>

      <div className="body">
        <nav className="side" aria-label="Sections">
          {SETS.length > 1 && <>
            <h6>Sample set</h6>
            {SETS.map((k) => (
              <button key={k} className="nav" aria-current={set === k ? 'true' : undefined}
                onClick={() => { setSet(k); setSelected(null); }}>
                <Icon id={k === 'public' ? 'file' : 'cabinet'} />{DATASETS[k][profile].dataset_label}
              </button>
            ))}
          </>}
          <h6>Batch</h6>
          {[['overview', 'grid'], ['events', 'layers', d.events.length], ['review', 'alert', d.batch.needs_review, 'warn'], ['tree', 'folder', n]].map(([v, ic, count, c]) => (
            <a key={v} className="nav" href={`#${v}`} aria-current={view === v ? 'page' : undefined}>
              <Icon id={ic} />{VIEWS[v]}
              {count ? <span className={`count ${c || ''}`}>{count}</span> : null}
            </a>
          ))}
          <h6>Clients</h6>
          {Object.keys(perClient).sort().map((c) => (
            <div key={c} className="client"><span className="av">{initials(c)}</span>{c}<span className="count">{perClient[c]}</span></div>
          ))}
          <h6>Help</h6>
          <button className="nav" onClick={() => tourTo(0)}><Icon id="play" />Take the tour</button>
          <button className="nav" onClick={() => setWelcome(true)}><Icon id="shield" />Disclaimers</button>
          <a className="nav" href="#about" aria-current={view === 'about' ? 'page' : undefined}><Icon id="info" />About</a>
          <div className="foot">
            <b>{d.batch.auto_filed} of {n} proposed</b>
            <div className="meter">
              <i style={{ width: `${ok / n * 100}%`, background: 'var(--ok)' }} />
              <i style={{ width: `${warn / n * 100}%`, background: 'var(--warn)' }} />
              <i style={{ width: `${(n - ok - warn) / n * 100}%`, background: 'var(--bad)' }} />
            </div>
            {d.batch.needs_review} held for review · threshold {d.confidence_threshold}
          </div>
        </nav>

        <div className="sheet">
          <main className="main">
            <div className="toolbar">
              <h2>{VIEWS[view]}</h2>
              <span className="sub">{sub}</span>
              <span className="grow" />
              <div className="scheme">
                <label htmlFor="profile">Filing scheme</label>
                <div className="select">
                  <select id="profile" value={profile} onChange={(e) => setProfile(e.target.value)}>
                    {PROFILES.map((p) => <option key={p} value={p}>{DATASETS[set][p].profile_name}</option>)}
                  </select>
                  <Icon id="down" />
                </div>
              </div>
            </div>

            <div className="scroll" ref={scrollRef}>
              <section className="view" hidden={view !== 'overview'}><Overview d={d} go={go} startTour={() => tourTo(0)} /></section>
              <section className="view" hidden={view !== 'events'}><Events {...viewProps} /></section>
              <section className="view" hidden={view !== 'review'}><Review {...viewProps} /></section>
              <section className="view" hidden={view !== 'tree'}><Tree {...viewProps} /></section>
              <section className="view" hidden={view !== 'about'}><About whyLocal={WHY_LOCAL} /></section>

              <footer>
                <span className="kb"><Icon id="shield" /><span>Knowledge base v{d.knowledge_base_version}</span></span> · Australia, Corporations Act 2001, ASIC.
                Not legal advice.<br />
                Changing the filing scheme changes the folders and nothing else. The
                classification, the advice events and the points to check are identical. That is what
                lets the tool fit a firm’s existing system instead of replacing it.
              </footer>
            </div>
          </main>

          {showInspector && (
            <Inspector d={d} doc={doc} decision={decisions[selected]}
              onDecide={decide} onStep={step} onClose={() => setSelected(null)} />
          )}
        </div>
      </div>

      {tour !== null && <Tour d={d} step={tour} onStep={tourTo} onClose={endTour} />}
      {welcome && <Welcome onClose={closeWelcome} onTour={() => { closeWelcome(); tourTo(0); }} />}
    </div>
  );
}
