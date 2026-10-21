import { useEffect, useRef } from 'react';
import { Icon } from './atoms.jsx';
import { plural } from './model.js';

// After a batch approval: what would be filed where, and what really happened (nothing).
export default function Filed({ docs, onUndo, onLog, onClose }) {
  const done = useRef(null);
  useEffect(() => { if (done.current) done.current.focus(); }, []);
  const byFolder = {};
  docs.forEach((x) => {
    const dst = x.destination;
    const k = dst.folder.join(' / ');
    (byFolder[k] = byFolder[k] || []).push(dst.filename);
  });
  return (
    <div className="scrim" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="welcome filed" role="dialog" aria-modal="true" aria-labelledby="filed-title">
        <span className="demo-tag">Simulated</span>
        <h2 id="filed-title">{plural(docs.length, 'document', 'documents')} filed</h2>
        <p className="welcome-lede">One approval, then each one renamed and moved into the client’s folder. The filing log keeps a record of this batch and why each document went where it did.</p>
        <div className="filed-list">
          {Object.keys(byFolder).sort().map((k) => (
            <div key={k}><div className="filed-dir"><Icon id="folder" />{k}</div>
              <ul>{byFolder[k].map((f) => <li key={f}><Icon id="check" />{f}</li>)}</ul></div>
          ))}
        </div>
        <ul className="welcome-not">
          <li><Icon id="lock" /><span><b>As designed</b> this step would move each file into the firm’s own
            folders on its own computer, renamed as shown. Nothing would leave that computer.</span></li>
          <li><Icon id="shield" /><span><b>In this demo</b> nothing is written anywhere. It lives in this browser tab
            and is gone when you close it.</span></li>
        </ul>
        <div className="welcome-acts">
          <button className="link-btn" onClick={onUndo}>Undo</button>
          <span className="grow" />
          <button className="btn sm" onClick={onLog}>See the filing log</button>
          <button ref={done} className="btn sm primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}
