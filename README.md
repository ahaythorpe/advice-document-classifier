# Advice Document Classifier & Filing System

Classifies and files financial-advice documents for Australian advice firms.

Someone at an advice firm drops a messy client folder of PDFs into the tool. For
each document it reads the text, decides what it is (SOA, ROA, FSG, fact find,
ATP, PDS…), works out which client and which *advice event* it belongs to, and
proposes where to file it and what to rename it — or refuses, and says why.

It never files silently. The tool proposes; a human approves, edits or rejects.

> **Status:** Phase 1 — local, human-in-the-loop, pre-pilot. Build step 3 of 7.
> **Not legal advice.** The knowledge base maps documents to provisions to drive
> classification. The AFSL boundary and liability terms need a financial-services
> lawyer's sign-off before this is sold to anyone.

---

## Quick start

Click around the demo — no dependencies, no setup:

```bash
python3 -m advicefiler.ui --demo        # opens http://127.0.0.1:8765/
```

Ten synthetic documents, including an illegible scan and an authority to proceed
with no advice record behind it, so the flags and the review queue have something
to show. Local only: it binds to `127.0.0.1`, reads files from this machine, and
uploads nothing. See `docs/DEPLOYMENT.md` for why this is a desktop tool rather
than a hosted one.

The same pipeline on the command line:

```bash
python3 harness.py                      # ten sample documents, full pipeline
python3 harness.py --display new        # with the teaching layer switched on
python3 harness.py --calibrate          # sweep the confidence threshold
python3 -m unittest discover -s tests   # 72 regression tests
```

To read real PDFs and Word files:

```bash
python3 -m pip install -r requirements.txt
python3 harness.py --input input/smith-family \
                   --ground-truth input/ground_truth.json
```

## What it produces

```
==============================================================================
ADVICE EVENTS (2)
==============================================================================
Nguyen — 2024-03-14 [SOA]
   subject: Retirement & Super Consolidation
   anchor : scan_004.pdf
   + scan_002.pdf   FactFind    (0.98) nearest advice event on or after it (12 days)
   + scan_003.pdf   RiskProfile (0.98) nearest advice event on or after it (12 days)
   + scan_005.pdf   ATP         (0.95) explicitly cites the SOA dated 2024-03-14
   + scan_006.pdf   PDS         (0.85) names AwesomeSuper, which this event's
                                       advice record recommends

[Nguyen]
   +- [2024-03 — Retirement & Super Consolidation [SOA]]
   |     - 2024-03-02 - Nguyen - RiskProfile.pdf
   |         !! risk_mismatch: assessed the client as 'balanced', but that
   |            category does not appear in the SOA it feeds (scan_004.pdf)

!! atp_without_advice_record  scan_009.pdf   [high / BLOCKS FILING]
     authorises implementation of advice that is not in this batch:
     client Patel has no advice event on file
```

## The design in four ideas

**Four steps.** Extract text → classify against the knowledge base → place into a
client and an advice event → file or flag.

**Two filing axes that cross-check each other.** Client outer, advice event
inner. This is not an organisational preference, it is the error detection: a
document that names a client but cites an advice event that does not exist is a
*disagreement between the axes*, and that disagreement is the flag. Single-axis
filing would have misplaced it silently.

**The advice process is the backbone.** Every document maps to a stage
(engagement → discovery → construction → delivery → implementation → ongoing
review) and links to specific other documents. That drives the teaching layer and
lets the tool reason about order: a fact find dated *after* the SOA it feeds, or
an authorisation with no advice record behind it, is a sequence violation. The
stages produce flags for a human, never automatic rejection — real advice loops
and revises.

**Two kinds of flag, and they are not the same.** A *placement* flag means the
tool cannot confidently place the document, so it goes to `_Needs review` and
nothing is filed. A *compliance* flag means the document files correctly and
carries a finding a human should see. Conflating them fills the review queue with
documents that are behaving perfectly, and a queue nobody trusts is the same as
no queue.

## Fixes go in the knowledge base, not in Python

`knowledge_base.json` is the single source of truth: teaching text, classifier
signals, scoring weights, flag rules, filing model, naming patterns. Nothing in
`advicefiler/` hardcodes a document type, a weight or a threshold.

This is load-bearing, for two reasons.

**Build step 4 swaps the keyword matcher for an LLM reading the same
`classifier_hints`.** A fix made in Python scoring evaporates at that point. A fix
made in the knowledge base is inherited, because the LLM reads the same entries.
So the SOA/ATP lookalike was fixed by adding *title-position* and
*reference-context* rules to the knowledge base — "an ATP that says `the
recommendations in the Statement of Advice dated 14 March 2024` **mentions** that
title, it does not **wear** it" — rather than by special-casing it in code.

**The law moves.** Under DBFO Tranche 2 the SOA is slated to be replaced by a
Client Advice Record. `car` already exists in the knowledge base sharing
`advice_record_role: true` with `soa`, and the pipeline finds advice records by
that role, never by the literal id. There is a test that adds a CAR and asserts it
anchors an advice event with no code change.

## Fitting into a firm's existing filing system

No firm will adopt this tool's folder scheme — they already run Xplan,
AdviserLogic, Practifi, Virtual Cabinet, FYI, SharePoint or a folder convention
nobody is allowed to change. So the destination is an adapter and the layout is
configuration. Three ways in, in increasing order of trust required:

```bash
# A. take the manifest — no write access at all
python3 harness.py --input input/smith --export-manifest out/manifest.json \
                                       --export-csv out/plan.csv

# B. take a reviewable script, run it through a channel IT already trusts
python3 harness.py --input input/smith --export-script out/file-them.ps1 \
    --script-shell powershell --dest-root "D:\\Clients"

# C. let the tool file: propose, a human approves, then commit
python3 harness.py --input input/smith --emit-approvals out/approvals.json
python3 harness.py --input input/smith --approved out/approvals.json \
    --dest-root "/Volumes/Advice/Clients" --commit \
    --backup-root ~/OneDrive/AdviceBackup --backup-region ap-southeast-2
```

**Desktop primary, cloud backup.** The working copy lives where advisers work
and the practice-management system indexes. Cloud is a second copy, mirrored
after the primary succeeds and hash-verified after writing — a backup nobody has
verified is a belief, not a backup. OneDrive, SharePoint, Teams, Dropbox and
Google Drive all appear as ordinary sync folders on an adviser's machine, so the
local adapter reaches them with no API and no integration project.
`--backup-root` requires `--backup-region` and refuses non-Australian regions
unless overridden explicitly.

**Filing profiles** (`--list-profiles`) own the folder layout, filename pattern,
document vocabulary, character set and path limits. `nested-default`,
`category-flat` (how most practice-management systems organise a client file),
`sharepoint-safe` (ASCII, short paths), `preserve-original`. Switching profile
changes the paths and nothing else — advice events are still computed and still
carried in the manifest even under a scheme with no folder for them.

Nothing is written without `--commit`, and nothing is written for a document the
approvals file does not approve. Documents queued for review default to
`reject`, so the safe outcome is the one you get by doing nothing. Re-running is
idempotent: filing is keyed on a content hash, so the same batch applied twice
does not produce two copies. See `docs/INTEGRATION.md`.

## Landing in the right client folder

Reading a name off a document is half the job. A firm with 800 client folders
needs the document to land in the *existing* one — not in an 801st, spelled
slightly differently. That failure is silent: `Nguyen` beside an existing
`Nguyen, Linh & David` raises no error and loses no file, and someone finds out
years later during a compliance review.

```bash
python3 harness.py --input input/smith --clients "/Volumes/Advice/Clients"
python3 harness.py --input input/smith --clients clients.csv \
    --emit-new-clients out/new-clients.json
```

The register comes from a practice-management export (CSV or JSON) or from the
destination itself — the firm's existing folder tree is the most accurate client
list they have, and needs no export and no IT ticket. Matching handles both
`Nguyen, Linh & David` and `Linh & David Nguyen` conventions, uses given names to
separate two households sharing a surname, and survives OCR damage and lost
diacritics. Where it cannot decide, it says so: `client_ambiguous_match` blocks
filing, and `new_client_proposed` asks once per client rather than once per
document.

Deliberately **not** an LLM. Client identity must resolve the same way every time
and a reviewer must be able to see why. Where the model earns its place is
upstream at step 4 — pulling an identity out of a document that never states one
plainly — and whatever it extracts still comes through this matcher.

Without `--clients`, matching is off and the name read from the document is used
as-is, so a first run against an unknown firm still works.

## Reorganising what is already filed

Most firms' real problem is the decade already filed, by six people, to four
conventions.

```bash
python3 harness.py --reorganise "/Volumes/Advice/Clients"          # what would change
python3 harness.py --reorganise "/Volumes/Advice/Clients" \
    --approved out/reorg.json --commit                             # move it
python3 harness.py --undo ".../_advicefiler/rollback-*.json" --commit
```

It reads the tree recursively, uses that tree's own client folders as the
register, and moves rather than copies. Three rules make it safe to point at a
live client file: a document already in the right place is not touched; a
document that cannot be confidently placed is **left exactly where it is**,
never swept into `_Needs review`; and every move is written to a rollback file
before it happens. Moves that change which client a document sits under are
listed first — if the classifier is wrong, the document leaves the file it
belongs to *and* contaminates one it does not.

## Security

No network calls at all — `advicefiler/` imports nothing that opens a socket, and
there is a test asserting it. Client text cannot leave the machine by accident.
(That changes at step 4, and is a decision for the licensee, not a library
upgrade.)

`--redact` replaces client names and paths with stable, non-reversible
pseudonyms while keeping types, confidences, flags and event structure — enough
to debug a classification or show a vendor the integration, with no way to say
whose file it was. Filed documents, audit log, state and register are owner-only.
Every filed document is recorded with its SHA-256, which answers the question a
compliance reviewer actually asks. Encryption at rest is deliberately left to the
volume; see `docs/SECURITY.md` for why.

## Real documents and client data

Real advice files contain client PII: names, assets and liabilities, income,
dependants, and health disclosures where insurance advice is involved.

* Drop real documents in `input/`. It is git-ignored, as is `output/`, and
  `.gitignore` additionally excludes `*.pdf`, `*.docx` and the failure log
  anywhere in the tree.
* Ground truth for real documents goes in `input/ground_truth.json`, **not** in
  the repo's `ground_truth.json` — it would carry client names into git history.
* Nothing leaves this machine. Cloud hosting and Australian data residency are
  deferred to pilot stage.

## Accuracy, honestly

Against the 10 synthetic samples and a 5-document real-file batch, the current
build scores 100% on type, client, event and review decision, with zero
confident-and-wrong answers.

**That number is not evidence of much.** Fifteen documents, most of them written
to exercise the pipeline, is a test that the apparatus works — not a measurement
of the classifier. The calibration sweep says so itself: it refuses to recommend
a threshold, because a sample containing no confidently-wrong answers at *any*
threshold cannot calibrate one. Real documents are what make these numbers mean
something, and that is exactly what build step 3 is for.

The metric that decides the threshold is **confident and wrong**. A wrong answer
at high confidence is worse than an honest "not sure", so the threshold is raised
until that column is empty and the review queue is whatever size that costs.

## Layout

```
SYSTEM.md              the living spec
knowledge_base.json    domain source of truth (v0.4)
harness.py             CLI entry point
ground_truth.json      labelled correct answers for the samples
sample_documents.json  ten synthetic documents, clean and broken
advicefiler/
  kb.py                knowledge-base access; nothing else reads the JSON
  extract.py           PDF/DOCX/text -> text, with scan-quality scoring
  classify.py          Classifier interface + the Phase 1 keyword engine
  entities.py          clients, dates, risk categories, product names
  events.py            advice-event grouping
  flags.py             the edge-case rules engine
  profiles.py          firm filing schemes (folder layout, vocabulary, limits)
  clients.py           matching a document to the firm's existing client
  security.py          redaction, file hygiene, audit digests
  ui.py                local review UI (build step 5, first cut)
  storage.py           the folder plan (data only — nothing is written)
  integrate.py         manifest/CSV/script export, approvals, destinations
  evaluate.py          ground truth, failure log, confidence calibration
  report.py            console output, both display modes
profiles/              four filing schemes; copy one to match a firm
docs/
  ROADMAP.md           the build plan: what gates each step, where the risk is
  DEPLOYMENT.md        desktop vs hosted, and why it matters here
  ARCHITECTURE.md      how the pieces fit and why
  INTEGRATION.md       connecting to a firm's existing filing system
  SECURITY.md          what is protected, how, and what is deliberately not done
  STEP3-RUNBOOK.md     putting real documents through, and what to do with misses
legacy/harness_v0.py   the keyword prototype, kept for before/after comparison
tests/                 72 regression tests, one per bug v0 actually made
```

## Build sequence

1. ✅ Knowledge base — the domain source of truth (now v0.4)
2. ✅ Test harness — classify + group + folder tree + flags + failure log
3. 🔨 **Real documents through the harness; fix failures; calibrate confidence**
4. ⬜ Swap the keyword matcher for the LLM classifier (same hints)
5. 🔨 Approve / edit / reject UI — local web UI works; desktop packaging next
6. ⬜ Move storage to Australian-region cloud (only when a pilot needs it)
7. ⬜ AI summary per advice event (only when grouping is trusted)

Deferred to pilot stage: cloud hosting and data residency, multi-tenant
isolation, audit logging, penetration test, PI/cyber insurance, and a lawyer's
sign-off on the AFSL boundary. None are build-blockers today; all are
sell-to-industry requirements before a firm's real data is involved.
