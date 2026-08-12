# Build plan

SYSTEM.md section 9 has the sequence. This is how to actually walk it: what
gates each step, what must not be built early, and where the real risk sits.

## Where we are

Steps 1 and 2 are done. Step 3's *apparatus* is done — extraction, ground truth,
failure log, calibration, and the integration layer that lets a firm hand us
documents without handing us their filing system. Step 3 itself is not done,
because it needs documents we do not have.

Everything measured so far scores 100%. That number is worth nothing yet: fifteen
mostly-synthetic documents, and the calibration sweep refuses to recommend a
threshold precisely because the sample contains no confidently-wrong answers to
calibrate against.

---

## The critical path

```
  3. real documents ──► 4. LLM classifier ──► 5. UI ──► 6. cloud ──► 7. summaries
        │                      │                 │
        └── needs a firm ──────┘                 └── needs 3+4 trusted
```

Everything downstream is gated on step 3, and step 3 is gated on getting real
files. That is the single constraint that matters; nothing else on this page
moves until it does.

---

## Step 3 — real documents (now)

**The one thing to do next: get one real client folder.** Not a curated set — a
messy one, ideally an old one. Route A in `docs/INTEGRATION.md` needs no write
access, no IT approval and no credentials, so it is the version of this a firm
can say yes to: we read, we propose, they compare against where the documents
actually are.

While waiting, build the **adversarial corpus** — deliberately hard synthetic
documents covering what the runbook prioritises: SOA/ATP bundles, degraded
scans, fact finds dated after their SOA, the four ROA kinds, two SOAs competing
for "current", pre/post-DBFO fee documents, undated documents, couples with two
surnames where one document names one partner. This is a bridge, not a
substitute: it will surface bugs, and it may produce the confidently-wrong
answers calibration needs, but a corpus written by the person fixing the
classifier tests what they thought of.

**Exit gate.** Several real client folders through. The failure log shows misses
being fixed and staying fixed. The threshold was chosen from data containing real
errors rather than defaulted. Every fix that could go in the knowledge base did —
that last one is what makes step 4 a swap rather than a rewrite.

## Step 4 — the LLM classifier

`Classifier` is already the seam; `KeywordClassifier` is one implementation and
`LLMClassifier` is the other. It reads the same `classifier_hints`, which is why
step 3's fixes carry over.

Three things this must get right:

**Return the same shape, including refusal.** Type, confidence, and `None` when
it does not know. An LLM that always answers is worse than the keyword matcher,
which at least scores zero on garbage.

**Traceability.** The classification should carry the span of text it relied on.
This is cheap here and load-bearing at step 7, where hallucination is the named
failure mode — a summary must be checkable against source text, and the habit
starts now.

**Calibration, separately.** LLM-stated confidence is not a probability. Map it
to observed accuracy against the same ground truth, then apply the same
threshold discipline. Do not assume the keyword threshold transfers.

**Migration safety net, which the harness already supports:** run both engines
over the same corpus with the same ground truth and diff. Ship when the LLM wins
on type and event accuracy *and* introduces no confident-wrong answer the keyword
version did not have. Keep the keyword engine — it is the offline fallback, and
the thing that tells you when a model update has silently regressed.

Practical: cache by `doc_id` (content hash), batch, and expect per-document cost
to matter at a firm with a decade of files.

## Step 5 — approve / edit / reject

**The data model already exists.** `advicefiler/approvals@1` is the decision
sheet: approve, reject, or correct the folder and filename. The UI is a view over
that file, so this step is genuinely a UI step and not a redesign.

Local web app on localhost — no cloud, no accounts, nothing leaves the machine.
Bulk-approve **by advice event**, not by document: an adviser judges "is this the
March super advice and everything behind it" once, not six times. Both display
modes live here (SYSTEM.md section 2), and the teaching layer already renders.

**Exit gate:** an adviser clears a real batch faster than filing it by hand. If
not, the review queue is too big and the answer is back in step 3, not in the UI.

## Integration hardening (alongside 4 and 5)

Ordered by what a pilot actually hits:

1. **`SourceAdapter`** — read *from* a DMS, mirroring `DestinationAdapter`. Input
   is a folder today.
2. **One vendor adapter**, chosen by whichever firm pilots. The contract is
   defined and exercised by the local implementation.
3. **Incremental runs** — watch a folder, process what is new. Content hashing
   already makes this safe.
4. **Two-way reconciliation** — compare where documents ended up against the
   manifest, so drift surfaces.

## Step 6 — cloud, only when a pilot needs it

Australian region, tenant isolation, audit logging, penetration test. The
residency guard in `integrate.py` is the shape of the constraint, not a
substitute for it: a real cloud destination needs the licensee's sign-off, a data
processing agreement, and a documented location.

Do not start this to have it. Start it when a named firm cannot pilot without it.

## Step 7 — the AI summary per advice event

The knowledge base states its own precondition: *"Do not build this until
classification and grouping are reliable. A summary built on mis-grouped
documents is confidently wrong."*

When it is time: summarise the event, never the loose document. Describe existing
documents only — generating, altering or recommending advice would cross into
providing financial advice and change the whole regulatory posture. Every
sentence traceable to source text. Drafts a human checks.

---

## Commercial gates — parallel, not sequential

None of these are build-blockers today. All of them block a firm's real data.

* **Lawyer on the AFSL boundary and liability terms.** The longest lead time and
  the one that can invalidate the product's positioning. Start it before step 6,
  not after.
* **PI and cyber insurance.**
* **Penetration test** — before any hosted version, not after.
* **Licensee sign-off** at the pilot firm. The adviser is not the decision-maker.

## Where the risk actually is

**Event grouping is the fragile part, and everything expensive depends on it.**
The knowledge base calls it the fiddliest part of the system; SYSTEM.md calls
mis-grouping the most likely early failure; the v0 harness proved both by filing
March inputs under September advice. Step 7 is built directly on top of it.

If real documents show grouping holding up, the rest is execution. If they show
it breaking in ways the links cannot resolve, that is worth knowing before an LLM
bill and a UI are built on the assumption — which is exactly why step 3 comes
before step 4, and why it is worth being slow about.

**Second risk: the review queue.** A queue too large to read is the same as no
queue, and a queue full of documents that were filed correctly teaches reviewers
to stop reading it. That is what the placement/compliance flag split is for, and
it needs testing on real volumes, not ten samples.
