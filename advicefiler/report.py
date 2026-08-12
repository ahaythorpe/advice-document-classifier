"""Console output.

Display mode is one of the three independent settings in SYSTEM.md section 2:
*new-to-industry* explains what each document is, why it exists in law and where
it sits in the advice process; *experienced* shows identification, placement and
flags only. Both read the same run — the setting changes how much is said, never
what was decided.
"""

from __future__ import annotations

import textwrap
from typing import Any, Dict, List, Optional

from . import flags as flags_module
from .evaluate import Comparison
from .kb import KnowledgeBase
from .model import Record
from .pipeline import PipelineResult
from .storage import FolderPlan

NEW_TO_INDUSTRY = "new"
EXPERIENCED = "experienced"

RULE = "=" * 78
THIN = "-" * 78

SEVERITY_MARK = {"high": "!!", "medium": "! ", "low": ". "}


def _wrap(text: str, indent: str = "     ") -> str:
    return "\n".join(textwrap.wrap(text, width=78 - len(indent),
                                   initial_indent=indent,
                                   subsequent_indent=indent))


# ---------------------------------------------------------------------------

def print_header(result: PipelineResult, backends: Dict[str, bool]) -> None:
    kb = result.kb
    print(RULE)
    print("ADVICE DOCUMENT CLASSIFIER — run %s"
          % result.started.strftime("%Y-%m-%d %H:%M"))
    print(RULE)
    print("knowledge base : v%s" % kb.version)
    print("classifier     : %s" % result.classifier_name)
    print("threshold      : %.2f (confidence), %.1f (evidence floor)"
          % (kb.confidence_threshold, kb.evidence_floor))
    print("documents      : %d" % len(result.records))
    if result.batch_client:
        print("intake batch   : resolves to one client (%s); non-client-specific "
              "documents may inherit it" % result.batch_client)
    else:
        print("intake batch   : more than one client (or none); nothing inherits "
              "a client")
    missing = [name for name, ok in sorted(backends.items()) if not ok]
    if missing:
        print("extractors     : %s missing — real PDFs/Word files cannot be read "
              "(pip install -r requirements.txt)" % ", ".join(missing))
    else:
        print("extractors     : all backends available")
    if result.extraction_failures:
        print()
        print("COULD NOT BE READ AT ALL (%d):" % len(result.extraction_failures))
        for failure in result.extraction_failures:
            print("  - %s: %s" % (failure["file"], failure["error"]))
    print()


def print_scorecard(result: PipelineResult, display: str = EXPERIENCED) -> None:
    kb = result.kb
    print(RULE)
    print("CLASSIFICATION SCORECARD")
    print(RULE)
    for record in result.records:
        status = "REVIEW" if record.needs_review else "  OK  "
        print("[%s] %-16s %-22s conf=%.2f  client=%s"
              % (status, record.name, kb.abbrev(record.doc_type),
                 record.confidence, record.family_key or "-"))
        if display == NEW_TO_INDUSTRY and record.doc_type:
            _print_teaching(kb, record.doc_type)
        if record.document.quality.score < 1.0:
            print(_wrap("extraction quality %.2f — %s"
                        % (record.document.quality.score,
                           "; ".join(record.document.quality.reasons)),
                        indent="       "))
    print()


def _print_teaching(kb: KnowledgeBase, doc_type: str) -> None:
    entry = kb.doc(doc_type)
    teaching = entry.get("teaching", {})
    stage = None
    for candidate in kb.data.get("advice_process_stages", []):
        if doc_type in candidate.get("typical_docs", []):
            stage = candidate
            break
    print(_wrap("WHAT: %s" % teaching.get("what_it_is", "-"), "       "))
    print(_wrap("WHY : %s" % teaching.get("why_it_exists", "-"), "       "))
    if stage:
        print(_wrap("WHERE: stage %s, %s" % (stage["stage"], stage["name"]), "       "))
    law = entry.get("legislation", {}).get("primary")
    if law:
        print(_wrap("LAW : %s" % law, "       "))
    note = teaching.get("two_weeks_in_note")
    if note:
        print(_wrap("NOTE: %s" % note, "       "))
    print()


def print_tree(result: PipelineResult, display: str = EXPERIENCED) -> None:
    kb = result.kb
    plan = result.plan  # type: Optional[FolderPlan]
    print(RULE)
    print("PROPOSED FOLDER TREE (client outer / advice-event inner)")
    print(RULE)
    print("Nothing below has been moved. Every line is a proposal for a human to")
    print("approve, edit or reject.")
    print()

    if plan is None:
        print("(no plan)")
        return

    # Nest by outer axis (client) then inner axis (advice event), which is the
    # shape of the filing model rather than a flat list of paths.
    nested = {}  # type: Dict[str, Dict[Optional[str], List[Any]]]
    for planned in plan.files:
        outer = planned.folder[0]
        inner = "/".join(planned.folder[1:]) or None
        nested.setdefault(outer, {}).setdefault(inner, []).append(planned)

    def outer_sort(name: str) -> Any:
        # Special folders last; they are exceptions, not clients.
        return (name.startswith("_"), name.lower())

    for outer in sorted(nested, key=outer_sort):
        print("[%s]" % outer)
        inners = nested[outer]
        for inner in sorted(inners, key=lambda k: (k is None, (k or "").lower())):
            indent = "   |  "
            if inner is not None:
                print("   +- [%s]" % inner)
                indent = "   |     "
            for planned in sorted(inners[inner], key=lambda p: p.filename):
                record = planned.record
                print("%s- %s" % (indent, planned.filename))
                print("%s    from %s (%s, conf %.2f)"
                      % (indent, record.name, kb.abbrev(record.doc_type),
                         record.confidence))
                if planned.rationale:
                    print(_wrap(planned.rationale, indent + "    "))
                for flag in record.compliance_flags:
                    print("%s    %s %s: %s"
                          % (indent, SEVERITY_MARK.get(flag.severity, "  "),
                             flag.rule_id, flag.message))
        print()


def print_events(result: PipelineResult) -> None:
    kb = result.kb
    grouping = result.grouping
    if grouping is None or not grouping.events:
        return
    print(RULE)
    print("ADVICE EVENTS (%d)" % len(grouping.events))
    print(RULE)
    for event in grouping.events:
        print("%s — %s [%s]%s"
              % (event.family_key,
                 event.date.isoformat() if event.date else "undated",
                 kb.abbrev(event.record_type),
                 (" · %s" % event.sub_kind_label) if event.sub_kind_label else ""))
        print("   subject: %s" % event.subject_label)
        print("   anchor : %s" % event.anchor.name)
        for member in event.members:
            if member is event.anchor:
                continue
            print("   + %-16s %-8s (%.2f) %s"
                  % (member.name, kb.abbrev(member.doc_type),
                     member.attachment_confidence, member.attachment_reason))
        completeness = _completeness(kb, event)
        if completeness:
            print("   missing: %s" % ", ".join(completeness))
        print()


def _completeness(kb: KnowledgeBase, event: Any) -> List[str]:
    """What a coherent advice event would normally also contain.

    Reported, never flagged. Real files are legitimately incomplete — scaled
    advice may have no full fact find, and not every recommendation is
    implemented. This is a prompt for a reviewer, not a finding.
    """
    present = set(event.member_types())
    wanted = []
    if not present & {"fact_find"}:
        wanted.append("fact find")
    if not present & {"risk_profile"}:
        wanted.append("risk profile")
    if not present & {"authority_to_proceed"}:
        wanted.append("authority to proceed")
    return wanted


def print_flags(result: PipelineResult) -> None:
    kb = result.kb
    flagged = [r for r in result.records if r.flags]
    print(RULE)
    print("FLAGS")
    print(RULE)
    if not flagged:
        print("(none — on real data this is suspicious, not reassuring: it means")
        print("nothing surfaced for review)")
        print()
        return

    order = {"high": 0, "medium": 1, "low": 2}
    rows = []  # type: List[Any]
    for record in flagged:
        for flag in record.flags:
            rows.append((order.get(flag.severity, 3), flag.flag_class,
                         record, flag))
    rows.sort(key=lambda r: (r[0], r[1]))

    for _, flag_class, record, flag in rows:
        verb = "BLOCKS FILING" if flag.blocks_filing else "files anyway"
        print("%s %-26s %-14s [%s / %s]"
              % (SEVERITY_MARK.get(flag.severity, "  "), flag.rule_id,
                 record.name, flag.severity, verb))
        print(_wrap(flag.message))
    print()


def print_coverage(kb: KnowledgeBase) -> None:
    coverage = flags_module.coverage(kb)
    print(RULE)
    print("RULE COVERAGE")
    print(RULE)
    print("implemented        : %d of %d knowledge-base rules"
          % (len(coverage["implemented"]), len(kb.flag_rules)))
    if coverage["not_implemented"]:
        print("NOT IMPLEMENTED    : %s" % ", ".join(coverage["not_implemented"]))
        print(_wrap("These rules exist in the domain model and are not checked by "
                    "this run. Documents they would have caught pass silently.",
                    indent="  "))
    else:
        print("not implemented    : none")
    if coverage["not_in_knowledge_base"]:
        print("NOT IN KB          : %s (implemented in code but undefined in the "
              "knowledge base — the source of truth has forked)"
              % ", ".join(coverage["not_in_knowledge_base"]))
    print()


# ---------------------------------------------------------------------------
# Evaluation output
# ---------------------------------------------------------------------------

def print_failure_log(comparisons: List[Comparison], stats: Dict[str, Any]) -> None:
    print(RULE)
    print("FAILURE LOG — input / tool's answer / correct answer / why")
    print(RULE)
    misses = [c for c in comparisons if not c.ok]
    if not misses:
        print("(no misses against ground truth)")
    for comparison in misses:
        record = comparison.record
        marker = "CONFIDENT AND WRONG" if comparison.confident_and_wrong else "miss"
        print("- %-16s %s" % (record.name, marker))
        print("    tool    : %s (conf %.2f)%s"
              % (comparison.kb.abbrev(record.doc_type), record.confidence,
                 ", queued" if record.needs_review else ", filed"))
        print("    correct : %s%s"
              % (comparison.kb.abbrev(comparison.expected_type),
                 ", should be queued" if comparison.review_expected else ""))
        print(_wrap("why     : %s" % comparison.why(), indent="    "))
    print()
    print(THIN)
    print("ACCURACY (%d labelled documents)" % stats.get("total", 0))
    print(THIN)
    print("  document type    : %d/%d  (%.0f%%)"
          % (stats["type_correct"], stats["total"], stats["type_accuracy"] * 100))
    print("  client           : %d/%d  (%.0f%%)"
          % (stats["client_correct"], stats["total"], stats["client_accuracy"] * 100))
    print("  advice event     : %d/%d  (%.0f%%)"
          % (stats["event_correct"], stats["total"], stats["event_accuracy"] * 100))
    print("  review decision  : %d/%d  (%.0f%%)"
          % (stats["review_correct"], stats["total"], stats["review_accuracy"] * 100))
    print("  auto-filed       : %d, of which correct: %d%s"
          % (stats["auto_filed"], stats["auto_filed_correct"],
             (" (%.0f%% precision)" % (stats["auto_filed_precision"] * 100))
             if stats["auto_filed_precision"] is not None else ""))
    print("  review queue     : %d" % stats["review_queue"])
    print("  CONFIDENT+WRONG  : %d%s"
          % (stats["confident_and_wrong"],
             ("  <-- %s" % ", ".join(stats["confident_and_wrong_files"]))
             if stats["confident_and_wrong"] else "   (the metric that matters)"))
    print()


def print_calibration(rows: List[Dict[str, Any]], recommended: Any,
                      rationale: str, current: float) -> None:
    print(RULE)
    print("CONFIDENCE CALIBRATION")
    print(RULE)
    print("Each row is a full pipeline re-run at that threshold, not a re-filter:")
    print("an advice record below the threshold cannot anchor an event, so its")
    print("whole event moves with it.")
    print()
    print("  thresh   type acc   event acc   filed   precision   queued   conf+wrong")
    print("  " + THIN[:72])
    for row in rows:
        precision = ("%.0f%%" % (row["auto_filed_precision"] * 100)
                     if row["auto_filed_precision"] is not None else "  -  ")
        marker = ""
        if recommended is not None and abs(row["threshold"] - recommended) < 1e-9:
            marker = "  <-- recommended"
        if abs(row["threshold"] - current) < 1e-9:
            marker += "  (current)"
        print("   %.2f      %5.0f%%      %5.0f%%     %3d      %6s      %3d        %2d%s"
              % (row["threshold"],
                 (row["type_accuracy"] or 0) * 100,
                 (row["event_accuracy"] or 0) * 100,
                 row["auto_filed"], precision, row["review_queue"],
                 row["confident_and_wrong"], marker))
    print()
    print(_wrap("Recommendation: %s. %s"
                % ("%.2f" % recommended if recommended is not None else "none",
                   rationale), indent="  "))
    print()
