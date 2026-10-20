import { Icon, FileIcon, Confidence, StatusBadge, Type, Finding } from './atoms.jsx';
import { pct, plural } from './model.js';

export default function Inspector({ d, doc, decision, onDecide, onStep, onClose }) {
  if (!doc) {
    return (
      <aside className="insp" aria-label="Document details">
        <div className="insp-empty"><div><Icon id="file" /><div>Select a document to see why it was placed where it was.</div></div></div>
      </aside>
    );
  }
  const list = d.documents;
  const i = list.indexOf(doc);
  const dst = doc.destination || {};
  const ev = d.events.find((e) => e.event_id === doc.event_id);

  return (
    <aside className="insp" aria-label="Document details">
      <div className="insp-head">
        <div className="insp-nav">
          <button className="ibtn" title="Previous" disabled={i <= 0} onClick={() => onStep(-1)}><Icon id="up" /></button>
          <button className="ibtn" title="Next" disabled={i >= list.length - 1} onClick={() => onStep(1)}><Icon id="down" /></button>
          <span>{i + 1} of {list.length}</span><span className="grow" />
          <button className="ibtn" title="Close" onClick={onClose}><Icon id="x" /></button>
        </div>
        <div className="insp-title"><FileIcon doc={doc} />
          <div style={{ minWidth: 0 }}><b>{doc.source_name}</b>
            <div className="tags"><Type>{doc.type_label}</Type><StatusBadge doc={doc} /></div>
          </div>
        </div>
      </div>

      <div className="insp-body">
        <div className="isec"><h4>Classification</h4>
          <dl className="kv">
            <dt>Type</dt><dd>{doc.type_label}{doc.category && <small>{doc.category}</small>}</dd>
            <dt>Confidence</dt><dd><Confidence doc={doc} /></dd>
            <dt>Extraction</dt><dd>{pct(doc.extraction_quality)}% quality · {plural(doc.pages, 'page', 'pages')}</dd>
          </dl>
          {doc.classification_evidence && <div className="evidence" style={{ marginTop: 8 }}>{doc.classification_evidence}</div>}
        </div>

        <div className="isec"><h4>Client and advice event</h4>
          <dl className="kv">
            <dt>Client</dt><dd>{doc.client || 'none'}{doc.client_provenance && <small>{doc.client_provenance}</small>}</dd>
            <dt>Dated</dt><dd>{doc.date || 'undated'}{doc.date_provenance && <small>{doc.date_provenance}</small>}</dd>
            <dt>Event</dt><dd>{ev ? <>{ev.subject} · {ev.record_label}<small>{ev.date || 'undated'}</small></> : 'none'}</dd>
            {doc.attachment_reason && <><dt>Grouped</dt><dd>{doc.attachment_reason}</dd></>}
          </dl>
        </div>

        <div className="isec"><h4>Findings</h4>
          {doc.flags.length
            ? doc.flags.map((f) => <Finding key={f.id} f={f} />)
            : <div className="none"><Icon id="check" />No findings</div>}
        </div>

        <div className="isec"><h4>{doc.needs_review ? 'Held in' : 'Proposed filing'}</h4>
          {dst.path && <span className="path">{dst.path}</span>}
          {dst.rationale && <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--mute)' }}>{dst.rationale}</p>}
        </div>
      </div>

      <div className="insp-foot">
        <div className="acts">
          <button className="btn yes" aria-pressed={decision === 'approve'} onClick={() => onDecide('approve')}><Icon id="check" />Approve</button>
          <button className="btn no" aria-pressed={decision === 'reject'} onClick={() => onDecide('reject')}><Icon id="x" />Reject</button>
        </div>
        <small>{decision ? `${decision === 'approve' ? 'Approved' : 'Rejected'} in this demo only. Nothing is saved.` : 'Nothing is filed until a person decides.'}</small>
      </div>
    </aside>
  );
}
