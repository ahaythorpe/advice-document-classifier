import { Icon } from './atoms.jsx';

// A short guided walk through the demo. Each step opens a view, and may select a
// document so the inspector has something to explain.
export const STEPS = [
  {
    view: 'overview',
    title: 'A messy client folder',
    body: 'Ten fabricated documents, scanned and named scan_001 to scan_010, the way they often arrive. The tool has read every one and worked out what it is.',
  },
  {
    view: 'events',
    title: 'Grouped by advice event',
    body: 'Documents are grouped by client and by the piece of advice they belong to: the fact find, risk profile, SOA and authority to proceed for one recommendation sit together.',
    select: (d) => d.documents.find((x) => x.type_label === 'SOA'),
  },
  {
    view: 'events',
    title: 'Why it was placed there',
    body: 'The panel on the right shows the reasoning: the type, how confident the tool is, the words it found, and where it proposes to file it. Nothing is filed until a person presses Approve.',
    select: (d) => d.documents.find((x) => x.type_label === 'SOA'),
  },
  {
    view: 'review',
    title: 'It refuses rather than guesses',
    body: 'When the tool is not sure, it holds the document for a person and says why. A wrongly filed client record is a compliance problem, so the bar is certainty.',
  },
  {
    view: 'tree',
    title: 'Fits the firm’s own system',
    body: 'This is the proposed filing. Change the Filing scheme at the top right to match how a firm already organises its files: only the folders change, never the classification.',
  },
  {
    view: 'about',
    title: 'Why I built this',
    body: 'The short version is on this page: big advice software is clunky and expensive, and none of it reads a document for you. That is the gap this fills.',
  },
];

export default function Tour({ step, onStep, onClose }) {
  const s = STEPS[step];
  const last = step === STEPS.length - 1;
  return (
    <div className="tour" role="dialog" aria-label="Guided tour" aria-live="polite">
      <div className="tour-head">
        <span className="tour-n">{step + 1} of {STEPS.length}</span>
        <span className="grow" />
        <button className="ibtn" title="Close tour" onClick={onClose}><Icon id="x" /></button>
      </div>
      <b>{s.title}</b>
      <p>{s.body}</p>
      <div className="tour-dots" aria-hidden="true">
        {STEPS.map((_, i) => <i key={i} className={i === step ? 'on' : ''} />)}
      </div>
      <div className="tour-acts">
        <button className="btn sm" disabled={step === 0} onClick={() => onStep(step - 1)}>Back</button>
        <button className="btn sm primary" onClick={() => (last ? onClose() : onStep(step + 1))}>{last ? 'Finish' : 'Next'}</button>
      </div>
    </div>
  );
}
