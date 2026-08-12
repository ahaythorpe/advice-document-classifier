"""Step 3 of the four steps: group documents into advice events.

The knowledge base calls this the fiddliest part of the system and SYSTEM.md
calls mis-grouping the most likely early failure. Both are right, and the v0
harness demonstrated it: sorting date *strings* put September 2025 before March
2024, so the March fact find and risk profile were filed under the September
insurance advice and the March super advice ended up holding nothing but itself.

The rewrite changes four things:

* anchors are found by ``advice_record_role``, never by the literal id "soa", so
  the DBFO CAR transition needs no code change;
* dates are real dates;
* attachment follows the direction of the advice process — inputs look forward
  to the advice they feed, authorisations look back to the advice they
  implement — with the directions themselves read from the knowledge base;
* when two events fit equally well the answer is "I don't know", not the first
  one in the list.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple

from .kb import KnowledgeBase
from .model import Record


class AdviceEvent(object):
    """One advisory decision and everything that belongs to it."""

    def __init__(self, anchor: Record, family_key: str,
                 subject_id: str, subject_label: str,
                 sub_kind_label: Optional[str] = None) -> None:
        self.anchor = anchor
        self.family_key = family_key
        self.subject_id = subject_id
        self.subject_label = subject_label
        self.sub_kind_label = sub_kind_label
        self.members = [anchor]  # type: List[Record]
        self.flags = []  # type: List[Any]

    @property
    def date(self) -> Optional[datetime.date]:
        return self.anchor.own_date.value if self.anchor.own_date else None

    @property
    def record_type(self) -> Optional[str]:
        return self.anchor.doc_type

    @property
    def key(self) -> str:
        return "%s|%s|%s" % (self.family_key,
                             self.date.isoformat() if self.date else "undated",
                             self.subject_id)

    def add(self, record: Record, reason: str, confidence: float) -> None:
        record.event = self
        record.attachment_reason = reason
        record.attachment_confidence = confidence
        self.members.append(record)

    def member_types(self) -> List[Optional[str]]:
        return [m.doc_type for m in self.members]

    def has_type(self, doc_id: str) -> bool:
        return any(m.doc_type == doc_id for m in self.members)

    def members_of_type(self, doc_id: str) -> List[Record]:
        return [m for m in self.members if m.doc_type == doc_id]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<AdviceEvent %s %s %s>" % (
            self.family_key, self.date, self.subject_label)


# ---------------------------------------------------------------------------
# Subject and sub-kind, read from the knowledge base
# ---------------------------------------------------------------------------

def infer_subject(kb: KnowledgeBase, text: str) -> Tuple[str, str]:
    """The subject-matter half of the event folder name."""
    low = text.lower()
    fallback = ("general", "Advice")
    for subject in kb.subjects:
        patterns = subject.get("patterns", [])
        if not patterns:
            fallback = (subject["id"], subject["label"])
            continue
        for phrase in patterns:
            if phrase.lower() in low:
                return subject["id"], subject["label"]
    return fallback


def infer_roa_sub_kind(kb: KnowledgeBase, record: Record) -> Optional[Dict[str, Any]]:
    """Which of the four ROA kinds this is, if it can be told.

    It matters: the further-advice kind depends on a prior SOA and the other
    three do not, so getting this wrong turns a normal file into a false
    exception, or hides a real one. Where the text does not say, this returns
    None and the roa_without_soa rule asks a human rather than assuming.
    """
    hints = kb.hints(record.doc_type or "")
    low = record.text.lower()
    for kind in hints.get("sub_kinds", []):
        for phrase in kind.get("patterns", []):
            if phrase.lower() in low:
                return kind
    return None


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

class GroupingResult(object):
    def __init__(self) -> None:
        self.events = []  # type: List[AdviceEvent]
        self.unanchored = []  # type: List[Tuple[Record, str]]
        self.missing_reference = {}  # type: Dict[str, Tuple[str, str]]


def build_events(kb: KnowledgeBase, records: List[Record]) -> GroupingResult:
    """Create one event per usable advice record, then attach everything else."""
    result = GroupingResult()
    threshold = kb.confidence_threshold

    # -- anchors
    for record in records:
        if not kb.is_advice_record(record.doc_type):
            continue
        if record.confidence < threshold:
            continue          # low_confidence flag is raised by the flags pass
        if not record.family_key:
            continue
        if record.own_date is None:
            continue          # no_date flag is raised by the flags pass
        subject_id, subject_label = infer_subject(kb, record.text)
        sub_kind = record.roa_sub_kind
        event = AdviceEvent(
            anchor=record,
            family_key=record.family_key,
            subject_id=subject_id,
            subject_label=subject_label,
            sub_kind_label=(sub_kind or {}).get("label"),
        )
        record.event = event
        record.attachment_reason = "anchors this event"
        record.attachment_confidence = record.confidence
        result.events.append(event)

    result.events.sort(key=lambda e: (e.family_key, e.date or datetime.date.min))

    # -- attachments
    rules = kb.data.get("filing_model", {}).get("attachment_rules", {})
    by_category = rules.get("by_category", {})
    max_gap = datetime.timedelta(days=int(rules.get("max_gap_days", 730)))

    for record in records:
        if record.event is not None:
            continue
        if record.doc_type is None or record.confidence < threshold:
            continue
        if kb.is_advice_record(record.doc_type):
            continue          # an unusable advice record; the flags pass explains why

        category = kb.category(record.doc_type) or ""
        rule = by_category.get(category, {})
        direction = rule.get("direction", "backward")

        if direction == "product_link":
            _attach_by_product(kb, record, result)
            continue

        if not kb.is_client_specific(record.doc_type):
            continue          # placed at licensee level by the storage pass

        if not record.family_key:
            result.unanchored.append((record, "no client identified"))
            continue

        candidates = [e for e in result.events if e.family_key == record.family_key]
        if not candidates:
            result.unanchored.append(
                (record, "client %s has no advice event on file" % record.family_key))
            continue

        # 1. explicit reference wins outright
        matched = _match_by_reference(kb, record, candidates)
        if matched is not None:
            event, why = matched
            if event is None:
                result.missing_reference[record.name] = why
                result.unanchored.append((record, why[0]))
                continue
            event.add(record, why[0], 0.95)
            continue

        # 2. directional date proximity
        if record.own_date is None:
            result.unanchored.append((record, "no date, so cannot be sequenced"))
            continue
        _attach_by_date(record, candidates, direction, max_gap, result)

    return result


def _match_by_reference(kb: KnowledgeBase, record: Record,
                        candidates: List[AdviceEvent]
                        ) -> Optional[Tuple[Optional[AdviceEvent], Tuple[str, str]]]:
    """Attach on an explicit citation, e.g. 'the SOA dated 14 March 2024'.

    Returns None when the document cites nothing, (event, why) on a hit, and
    (None, why) when it cites an advice record that is not in the batch — which
    is a genuine finding rather than a grouping failure.
    """
    for cited_type, cited_date in record.referenced_dates.items():
        if not kb.is_advice_record(cited_type):
            continue
        for event in candidates:
            if event.date == cited_date.value:
                return event, (
                    "explicitly cites the %s dated %s"
                    % (kb.abbrev(cited_type), cited_date.value.isoformat()),
                    cited_type)
        return None, (
            "cites a %s dated %s; no such advice record in this batch"
            % (kb.abbrev(cited_type), cited_date.value.isoformat()),
            cited_type)
    return None


def _attach_by_date(record: Record, candidates: List[AdviceEvent],
                    direction: str, max_gap: datetime.timedelta,
                    result: GroupingResult) -> None:
    """Attach to the nearest event in the direction the advice process runs."""
    own = record.own_date.value
    dated = [e for e in candidates if e.date is not None]
    if not dated:
        result.unanchored.append((record, "no dated advice event to attach to"))
        return

    if direction == "forward":
        preferred = sorted([e for e in dated if e.date >= own], key=lambda e: e.date)
        other = sorted([e for e in dated if e.date < own],
                       key=lambda e: e.date, reverse=True)
        preferred_word, other_word = "on or after", "before"
    else:
        preferred = sorted([e for e in dated if e.date <= own],
                           key=lambda e: e.date, reverse=True)
        other = sorted([e for e in dated if e.date > own], key=lambda e: e.date)
        preferred_word, other_word = "on or before", "after"

    pool, reversed_direction, word = preferred, False, preferred_word
    if not pool:
        pool, reversed_direction, word = other, True, other_word

    if not pool:
        result.unanchored.append((record, "no dated advice event to attach to"))
        return

    best = pool[0]
    # Two events on the same date fit equally well; there is no honest choice.
    if len(pool) > 1 and pool[1].date == best.date:
        result.unanchored.append((
            record,
            "two advice events dated %s fit equally well (%s, %s)"
            % (best.date.isoformat(), best.subject_label, pool[1].subject_label)))
        return

    gap = abs(best.date - own)
    if gap > max_gap:
        result.unanchored.append((
            record,
            "nearest advice event is %d days away (%s), beyond the %d-day limit"
            % (gap.days, best.date.isoformat(), max_gap.days)))
        return

    confidence = max(0.35, 1.0 - (float(gap.days) / max(1, max_gap.days)))
    if reversed_direction:
        confidence *= 0.6
        reason = ("nearest advice event is %s it (%s, %d days) — note this "
                  "reverses the expected order" % (word, best.date.isoformat(), gap.days))
    else:
        reason = "nearest advice event %s it (%s, %d days)" % (
            word, best.date.isoformat(), gap.days)

    best.add(record, reason, round(confidence, 2))


def _attach_by_product(kb: KnowledgeBase, record: Record,
                       result: GroupingResult) -> None:
    """Link issuer material to the event whose advice names the same product."""
    if not record.product_tokens:
        return
    hits = []  # type: List[Tuple[int, AdviceEvent, str]]
    for event in result.events:
        anchor_tokens = event.anchor.product_tokens
        shared = record.product_tokens & anchor_tokens
        if shared:
            hits.append((len(shared), event, ", ".join(sorted(shared))))
    if not hits:
        return
    hits.sort(key=lambda h: (-h[0], h[1].date or datetime.date.min))
    if len(hits) > 1 and hits[1][0] == hits[0][0]:
        # The knowledge base's shared_document_rule expects this: file once at
        # first use, reference elsewhere. Earliest event wins, and the tie is
        # recorded on the proposal rather than hidden.
        _, event, shared = hits[0]
        event.add(record, "names %s, which appears in %d advice records; filed at "
                          "the earliest per shared_document_rule" % (shared, len(hits)),
                  0.6)
        return
    _, event, shared = hits[0]
    event.add(record, "names %s, which this event's advice record recommends" % shared, 0.85)
