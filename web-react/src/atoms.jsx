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

export const Confidence = ({ doc }) => {
  return (
    <span className="conf" title={`Confidence ${doc.confidence.toFixed(2)}`}>
      <span className="bar"><i style={{ width: `${pct(doc.confidence)}%` }} /></span>
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
