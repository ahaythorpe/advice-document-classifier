"""Ground truth, the failure log, and confidence calibration.

SYSTEM.md section 8: "Keep a failure log: input, tool's answer, correct answer,
one-line guess at why it missed. Every wrong answer is a specific fix (usually in
the knowledge base, sometimes in scoring). This log is also what proves accuracy
to a buyer."

v0 printed its flags and called that the failure log. It was not one: it had no
correct-answer column, because nothing recorded what the correct answer was, so
nothing could be measured and no threshold could be calibrated. This module adds
the missing half.

The metric that decides the threshold is CONFIDENT AND WRONG. SYSTEM.md section
7 is explicit that a wrong answer at high confidence is worse than an honest
"not sure", so the threshold is not tuned for accuracy or for a small review
queue — it is raised until nothing is confidently wrong, and the queue is
whatever size that costs.
"""

from __future__ import annotations

import copy
import datetime
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .extract import ExtractedDocument
from .kb import KnowledgeBase
from .model import Record
from .pipeline import PipelineResult, run as run_pipeline


class GroundTruth(object):
    def __init__(self, data: Dict[str, Any], path: Optional[str] = None) -> None:
        self.path = path
        self.documents = data.get("documents", {})

    @classmethod
    def load(cls, path: str) -> "GroundTruth":
        with open(path, "r") as fh:
            return cls(json.load(fh), path=path)

    def has(self, name: str) -> bool:
        return name in self.documents

    def get(self, name: str) -> Dict[str, Any]:
        return self.documents.get(name, {})

    def __len__(self) -> int:
        return len(self.documents)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

class Comparison(object):
    """One document: what the tool said, what was true, and whether it matters."""

    def __init__(self, record: Record, expected: Dict[str, Any],
                 kb: KnowledgeBase, event_label: Optional[str]) -> None:
        self.record = record
        self.expected = expected
        self.kb = kb
        self.predicted_event_label = event_label

    @property
    def expected_type(self) -> Optional[str]:
        return self.expected.get("type")

    @property
    def type_correct(self) -> bool:
        return self.record.doc_type == self.expected_type

    @property
    def client_correct(self) -> bool:
        return (self.record.family_key or None) == (self.expected.get("client") or None)

    @property
    def expected_event(self) -> Optional[str]:
        return self.expected.get("event")

    @property
    def event_correct(self) -> bool:
        return (self.predicted_event_label or None) == (self.expected_event or None)

    @property
    def review_expected(self) -> bool:
        return bool(self.expected.get("needs_review"))

    @property
    def review_correct(self) -> bool:
        return self.record.needs_review == self.review_expected

    @property
    def confident_and_wrong(self) -> bool:
        """The failure this system exists to avoid."""
        return (not self.type_correct
                and self.record.doc_type is not None
                and self.record.confidence >= self.kb.confidence_threshold)

    @property
    def raised_flags(self) -> List[str]:
        return sorted(set(f.rule_id for f in self.record.flags))

    @property
    def missing_flags(self) -> List[str]:
        expected = set(self.expected.get("expect_flags", []))
        return sorted(expected - set(self.raised_flags))

    @property
    def unexpected_flags(self) -> List[str]:
        expected = set(self.expected.get("expect_flags", []))
        # Flags that follow from a wrong type are noise here; the type is the
        # finding worth reporting, not its consequences.
        return sorted(set(self.raised_flags) - expected)

    @property
    def ok(self) -> bool:
        return (self.type_correct and self.client_correct and self.event_correct
                and self.review_correct and not self.missing_flags)

    def why(self) -> str:
        """One line guessing why it missed — the fourth column of the log."""
        if self.ok:
            return ""
        problems = []
        if not self.type_correct:
            problems.append(
                "type: said %s, is %s (%s)"
                % (self.kb.abbrev(self.record.doc_type),
                   self.kb.abbrev(self.expected_type),
                   self.record.classification.why()))
        if not self.client_correct:
            problems.append("client: said %s, is %s"
                            % (self.record.family_key or "none",
                               self.expected.get("client") or "none"))
        if not self.event_correct:
            problems.append("event: said %s, is %s (%s)"
                            % (self.predicted_event_label or "none",
                               self.expected_event or "none",
                               self.record.attachment_reason or "not attached"))
        if not self.review_correct:
            problems.append("review queue: %s, should be %s"
                            % ("queued" if self.record.needs_review else "filed",
                               "queued" if self.review_expected else "filed"))
        if self.missing_flags:
            problems.append("missed flags: %s" % ", ".join(self.missing_flags))
        return " | ".join(problems)


def _event_labels(result: PipelineResult, truth: GroundTruth) -> Dict[str, Optional[str]]:
    """Name each predicted event after the expected event of its anchor.

    Grouping is only meaningful relative to a partition, so an event is judged by
    whether a document landed with the right neighbours, not by its folder name.
    """
    labels = {}  # type: Dict[str, Optional[str]]
    for event in (result.grouping.events if result.grouping else []):
        labels[event.key] = truth.get(event.anchor.name).get("event")
    return labels


def compare(result: PipelineResult, truth: GroundTruth) -> List[Comparison]:
    labels = _event_labels(result, truth)
    out = []  # type: List[Comparison]
    for record in result.records:
        if not truth.has(record.name):
            continue
        label = labels.get(record.event.key) if record.event else None
        out.append(Comparison(record, truth.get(record.name), result.kb, label))
    return out


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------

def score(comparisons: List[Comparison]) -> Dict[str, Any]:
    total = len(comparisons)
    if not total:
        return {"total": 0}

    def ratio(n: int) -> float:
        return round(float(n) / total, 3)

    type_ok = sum(1 for c in comparisons if c.type_correct)
    client_ok = sum(1 for c in comparisons if c.client_correct)
    event_ok = sum(1 for c in comparisons if c.event_correct)
    review_ok = sum(1 for c in comparisons if c.review_correct)
    confident_wrong = [c for c in comparisons if c.confident_and_wrong]

    filed = [c for c in comparisons if not c.record.needs_review]
    filed_correct = [c for c in filed if c.type_correct and c.event_correct]

    return {
        "total": total,
        "type_correct": type_ok, "type_accuracy": ratio(type_ok),
        "client_correct": client_ok, "client_accuracy": ratio(client_ok),
        "event_correct": event_ok, "event_accuracy": ratio(event_ok),
        "review_correct": review_ok, "review_accuracy": ratio(review_ok),
        "confident_and_wrong": len(confident_wrong),
        "confident_and_wrong_files": [c.record.name for c in confident_wrong],
        "auto_filed": len(filed),
        "auto_filed_correct": len(filed_correct),
        "auto_filed_precision": (round(float(len(filed_correct)) / len(filed), 3)
                                 if filed else None),
        "review_queue": total - len(filed),
        "fully_correct": sum(1 for c in comparisons if c.ok),
    }


# ---------------------------------------------------------------------------
# Failure log
# ---------------------------------------------------------------------------

def failure_log_rows(comparisons: List[Comparison], run_id: str,
                     kb_version: str, classifier: str) -> List[Dict[str, Any]]:
    rows = []  # type: List[Dict[str, Any]]
    for comparison in comparisons:
        if comparison.ok:
            continue
        record = comparison.record
        rows.append({
            "run_id": run_id,
            "kb_version": kb_version,
            "classifier": classifier,
            "input": record.name,
            "tool_type": record.doc_type,
            "correct_type": comparison.expected_type,
            "confidence": record.confidence,
            "tool_client": record.family_key,
            "correct_client": comparison.expected.get("client"),
            "tool_event": comparison.predicted_event_label,
            "correct_event": comparison.expected_event,
            "queued_for_review": record.needs_review,
            "should_be_queued": comparison.review_expected,
            "flags_raised": comparison.raised_flags,
            "flags_missed": comparison.missing_flags,
            "confident_and_wrong": comparison.confident_and_wrong,
            "why": comparison.why(),
        })
    return rows


def write_failure_log(rows: List[Dict[str, Any]], path: str) -> str:
    """Append to a JSONL log. Appending, not overwriting: the improvement loop
    is a history, and the point is to see failures disappear over runs."""
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "a") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return path


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def calibrate(kb: KnowledgeBase, documents: List[ExtractedDocument],
              truth: GroundTruth,
              thresholds: Optional[List[float]] = None) -> List[Dict[str, Any]]:
    """Re-run the whole pipeline at each threshold and score it.

    The pipeline is re-run rather than the confidences re-filtered, because the
    threshold does more than gate filing: an advice record below it cannot anchor
    an event, so everything that would have attached to that event moves too.
    Sweeping the classifier output alone would report a precision the system
    never actually achieves.
    """
    thresholds = thresholds or [round(0.05 * i, 2) for i in range(0, 20)]
    rows = []  # type: List[Dict[str, Any]]

    for threshold in thresholds:
        trial_kb = KnowledgeBase(copy.deepcopy(kb.data), path=kb.path)
        trial_kb.data["scoring"]["confidence"]["threshold"] = threshold
        result = run_pipeline(trial_kb, documents)
        comparisons = compare(result, truth)
        stats = score(comparisons)
        rows.append({
            "threshold": threshold,
            "type_accuracy": stats.get("type_accuracy"),
            "event_accuracy": stats.get("event_accuracy"),
            "auto_filed": stats.get("auto_filed"),
            "auto_filed_precision": stats.get("auto_filed_precision"),
            "review_queue": stats.get("review_queue"),
            "confident_and_wrong": stats.get("confident_and_wrong"),
            "fully_correct": stats.get("fully_correct"),
        })
    return rows


def recommend_threshold(rows: List[Dict[str, Any]]) -> Tuple[Optional[float], str]:
    """The lowest threshold above which nothing is ever confidently wrong.

    Lowest rather than highest, because among safe thresholds the one that
    queues fewest documents wastes least of a reviewer's attention — and a queue
    padded with documents the tool got right is how a reviewer learns to stop
    reading the queue.

    Two honest refusals are built in.

    A sweep in which nothing is confidently wrong at ANY threshold, including
    zero, has not calibrated anything. It has discovered that the sample is too
    small or too easy to contain the failure the threshold exists to prevent.
    Reporting 0.00 from such a sweep would be arithmetically correct and
    practically dangerous: it reads as "no threshold needed" when it means "this
    sample cannot tell you". That is the overconfidence SYSTEM.md section 7
    warns about, wearing a number.

    A sweep in which confident-and-wrong never reaches zero is a knowledge-base
    problem. No threshold fixes a classifier that is wrong while certain.
    """
    if not rows:
        return None, "no calibration rows"

    ordered = sorted(rows, key=lambda r: r["threshold"])
    lowest = ordered[0]["threshold"]

    if all(r["confident_and_wrong"] == 0 for r in ordered):
        return None, (
            "this sample produces no confident-and-wrong answers at any threshold, "
            "including %.2f — so it cannot calibrate one. That is a fact about the "
            "sample, not evidence that the current threshold is safe. Calibration "
            "needs documents the classifier actually gets wrong: real files, "
            "bad scans, lookalikes, and the awkward edges. Keep the threshold "
            "where it is until real documents have been through."
            % lowest)

    # The smallest threshold from which the safe run continues all the way up.
    safe_from = None
    for candidate in ordered:
        tail = [r for r in ordered if r["threshold"] >= candidate["threshold"]]
        if all(r["confident_and_wrong"] == 0 for r in tail):
            safe_from = candidate
            break

    if safe_from is None:
        return None, (
            "no threshold in the sweep eliminates confident-and-wrong answers. "
            "Raising the threshold cannot fix a classifier that is wrong while "
            "certain — the fix belongs in the knowledge base's signals, not here")

    return safe_from["threshold"], (
        "lowest threshold above which nothing is confidently wrong; auto-files "
        "%d of %d with %s precision and queues %d. Consider one step higher as "
        "a margin — the sweep is fitted to the documents you have"
        % (safe_from["auto_filed"],
           safe_from["auto_filed"] + safe_from["review_queue"],
           ("%.0f%%" % (safe_from["auto_filed_precision"] * 100))
           if safe_from["auto_filed_precision"] is not None else "n/a",
           safe_from["review_queue"]))


def run_id(now: Optional[datetime.datetime] = None) -> str:
    return (now or datetime.datetime.now()).strftime("%Y%m%dT%H%M%S")
