# Architecture

How the pieces fit, and why they are shaped this way. SYSTEM.md is the spec; this
is the implementation's reasoning.

## The pipeline

```
  input/*.pdf ──► extract.py ──► classify.py ──► entities.py
                  text +          type +          client, dates,
                  quality         confidence      risk category, products
                                        │
                                        ▼
                                   events.py ──► flags.py ──► storage.py
                                   advice        13 KB rules   folder plan
                                   events                      (data only)
                                        │
                                        ▼
                            evaluate.py ──► report.py
                            vs ground truth   console
```

`pipeline.run()` is the only place these are wired together, and both the sample
path and the real-document path go through it. That is deliberate: a fix proven
against `sample_documents.json` is a fix proven for a real intake batch, which is
the premise of build step 3.

## Three settings that must not entangle

SYSTEM.md section 2 names three knobs that do not depend on each other, and
keeping them independent is what stops the design tangling later.

| Setting | Where it lives | What must not happen |
|---|---|---|
| Display mode | `report.py` only | Nothing outside `report.py` may branch on it. It changes how much is *said*, never what was *decided*. |
| Filing mode | `storage.py` + `naming.py` | Arrangement is a nesting rule over results already produced. The classifier must not know the folder scheme. |
| Classification engine | `classify.py` behind `Classifier` | No module downstream may know which engine ran. |

## The knowledge base is the only source of truth

`kb.py` is the sole reader of `knowledge_base.json`. Everything else asks it.
Nothing anywhere hardcodes a document type, a weight, a threshold, a folder name
or a flag rule.

Two concrete consequences:

**Asking for an undefined flag raises.** `Flag.from_rule()` looks the rule up in
`edge_case_flags.rules` and raises `KnowledgeBaseError` if it is not there. You
cannot invent a flag in code; you add it to the domain model first. Severity and
placement/compliance class come from the rule, so retuning what a flag *means* is
a knowledge-base edit.

**Roles, not ids.** Advice records are found via `advice_record_role: true`, never
by matching `"soa"`. `car` already carries that role. `tests/test_pipeline.py`
contains a test that relabels CAR and asserts it anchors an advice event with no
code change — that test is the DBFO Tranche 2 migration, run in advance.

## Where the v0 harness went wrong

Every one of these was observed in the v0 output on the same ten samples, and
each has a regression test.

| Bug | Cause | Fix |
|---|---|---|
| An ATP classified as an SOA | Title patterns scored equally wherever they appeared, so citing an SOA looked like being one | KB `title_position` + `reference_patterns`: a title inside a citation is a mention, weight 0.5, versus 6.0 for a title worn in title position |
| Ties broken by file order | `max()` over a dict returned the first key at the top score; `soa` is first in the KB, so every ATP/SOA tie became an SOA | Explicit sort on `(-score, kb_order)`, and the weighting change means the tie no longer occurs |
| March inputs filed under September advice | Dates compared as strings: `"10 September 2025" < "14 March 2024"` because `'0' < '4'` | Real `datetime.date` throughout, Australian day-first for numeric forms |
| Correct ROA flagged at 0.57 | `top/(top+runner)` produced arbitrary mid-range values | `margin × evidence`, where margin is separation from the runner-up and evidence is absolute score against a floor |
| Garbage scored 1.0 confidence | Margin alone: one weak cue and nothing else gives perfect separation | The evidence floor, plus extraction quality as a hard ceiling on confidence |
| `[CLIENT] None` folder | FSG has no client, and that was treated as a placement failure | `client_specific: false` in the KB, plus a `_Licensee documents` folder |
| PDS orphaned | No product linking | CamelCase product tokens matched against the advice record's text |
| 7 of 11 flag rules unimplemented, silently | Nothing compared code against the domain model | `flags.coverage()` reports unimplemented rules in every run |
| No "correct answer" column | No ground truth existed | `ground_truth.json` + `evaluate.py` |

## Confidence

```
margin      = (top - runner_up) / top          separation from the alternative
evidence    = min(1, top / evidence_floor)     absolute weight of what was found
confidence  = margin × evidence
confidence  = min(confidence, extraction_quality)
```

Both halves are needed. Margin alone lets a document that matched one weak cue
and nothing else score 1.0 — which is exactly how a bad scan gets filed
confidently. The quality ceiling is the other half of the same idea: a document
we could barely read cannot be classified confidently, however well its noise
happened to score.

## Grouping

An advice event is anchored by an advice record. Everything else attaches by, in
order of precedence:

1. **Explicit citation** — "the Statement of Advice dated 14 March 2024" resolves
   to that event. Confidence 0.95.
2. **Directional proximity** — direction comes from the document's category, read
   from `filing_model.attachment_rules`: inputs look *forward* to the advice they
   feed, authorisations and ongoing-service documents look *backward* to the
   advice they follow. Confidence decays with the gap, capped at 730 days.
3. **Product link** — issuer material (PDS) attaches to the event whose advice
   record names the same product.

Two candidates that fit equally well produce `event_ambiguous` and nothing is
filed. Picking one to keep the tree tidy is precisely the mis-grouping SYSTEM.md
calls the most likely early failure, and a wrongly attached input silently
corrupts the event it lands in.

Attaching against the expected direction is allowed at reduced confidence, with
the reversal stated on the proposal — because the reversal is often itself the
finding. An input dated after its advice record is the `fact_find_after_soa`
exception.

## Storage writes nothing

`storage.py` produces a `FolderPlan`, which is data. `ProposalOnlyTarget.commit()`
raises, with an explanation. Phase 1 has no code path that moves a file, because
the approve/edit/reject step that would authorise it is build step 5, and filing
before then would be exactly the silent filing the spec forbids.

`StorageTarget` exists so that a local target and an Australian-region cloud
target can both implement it later without the classifier or the grouper knowing
which is in use — `filing_model.build_note` asks for exactly that.

## What is deliberately not built

**The AI summary** (`summary_feature` in the knowledge base, SYSTEM.md section 6)
is not started. Its own preconditions forbid it: a summary built on mis-grouped
documents is confidently wrong, and grouping has not yet met real documents.

**Bundle splitting.** `multi_doc_bundle` detects a file containing more than one
document — the classic SOA with an ATP stapled to the back — and routes it to
review. It does not split it. Splitting changes the input set, and doing that
automatically before classification is trusted would compound one guess with
another.

**OCR.** Bad scans are detected and quarantined, not rescued. Adding OCR would
make the tool confident about documents it currently, correctly, refuses.
