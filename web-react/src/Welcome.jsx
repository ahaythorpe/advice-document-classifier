import { useEffect, useRef } from 'react';
import { Icon } from './atoms.jsx';

// First-visit popup: what the demo is, how it works, and what it is not.
const HOW = [
  ['Read', 'pulls the text from each document'],
  ['Identify', 'works out the type, client and advice event'],
  ['Check', 'raises compliance flags'],
  ['Propose', 'suggests a folder: the client then the advice event'],
  ['File', 'the confident ones in one click and the rest by a person'],
  ['Log', 'every filing is recorded and can be undone'],
];

const NOT = [
  ['No client data.', 'The demo folder is made up to protect privacy, down to the licence numbers. The second set is PDFs their issuers publish: ASIC examples, blank templates and fund PDSs. You see what the tool decided about each one. The PDFs themselves are not on this website.'],
  ['Nothing is uploaded or saved.', 'There is no upload control. Your clicks stay in this browser tab.'],
  ['Not financial advice.', 'The tool describes documents that already exist. It never writes or recommends advice.'],
  ['Not legal advice.', 'Its rules are mapped to the Corporations Act and ASIC guidance. They still need professional sign-off.'],
  ['A prototype.', 'This is an early demo to show the idea. It is not a finished product.'],
];

export default function Welcome({ onTour, onClose }) {
  const first = useRef(null);
  useEffect(() => { if (first.current) first.current.focus(); }, []);
  return (
    <div className="scrim" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="welcome" role="dialog" aria-modal="true" aria-labelledby="welcome-title">
        <span className="demo-tag">Demo only</span>
        <h2 id="welcome-title">Advice Document Filing</h2>
        <p className="welcome-lede">A tool that reads a financial-advice firm’s client documents,
          works out what each one is and proposes where to file it. A person approves every suggestion.</p>

        <h4>How it works</h4>
        <ol className="welcome-how">
          {HOW.map(([k, v], i) => <li key={k}><i>{i + 1}</i><span><b>{k}</b> {v}</span></li>)}
        </ol>

        <h4>Before you look around</h4>
        <ul className="welcome-not">
          {NOT.map(([k, v]) => <li key={k}><Icon id="shield" /><span><b>{k}</b> {v}</span></li>)}
        </ul>

        {/* Same three buttons as every tour step. Back has nowhere to go on the first popup. */}
        <div className="welcome-acts">
          <button className="link-btn" onClick={onClose}>Skip</button>
          <span className="grow" />
          <button className="btn sm" disabled>Back</button>
          <button ref={first} className="btn sm primary" onClick={onTour}>Next</button>
        </div>
      </div>
    </div>
  );
}
