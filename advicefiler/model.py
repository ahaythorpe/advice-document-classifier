"""The objects that flow through the pipeline.

One record per document. Flags are attached to records rather than raised as
exceptions, because in this system a problem is an output, not a failure: the
review queue is a deliverable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from .classify import Classification
from .entities import ParsedDate
from .extract import ExtractedDocument
from .kb import KnowledgeBase

# How a flag is meant to be acted on. Read from the knowledge base
# (edge_case_flags.classes), never decided here.
PLACEMENT = "placement"
COMPLIANCE = "compliance"


class Flag(object):
    """One firing of one knowledge-base edge-case rule against one document."""

    def __init__(self, rule_id: str, severity: str, flag_class: str,
                 message: str, trigger: str = "", why: str = "") -> None:
        self.rule_id = rule_id
        self.severity = severity
        self.flag_class = flag_class
        self.message = message
        self.trigger = trigger
        self.why = why

    @classmethod
    def from_rule(cls, kb: KnowledgeBase, rule_id: str, message: str) -> "Flag":
        """Build a flag from its knowledge-base rule.

        Severity and class come from the rule, so retuning what a flag means is a
        knowledge-base edit. Asking for an unknown rule id raises: flags are
        domain facts and inventing one in code forks the source of truth.
        """
        rule = kb.flag_rule(rule_id)
        return cls(
            rule_id=rule_id,
            severity=rule.get("severity", "medium"),
            flag_class=rule.get("class", PLACEMENT),
            message=message,
            trigger=rule.get("trigger", ""),
            why=rule.get("why", ""),
        )

    @property
    def blocks_filing(self) -> bool:
        return self.flag_class == PLACEMENT

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<Flag %s %s %s>" % (self.rule_id, self.severity, self.flag_class)


class Record(object):
    """A document plus everything the pipeline worked out about it."""

    def __init__(self, document: ExtractedDocument,
                 classification: Classification) -> None:
        self.document = document
        self.classification = classification
        # Stable identity for integration: lets a destination recognise a
        # document it has already filed, so a re-run is idempotent rather than
        # a second copy. Content-based, so a renamed file is still the same
        # document and a re-scanned one is not.
        self.doc_id = document.content_id

        # Identity
        self.client_raw = None  # type: Optional[str]
        self.surnames = []  # type: List[str]
        self.family_key = None  # type: Optional[str]
        self.client_provenance = None  # type: Optional[str]

        # Dates
        self.own_date = None  # type: Optional[ParsedDate]
        self.date_provenance = ""
        self.referenced_dates = {}  # type: Dict[str, ParsedDate]

        # Type-specific extras
        self.risk_category = None  # type: Optional[str]
        self.product_tokens = set()  # type: Set[str]
        self.roa_sub_kind = None  # type: Optional[Dict[str, Any]]

        # Outcome
        self.flags = []  # type: List[Flag]
        self.event = None  # type: Optional[Any]
        self.attachment_reason = ""
        self.attachment_confidence = 0.0
        self.placement = None  # type: Optional[str]
        self.proposed_filename = None  # type: Optional[str]

    # -- proxies ------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.document.name

    @property
    def doc_type(self) -> Optional[str]:
        return self.classification.doc_type

    @property
    def confidence(self) -> float:
        return self.classification.confidence

    @property
    def text(self) -> str:
        return self.document.text

    # -- flags --------------------------------------------------------------

    def flag(self, kb: KnowledgeBase, rule_id: str, message: str) -> Flag:
        flag = Flag.from_rule(kb, rule_id, message)
        self.flags.append(flag)
        return flag

    @property
    def placement_flags(self) -> List[Flag]:
        return [f for f in self.flags if f.flag_class == PLACEMENT]

    @property
    def compliance_flags(self) -> List[Flag]:
        return [f for f in self.flags if f.flag_class == COMPLIANCE]

    @property
    def needs_review(self) -> bool:
        """Only placement flags stop a document being filed.

        A risk-profile mismatch is a real finding, but the document it sits on is
        correctly identified and correctly placed. Sending it to _Needs review
        would bury good work under a question that is not about filing, and a
        review queue nobody trusts is the same as no review queue.
        """
        return bool(self.placement_flags)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<Record %s %s conf=%.2f>" % (self.name, self.doc_type, self.confidence)
