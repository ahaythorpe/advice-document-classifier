# Build step 3 — real documents through the harness

> *"Real documents through the harness; fix failures; calibrate confidence."*
> — SYSTEM.md, build sequence

Everything below assumes the apparatus is finished, which it now is. What remains
is the part only real documents can do.

## Before the first real file

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests     # should be 38 passing
```

Check the privacy posture holds, because after this point the directory contains
client PII:

```bash
git status --short          # must show nothing from input/ or output/
git check-ignore -v input/anything.pdf
```

## The loop

### 1. One client folder at a time

```bash
mkdir -p input/nguyen-family
cp ~/wherever/*.pdf input/nguyen-family/
python3 harness.py --input input/nguyen-family
```

Batches matter: the tool treats one folder as one *intake batch*, and a batch
that resolves to a single client lets non-client-specific documents (FSG, PDS)
inherit that client. Mixing several clients into one folder throws that away, and
mixing them silently is worse than not having it.

Read the output before labelling anything. The two questions worth asking first:

* **Is anything confidently wrong?** That is the failure the system exists to
  prevent, and it outranks everything else in this list.
* **Is the review queue full of documents that are behaving correctly?** An FSG
  with no client name, a PDS with no client name — those are normal. If they are
  being queued, the fix is a `client_specific` or routing question, not a
  threshold question.

### 2. Label what actually happened

Copy `ground_truth.json` as a template, and put yours in `input/` where git
cannot reach it:

```bash
cp ground_truth.json input/ground_truth.json
$EDITOR input/ground_truth.json
python3 harness.py --input input/nguyen-family \
                   --ground-truth input/ground_truth.json
```

Label from the documents, not from the tool's output. Reading the tool's answer
first and agreeing with it is how ground truth quietly becomes a record of what
the tool does rather than what is true.

Per document: `type`, `client` (family key), `event` (any stable label — only the
grouping it implies is checked), `needs_review`, and `expect_flags`. Compliance
flags belong in `expect_flags` too: a document can be filed correctly and still
carry a finding.

### 3. Read the failure log

Appended to `output/failure_log.jsonl`, one row per miss, with the four columns
SYSTEM.md section 8 asks for: input, tool's answer, correct answer, and a
one-line guess at why.

It appends rather than overwrites, because the improvement loop is a history. The
thing you want to see is a failure appearing in run 4 and never again.

```bash
python3 - <<'PY'
import json, collections
rows = [json.loads(l) for l in open("output/failure_log.jsonl")]
by_run = collections.Counter(r["run_id"] for r in rows)
for run, n in sorted(by_run.items()):
    print(run, n, "misses")
PY
```

### 4. Fix the miss — almost always in the knowledge base

This is the discipline that makes step 3 worth doing before step 4 rather than
after. **Build step 4 replaces the keyword classifier with an LLM reading the same
`classifier_hints`.** A fix made in Python scoring is thrown away at that point. A
fix made in `knowledge_base.json` is inherited, because the LLM reads the same
entries.

So work down this list, and only fall off the end as a last resort:

| Symptom | Fix, in order of preference |
|---|---|
| Two types confused | Add a `structural_signal` unique to the right one; add the wrong one's title to the right one's `reference_patterns` if it is being cited |
| A cited document wins | `reference_patterns` on the cited type — this is the SOA/ATP lookalike |
| Right type, low confidence | Add `structural_signals`. Raising `evidence_floor` is the blunt instrument; more signal is the real fix |
| Wrong client | Extend the label forms in `entities.py` — one of the few genuinely mechanical bits |
| Wrong event | Check `attachment_rules.by_category` direction, then `max_gap_days` |
| Wrong folder name | `advice_subjects` — add or reorder patterns, specific before general |
| A document behaving correctly is queued | `client_specific`, `requires_date`, or a routing rule. Not the threshold |
| A real problem is not flagged | Add or widen a rule in `edge_case_flags.rules` |

Then re-run. The regression tests exist so a fix cannot quietly break an earlier
one:

```bash
python3 -m unittest discover -s tests
```

Add a test for anything a real document taught you. `tests/test_pipeline.py` is
organised as one test per bug the v0 harness actually made; keep that habit.

### 5. Calibrate — last, not first

```bash
python3 harness.py --input input/nguyen-family \
                   --ground-truth input/ground_truth.json \
                   --calibrate --quiet-tree
```

Each row is a full pipeline re-run at that threshold, not a re-filter of one run's
output. That matters: an advice record below the threshold cannot anchor an
event, so everything that would have attached to it moves too. Sweeping the
classifier output alone would report a precision the system never achieves.

Read the `conf+wrong` column first. The recommendation is the lowest threshold
above which that column is empty — lowest, because among safe thresholds the one
that queues fewest documents wastes least of a reviewer's attention, and a queue
padded with correct documents is how a reviewer learns to stop reading it.
Consider one step higher as a margin: the sweep is fitted to the documents you
have.

Two answers the sweep can give instead of a number, both honest:

* **"Cannot calibrate."** No confident-and-wrong answers at *any* threshold,
  including zero. That is a fact about the sample, not a clean bill of health.
  You need documents the classifier actually gets wrong: bad scans, lookalikes,
  bundles, the awkward edges. This is what the synthetic samples currently
  return, and it is the correct answer for them.
* **"No threshold works."** Confident-and-wrong never reaches zero. No threshold
  fixes a classifier that is wrong while certain — go back to the knowledge base.

Once a real threshold is chosen, write it into `scoring.confidence.threshold` in
`knowledge_base.json` with a note about which corpus calibrated it. It is a
finding, not a constant.

## What to feed it

Ordinary clean files prove least. Prioritise:

* **Bundles** — an SOA with the ATP appended. Should raise `multi_doc_bundle` and
  refuse to place, not pick one.
* **Bad scans** — crooked, photocopied, faxed. Should score low and flag, not
  classify confidently. This is the one where a confident wrong answer is most
  likely and most damaging.
* **Multiple events for one client** — super in year one, insurance in year two.
  The events must stay separate and the inputs must land on the right one.
* **Couples with two surnames**, and files where one document names only one
  partner.
* **Old files** — pre-DBFO fee documents, superseded FSG editions.
* **Whatever your firm files that this list does not mention.** Every firm has a
  document type the knowledge base has never seen; those arrive as
  `unknown_type`, which is the correct answer until someone adds an entry.

## When step 3 is done

Not "when accuracy is high". When:

* several real client folders have been through, including deliberately awkward ones;
* the failure log shows misses being fixed and staying fixed;
* the threshold was chosen from data that contained real errors, rather than
  defaulted;
* the review queue is small enough to be read, and everything in it deserves to
  be there;
* every fix that could go in the knowledge base did.

That last one is what makes step 4 a swap rather than a rewrite.
