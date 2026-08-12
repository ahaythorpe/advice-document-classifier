"""The four steps, wired together.

    extract -> classify -> place -> file or flag

One function, so that the sample path and the real-document path are provably
the same path. A fix proven against sample_documents.json is a fix proven for a
real intake batch, which is the whole point of build step 3.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from . import entities, events, flags, storage
from .classify import Classifier, KeywordClassifier
from .extract import ExtractedDocument
from .kb import KnowledgeBase
from .model import Record
from .clients import ClientRegister
from .profiles import FilingProfile


class PipelineResult(object):
    def __init__(self, kb: KnowledgeBase, classifier_name: str) -> None:
        self.kb = kb
        self.classifier_name = classifier_name
        self.records = []  # type: List[Record]
        self.grouping = None  # type: Optional[events.GroupingResult]
        self.plan = None  # type: Optional[storage.FolderPlan]
        self.profile = None  # type: Optional[FilingProfile]
        self.batch_client = None  # type: Optional[str]
        self.register = None  # type: Optional[ClientRegister]
        self.new_clients = []  # type: List[Any]
        self.extraction_failures = []  # type: List[Dict[str, str]]
        self.started = None  # type: Optional[datetime.datetime]

    @property
    def flagged(self) -> List[Record]:
        return [r for r in self.records if r.flags]

    @property
    def needing_review(self) -> List[Record]:
        return [r for r in self.records if r.needs_review]


def _enrich(kb: KnowledgeBase, record: Record) -> None:
    """Pull identity, dates and type-specific details out of the text."""
    doc_type = record.doc_type

    raw, surnames, family = entities.extract_client(record.text)
    record.client_raw = raw
    record.surnames = surnames
    record.family_key = family
    record.given_names = entities.extract_given_names(record.text) if family else []
    record.client_provenance = "read from document" if family else None

    hints = kb.hints(doc_type) if doc_type else {}
    record.own_date, record.date_provenance = entities.extract_own_date(
        record.text, hints.get("key_fields", []))

    reference_patterns = {}  # type: Dict[str, List[str]]
    for doc in kb.documents:
        patterns = doc.get("classifier_hints", {}).get("reference_patterns", [])
        if patterns:
            reference_patterns[doc["id"]] = patterns
    record.referenced_dates = entities.extract_referenced_dates(
        record.text, reference_patterns)

    record.product_tokens = entities.extract_product_tokens(record.text)

    if hints.get("category_patterns"):
        record.risk_category = entities.extract_risk_category(
            record.text, hints["category_patterns"], kb.risk_categories)

    if hints.get("sub_kinds"):
        record.roa_sub_kind = events.infer_roa_sub_kind(kb, record)


def _resolve_clients(kb: KnowledgeBase, records: List[Record]) -> Optional[str]:
    """Merge compatible family keys, then find the batch's client if it has one."""
    mapping = entities.merge_family_keys([r.family_key for r in records])
    for record in records:
        if record.family_key and mapping.get(record.family_key) != record.family_key:
            merged = mapping[record.family_key]
            record.client_provenance = (
                "read as '%s', merged into '%s' (one household, two surnames)"
                % (record.family_key, merged))
            record.family_key = merged

    threshold = kb.confidence_threshold
    distinct = set()
    for record in records:
        if not record.family_key or record.confidence < threshold:
            continue
        if kb.is_client_specific(record.doc_type):
            distinct.add(record.family_key)
    # Exactly one client in the batch, and only then, may non-client-specific
    # documents inherit it. Two clients means inheriting would be a guess.
    return list(distinct)[0] if len(distinct) == 1 else None


def _match_clients(kb: KnowledgeBase, result: "PipelineResult",
                   register: ClientRegister) -> None:
    """Resolve each document's client against the firm's existing list.

    Where a client matches, the firm's own folder name wins over ours — the
    document belongs in the file they already have, spelled the way they already
    spell it. Where it does not match, nothing is invented silently: the
    new_client_proposed rule asks once.
    """
    from .clients import ClientEntry
    proposed = {}
    for record in result.records:
        if not record.family_key or not kb.is_client_specific(record.doc_type):
            continue
        match = register.match(record.surnames, record.given_names)
        record.client_match = match
        if match.matched:
            record.family_key = match.entry.folder_name
            record.client_provenance = ("matched to the firm's existing client "
                                        "%s (%.2f) — %s"
                                        % (match.entry.folder_name, match.score,
                                           match.reason))
        elif "too closely" not in match.reason:
            proposed.setdefault(
                record.family_key,
                ClientEntry.from_folder_name(record.family_key))
    result.new_clients = list(proposed.values())


def run(kb: KnowledgeBase, documents: List[ExtractedDocument],
        classifier: Optional[Classifier] = None,
        extraction_failures: Optional[List[Dict[str, str]]] = None,
        now: Optional[datetime.datetime] = None,
        profile: Optional[FilingProfile] = None,
        register: Optional[ClientRegister] = None) -> PipelineResult:
    classifier = classifier or KeywordClassifier(kb)
    result = PipelineResult(kb, classifier.name)
    result.extraction_failures = extraction_failures or []
    result.started = now or datetime.datetime.now()

    # 1-2. extract (already done by the caller) and classify
    for document in documents:
        record = Record(document, classifier.classify(document))
        _enrich(kb, record)
        result.records.append(record)

    result.batch_client = _resolve_clients(kb, result.records)
    result.register = register
    if register is not None:
        _match_clients(kb, result, register)

    # 3. place
    result.grouping = events.build_events(kb, result.records)

    # 4. file or flag
    flags.run_all(kb, result.records, result.grouping, result.batch_client)
    result.profile = profile or FilingProfile.load()
    result.plan = storage.build_plan(kb, result.records, result.grouping,
                                     result.batch_client, result.profile)
    return result
