import { statusOf, statusLabel, cls, pct, dotColor, flagTitle, SEVERITY } from './model.js';

export const Icon = ({ id }) => (
  <svg className="i"><use href={`#i-${id}`} /></svg>
);

export const Dot = ({ s }) => <i className={`dot ${cls(s || 'ok')}`} />;

export const FileIcon = ({ doc }) => (
  <span className="fic">
    <svg><use href="#doc" /></svg>
    <span className="d" style={{ background: dotColor(statusOf(doc)) }} />
  </span>
);

// The tick on the bar is the firm's threshold: below it the tool will not file.
export const Confidence = ({ doc, threshold }) => {
  const low = threshold != null && doc.confidence < threshold;
  return (
    <span className="conf" title={`Confidence ${doc.confidence.toFixed(2)}${threshold != null ? `, threshold ${threshold}` : ''}`}>
      <span className={`bar ${low ? 'low' : ''}`}><i style={{ width: `${pct(doc.confidence)}%` }} />
        {threshold != null && <b className="tick" style={{ left: `${pct(threshold)}%` }} />}</span>
      <em>{pct(doc.confidence)}%</em>
    </span>
  );
};

export const StatusBadge = ({ doc }) => (
  <span className={`badge ${cls(statusOf(doc))}`}><i className="dot" />{statusLabel(doc)}</span>
);

export const Type = ({ children }) => <span className="type">{children}</span>;

export const Finding = ({ f }) => (
  <div className={`note ${f.severity === 'high' ? 'high' : ''}`}>
    <div className="nh"><span className="sev">{SEVERITY[f.severity] || f.severity}</span><span>{flagTitle(f.id)}</span></div>
    {f.message}<em> ({f.blocks_filing ? 'held until checked' : 'can still be filed'})</em>
  </div>
);
