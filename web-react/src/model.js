// Pure helpers over the pipeline payload. No UI here.

export const DATA = window.DATA;
export const PROFILES = Object.keys(DATA);

// green = confident, amber = needs review or a finding, red = high-severity finding
export function statusOf(x) {
  if (x.flags.some((f) => f.severity === 'high')) return 'bad';
  if (x.needs_review || x.flags.length) return 'warn';
  return 'ok';
}

export function statusLabel(x) {
  if (x.needs_review) return 'Needs review';
  if (x.flags.some((f) => f.severity === 'high')) return 'High finding';
  if (x.flags.length) return 'Finding';
  return 'Confident';
}

export const cls = (s) => (s === 'ok' ? '' : s);
export const pct = (c) => Math.round(c * 100);
export const dotColor = (s) => (s === 'bad' ? 'var(--bad)' : s === 'warn' ? 'var(--warn)' : 'var(--ok)');
export const initials = (n) => (n || '?').split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
export const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

const ACRONYM = /^(atp|soa|roa|fsg|pds|afca)$/;
export const flagTitle = (id) =>
  id.split('_').map((w, i) => (ACRONYM.test(w) ? w.toUpperCase() : i ? w : w[0].toUpperCase() + w.slice(1))).join(' ');

export const FILTERS = [
  { key: 'all', label: 'All', test: () => true },
  { key: 'ok', label: 'Confident', test: (x) => statusOf(x) === 'ok' },
  { key: 'review', label: 'Needs review', test: (x) => x.needs_review },
  { key: 'findings', label: 'Findings', test: (x) => x.flags.length > 0 },
];

export function groupByEvent(d, keep) {
  const byEvent = {};
  const loose = [];
  d.documents.filter(keep).forEach((x) =>
    x.event_id ? (byEvent[x.event_id] = byEvent[x.event_id] || []).push(x) : loose.push(x));
  const groups = d.events
    .map((ev) => ({ ev, docs: byEvent[ev.event_id] || [] }))
    .filter((g) => g.docs.length);
  return { groups, loose };
}

export function folderTree(d) {
  const root = { dirs: {}, files: [] };
  d.documents.forEach((x) => {
    let n = root;
    ((x.destination || {}).folder || []).forEach((p) => {
      n = n.dirs[p] = n.dirs[p] || { dirs: {}, files: [] };
    });
    n.files.push(x);
  });
  return root;
}

export const countFiles = (n) => n.files.length + Object.values(n.dirs).reduce((a, c) => a + countFiles(c), 0);
export const highFindings = (d) => d.documents.reduce((n, x) => n + x.flags.filter((f) => f.severity === 'high').length, 0);
