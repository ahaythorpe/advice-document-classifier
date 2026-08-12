# Advice Document Classifier & Filing System — Living Spec

**Status:** Phase 1 (prototype, local, human-in-the-loop). Pre-pilot. Build step 3 in progress.
**Regime:** Australia — Corporations Act 2001, ASIC. Knowledge base v0.4.
**This is not legal advice.** The AFSL boundary and liability terms need a financial-services lawyer's sign-off before selling.

---

## 1. What it is, in one paragraph

Someone at an advice firm drops a pile of PDFs — a messy client folder — into the tool. For each document it reads the text, decides what it is (SOA, ROA, FSG, fact-find, etc.), proposes where to file it and what to rename it, and either files it cleanly or flags it for a human. It never files silently on low confidence. The tool proposes; a human approves, edits, or rejects.

## 2. Three independent settings (keep them separate)

The system has three knobs that do NOT depend on each other. Keeping them independent is what stops the design tangling later.

1. **Display mode** — how much each card teaches.
   - *New-to-industry:* card explains what the document is, why it exists in law, where it sits in the advice process.
   - *Experienced:* identification, filing suggestion, and flags only.
2. **Filing mode** — how output is arranged on disk. Default and recommended: **client outer, advice-event inner** (see §5).
3. **Classification engine** — the same underneath, regardless of the two settings above.

## 3. How it works — four steps

1. **Extract** text from the document (pypdf/pdfplumber for PDFs, python-docx for Word).
2. **Classify** against the knowledge base `classifier_hints` → returns `type + confidence`.
   (Phase 1 stand-in: keyword matcher. Real: an LLM reading the same hints. Downstream is identical.)
3. **Place** — assign to a client and an advice event; propose folder + filename.
4. **File or flag** — clean placement, or route to `_Needs review` with a reason.

## 4. The advice process is the backbone

Every document maps to a stage of advice (engagement → discovery → construction → delivery → implementation → ongoing review) and links to specific other documents. This does two jobs:

- **Teaching:** shows a new adviser where a document sits in the sequence.
- **Failure-catching:** lets the tool reason about order and completeness. A fact-find dated *after* the SOA it feeds, or an authority-to-proceed with no advice record behind it, is out of sequence → flag. The stages drive *flags for a human*, never automatic rejection (real advice loops and revises).

## 5. Filing model — nested, two axes

```
📁 <Client / family>
   📁 <YYYY-MM — subject> [<record type>]     ← one advice event
        - advice record (SOA/ROA/CAR)
        - inputs (fact find, risk profile)
        - implementation (authority to proceed)
        - supporting product disclosure (PDS)
   📁 _Client-level documents                  ← FSG, general correspondence
   📁 _Needs review ⚠                          ← anything not confidently placed

📁 _Licensee documents                         ← FSG editions, unmatched PDSs
```

- **`_Licensee documents` (added at step 3).** An FSG has no client name because
  it never had one — it is licensee-wide and editioned by effective date. Treating
  that absence as a placement failure fills the review queue with documents that
  are behaving correctly, which teaches a reviewer to ignore the queue. Genuine
  orphans must stay rare enough to be worth reading. Where an intake batch
  resolves to a single client, these may instead inherit that client (recorded as
  inherited, never as read).
- **Two kinds of flag (added at step 3).** A *placement* flag means the document
  cannot be confidently placed: it goes to `_Needs review` and nothing is filed. A
  *compliance* flag means the document files correctly and carries a finding for a
  human — a risk-profile mismatch is placed perfectly and still worth surfacing.
  Conflating the two buries correct work under questions that are not about
  filing. Which class each rule belongs to is a knowledge-base fact.

- **Outer = client.** Matches how firms and reviewers pull files.
- **Inner = advice event.** Groups everything behind one advisory decision, using the document-to-document links. A client accumulates many events over years (super year 1, insurance year 2 …); each is its own folder.
- **Why nesting is more accurate:** a document is placed by two axes that must agree (right client AND a coherent event). Disagreement = a flag a single axis would miss.
- **Shared documents** (e.g. a PDS used in two events): file once, reference elsewhere. Configurable per firm.
- **Always a proposal a human confirms.** Event grouping depends on link accuracy — the fiddliest part — so mis-grouping is expected early and must surface, never auto-bundle.

## 6. AI summary (planned, later phase)

Once classification and grouping are trusted, generate a plain-English **summary per advice event** (not per loose document): what the advice was, the basis, cost and benefits, whether inputs were present and consistent, whether it was authorised, any flags.

**Hard rules:** it describes existing documents — it must never generate, alter, or recommend advice (that would cross into providing financial advice). Summaries are drafts a human checks against the source. LLM hallucination is a serious failure mode here, so summaries must be traceable to source text. Do not build until grouping is reliable.

## 7. Known failure modes (watch for these)

- **Lookalikes:** an ATP that mentions "Statement of Advice" gets misread as an SOA. Fix in the knowledge base by weighting structural signals (signature, "I authorise") over mentioned titles.
- **Bad scans:** crooked/photocopied documents yield garbage text; the tool must score low and flag, not classify confidently.
- **Overconfidence:** a wrong answer at high confidence is worse than an honest "not sure." Confidence must be visible and calibrated against the failure log.
- **Mis-grouping:** wrong advice-event links attach inputs to the wrong event. The most likely early failure; keep it human-confirmed.
- **Stale knowledge base:** when the law changes (DBFO → CAR is live), every entry referencing the old rule is silently wrong until updated. Treat the KB as maintained, dated, and versioned.

## 8. Improvement loop

Keep a **failure log**: input, tool's answer, correct answer, one-line guess at why it missed. Every wrong answer is a specific fix (usually in the knowledge base, sometimes in scoring). This log is also what proves accuracy to a buyer. The test harness produces this log on every run.

## 9. Build sequence

1. ✅ Knowledge base (v0.4) — the domain source of truth.
2. ✅ Test harness — classify + group + folder tree + flags + failure log, on sample docs, local.
3. 🔨 Real documents through the harness; fix failures; calibrate confidence.
   - ✅ Extraction layer (PDF/Word/text) with scan-quality scoring, which the v0 harness never had.
   - ✅ Ground truth, so the failure log has its correct-answer column (§8) and confidence can be calibrated at all.
   - ✅ v0's own failures fixed — the SOA/ATP lookalike, string-sorted dates mis-grouping the events, uncalibrated confidence, orphaned licensee documents. Each has a regression test.
   - ✅ All knowledge-base flag rules implemented; unimplemented rules are now reported in every run rather than being invisible.
   - ⬜ **Real client documents.** Everything above is apparatus. Fifteen synthetic documents cannot calibrate a threshold — the sweep says so itself and refuses to recommend one. See `docs/STEP3-RUNBOOK.md`.
4. Swap keyword matcher for the LLM classifier (same hints).
5. Approve/Edit/Reject UI.
6. Move storage from local folder to Australian-region cloud (only when a pilot needs it).
7. AI summary per event (only when grouping is trusted).

## 10. Deferred to pilot stage (not now)

Cloud hosting + Australian data residency, multi-tenant isolation, audit logging, penetration test, PI/cyber insurance, lawyer sign-off on the AFSL boundary and liability terms. None are build-blockers today; all are sell-to-industry requirements before a firm's real data is involved.
