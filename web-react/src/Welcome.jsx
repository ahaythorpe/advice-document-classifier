import { useEffect, useRef } from 'react';
import { Icon } from './atoms.jsx';

// First-visit popup: what the demo is, how it works, and what it is not.
const HOW = [
  ['Read', 'pulls the text from each document'],
  ['Identify', 'works out the type, client and advice event'],
  ['Check', 'raises compliance flags'],
  ['Propose', 'suggests a folder and file name'],
  ['Ask a person', 'nothing is filed until someone approves'],
];

const NOT = [
  ['No client data.', 'The main sample folder is made up, down to the licence numbers. The second set is PDFs their issuers publish: ASIC examples, blank templates and fund PDSs. Results only; the PDFs are not hosted.'],
  ['Nothing is uploaded or saved.', 'There is no upload control, and your clicks stay in this browser tab.'],
  ['Not financial advice.', 'The tool describes documents that already exist. It never writes or recommends advice.'],
  ['Not legal advice.', 'Its rules are mapped to the Corporations Act and ASIC guidance, and still need professional sign-off.'],
  ['Real firms run it locally.', 'As a desktop app on their own computers, so client files never leave the firm.'],
];

export default function Welcome({ onTour, onClose }) {
  const first = useRef(null);
  useEffect(() => { if (first.current) first.current.focus(); }, []);
  return (
    <div className="scrim" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="welcome" role="dialog" aria-modal="true" aria-labelledby="welcome-title">
        <button className="ibtn welcome-x" title="Close" onClick={onClose}><Icon id="x" /></button>
        <span className="demo-tag">Demo only</span>
        <h2 id="welcome-title">Advice Document Filing</h2>
        <p className="welcome-lede">A tool that reads a financial-advice firm’s client documents,
          works out what each one is, and proposes where to file it. A person approves every suggestion.</p>

        <h4>How it works</h4>
        <ol className="welcome-how">
          {HOW.map(([k, v], i) => <li key={k}><i>{i + 1}</i><span><b>{k}</b> {v}</span></li>)}
        </ol>

        <h4>Before you look around</h4>
        <ul className="welcome-not">
          {NOT.map(([k, v]) => <li key={k}><Icon id="shield" /><span><b>{k}</b> {v}</span></li>)}
        </ul>

        <div className="welcome-acts">
          <button className="btn" onClick={onClose}>Explore on my own</button>
          <button ref={first} className="btn primary" onClick={onTour}><Icon id="play" />Take the 1-minute tour</button>
        </div>
      </div>
    </div>
  );
}
