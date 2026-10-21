// Pure helpers over the pipeline payload. No UI here.

// { dataset: { profile: manifest } }. The demo set is always present and first.
export const DATASETS = window.DATA;
export const SETS = Object.keys(DATASETS);
export const PROFILES = Object.keys(DATASETS[SETS[0]]);

// Every document is in exactly one group, so the counts agree on every screen.
// Held by the tool (amber), not held but something to check (red), or confident (green).
export function statusOf(x) {
  if (x.needs_review) return 'warn';
  if (x.flags.length) return 'bad';
  return 'ok';
}

export function statusLabel(x) {
  return { warn: 'Needs review', bad: 'Worth checking', ok: 'Confident' }[statusOf(x)];
}

export const cls = (s) => (s === 'ok' ? '' : s);
export const pct = (c) => Math.round(c * 100);
export const dotColor = (s) => (s === 'bad' ? 'var(--bad)' : s === 'warn' ? 'var(--warn)' : 'var(--ok)');
export const initials = (n) => (n || '?').split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
export const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

const ACRONYM = /^(atp|soa|roa|fsg|pds|afca)$/;
// Plain words for severity: these are prompts for a person, not verdicts.
export const SEVERITY = { high: 'Important', medium: 'Check', low: 'Note' };

export const flagTitle = (id) =>
  id.split('_').map((w, i) => (ACRONYM.test(w) ? w.toUpperCase() : i ? w : w[0].toUpperCase() + w.slice(1))).join(' ');

export const FILTERS = [
  { key: 'all', label: 'All', test: () => true },
  { key: 'review', label: 'Needs review', test: (x) => statusOf(x) === 'warn' },
  { key: 'findings', label: 'Worth checking', test: (x) => statusOf(x) === 'bad' },
  { key: 'ok', label: 'Confident', test: (x) => statusOf(x) === 'ok' },
];

// Most urgent first: what is held, then what to look at, then what is fine.
export const STATUS_ORDER = ['Needs review', 'Worth checking', 'Confident'];

export function groupByStatus(d, keep) {
  const by = {};
  d.documents.filter(keep).forEach((x) => (by[statusLabel(x)] = by[statusLabel(x)] || []).push(x));
  return STATUS_ORDER.filter((k) => by[k]).map((label) => ({ label, docs: by[label] }));
}

// Only these can be approved together: placed, nothing held, nothing to check.
// Anything flagged waits for a person one by one, however confident.
export const batchable = (x) => !x.needs_review && !x.flags.length && !!(x.destination || {}).path;
export const BATCH_LEVELS = [0.7, 0.8, 0.9];   // first is the default

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
