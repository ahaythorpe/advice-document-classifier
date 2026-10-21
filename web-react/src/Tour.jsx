import { useEffect, useLayoutEffect, useRef, useState } from 'react';

const soa = (d) => d.documents.find((x) => x.type_label === 'SOA');

// A click-through tour. Each step opens a view, spotlights one element and says
// what it does. Steps marked `click` ask the visitor to click the element
// themselves, and move on when they do; Next always works too.
export const STEPS = [
  {
    view: 'overview', target: '.stats',
    title: 'A messy client folder',
    body: 'Ten demo documents, scanned and named scan_001 to scan_010 the way they often arrive. The tool has read every one. These tiles sum up what it found.',
  },
  {
    view: 'overview', target: 'a.nav[href="#events"]', click: true,
    title: 'Open the advice events',
    body: 'Click Advice events.',
  },
  {
    view: 'events', target: (d) => `.view:not([hidden]) tr[data-doc="${soa(d).doc_id}"]`, click: true,
    title: 'Grouped by advice event',
    body: 'The fact find, risk profile, SOA and authority to proceed for one recommendation sit together. Click the SOA to see how the tool read it.',
  },
  {
    view: 'events', target: '.insp-body', select: soa,
    title: 'Why it was placed there',
    body: 'In short says how sure the tool is and why it chose this folder. The detail is underneath.',
  },
  {
    view: 'events', target: '.view:not([hidden]) .batch',
    title: 'File the confident ones in one click',
    body: 'Everything above the line with nothing to check is filed together. You choose the line. Try it: nothing is saved.',
  },
  {
    view: 'events', target: 'a.nav[href="#review"]', click: true,
    title: 'What it would not file',
    body: 'Click Needs review.',
  },
  {
    view: 'review', target: '.rv-list',
    title: 'It holds rather than guesses',
    body: 'When the tool is not sure it holds the document and says why. A person approves or rejects each one. A wrongly filed client record is a compliance problem.',
  },
  {
    view: 'review', target: 'a.nav[href="#log"]',
    title: 'Every filing is logged',
    body: 'The Filing log lists each batch with the reason for every document. Any of it can be undone.',
  },
  {
    view: 'tree', target: '.view:not([hidden]) .tree .tn .tn > li > .tr',   // the first advice event folder
    title: 'Client then advice event',
    body: 'Each client has a folder with one folder per advice event inside. The stage shows on each document. A firm can switch to its own scheme above.',
  },
  {
    view: 'about', target: '.about .why',
    title: 'Why I built this',
    body: 'Big advice software is clunky and expensive. None of it reads a document for you. This is small and sits on top of what a firm already uses.',
  },
];

const PAD = 6;
const CARD = 330;

// Follows the target every frame, so the spotlight stays right when the view
// changes, a panel opens or the page scrolls. Gone if the target is not on screen.
function useRect(selector) {
  const [rect, setRect] = useState(null);
  useLayoutEffect(() => {
    let raf = 0;
    let last = '';
    let scrolled = false;
    const tick = () => {
      const el = selector && document.querySelector(selector);
      const r = el && el.getBoundingClientRect();
      const next = r && r.width && r.height ? { top: r.top, left: r.left, width: r.width, height: r.height } : null;
      if (el && next && !scrolled && el.scrollIntoView) { el.scrollIntoView({ block: 'nearest' }); scrolled = true; }
      const key = JSON.stringify(next);
      if (key !== last) { last = key; setRect(next); }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [selector]);
  return rect;
}

// Beside the target if there is room, otherwise below or above it, always on screen.
function place(rect, h) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const w = Math.min(CARD, vw - 32);
  if (!rect) return { left: (vw - w) / 2, top: vh - h - 20, width: w };
  const clampX = (x) => Math.max(16, Math.min(x, vw - w - 16));
  const clampY = (y) => Math.max(16, Math.min(y, vh - h - 16));
  if (rect.left + rect.width + PAD + 16 + w < vw && rect.height < vh / 2) {
    return { left: rect.left + rect.width + PAD + 14, top: clampY(rect.top - 4), width: w };
  }
  if (rect.top + rect.height + PAD + h + 16 < vh) {
    return { left: clampX(rect.left), top: rect.top + rect.height + PAD + 12, width: w };
  }
  return { left: clampX(rect.left), top: clampY(rect.top - PAD - 12 - h), width: w };
}

export default function Tour({ d, step, onStep, onClose, onBackToStart }) {
  const s = STEPS[step];
  const last = step === STEPS.length - 1;
  const selector = typeof s.target === 'function' ? s.target(d) : s.target;
  const rect = useRect(selector);
  const next = () => (last ? onClose() : onStep(step + 1));
  // Back from the first step returns to the welcome popup, so Back always does something.
  const back = () => (step === 0 ? onBackToStart() : onStep(step - 1));

  // For click steps, the visitor's own click on the spotlit element moves the tour on.
  useEffect(() => {
    if (!s.click) return undefined;
    const on = (e) => {
      const el = document.querySelector(selector);
      if (el && el.contains(e.target)) setTimeout(next, 0);
    };
    document.addEventListener('click', on, true);
    return () => document.removeEventListener('click', on, true);
  });

  // The card's real height, so a step with more text is still placed clear of its target.
  const card = useRef(null);
  const [h, setH] = useState(200);
  useLayoutEffect(() => { if (card.current && card.current.offsetHeight !== h) setH(card.current.offsetHeight); });
  const pos = place(rect, h);
  // Phones pin the card to the bottom edge; when the spotlit element is in the
  // lower half it moves to the top so it never covers what it describes.
  const low = rect && rect.top + rect.height / 2 > window.innerHeight / 2;
  return (
    <>
      {rect && (
        <div className={`spot ${s.click ? 'pulse' : ''}`} aria-hidden="true" style={{
          top: rect.top - PAD, left: rect.left - PAD, width: rect.width + PAD * 2, height: rect.height + PAD * 2,
        }} />
      )}
      <div className={`tour ${low ? 'low' : ''}`} ref={card} role="dialog" aria-label="Guided tour" aria-live="polite" style={pos}>
        <div className="tour-head">
          <span className="tour-n">{step + 1} of {STEPS.length}</span>
        </div>
        <b>{s.title}</b>
        <p>{s.body}</p>
        <div className="tour-dots" aria-hidden="true">
          {STEPS.map((_, i) => <i key={i} className={i === step ? 'on' : ''} />)}
        </div>
        <div className="tour-acts">
          <button className="link-btn" onClick={onClose}>Skip</button>
          <span className="grow" />
          <button className="btn sm" onClick={back}>Back</button>
          <button className="btn sm primary" onClick={next}>{last ? 'Finish' : 'Next'}</button>
        </div>
      </div>
    </>
  );
}
