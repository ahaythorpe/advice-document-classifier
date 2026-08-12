"""Access to knowledge_base.json — the single source of truth.

Nothing in this package may hardcode a document type, a weight, a threshold or a
flag rule. If a value is a domain fact, it lives in the knowledge base and is
read through here. The knowledge base states this itself (meta.consumers: "do
not fork copies into the UI or classifier"), and it is what lets the DBFO
SOA -> CAR transition land as a data change rather than a rewrite.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KB_PATH = os.path.join(os.path.dirname(_PACKAGE_DIR), "knowledge_base.json")


class KnowledgeBaseError(RuntimeError):
    """The knowledge base is missing something the pipeline needs."""


class KnowledgeBase(object):
    """A loaded knowledge base, indexed for lookup."""

    def __init__(self, data: Dict[str, Any], path: Optional[str] = None) -> None:
        self.data = data
        self.path = path
        self.by_id = {}  # type: Dict[str, Dict[str, Any]]
        for doc in data.get("documents", []):
            self.by_id[doc["id"]] = doc
        if not self.by_id:
            raise KnowledgeBaseError("knowledge base contains no documents")

    # -- loading ------------------------------------------------------------

    @classmethod
    def load(cls, path: Optional[str] = None) -> "KnowledgeBase":
        path = path or DEFAULT_KB_PATH
        if not os.path.exists(path):
            raise KnowledgeBaseError("knowledge base not found at %s" % path)
        with open(path, "r") as fh:
            return cls(json.load(fh), path=path)

    # -- meta ---------------------------------------------------------------

    @property
    def version(self) -> str:
        return self.data.get("meta", {}).get("version", "unknown")

    @property
    def documents(self) -> List[Dict[str, Any]]:
        return self.data.get("documents", [])

    def doc(self, doc_id: str) -> Dict[str, Any]:
        try:
            return self.by_id[doc_id]
        except KeyError:
            raise KnowledgeBaseError("unknown document type %r" % doc_id)

    def name(self, doc_id: Optional[str]) -> str:
        if doc_id is None:
            return "unidentified"
        return self.by_id.get(doc_id, {}).get("name", doc_id)

    def abbrev(self, doc_id: Optional[str]) -> str:
        if doc_id is None:
            return "UNKNOWN"
        entry = self.by_id.get(doc_id, {})
        return entry.get("abbrev", doc_id.upper()).replace(" ", "")

    # -- roles --------------------------------------------------------------
    # Keyed on advice_record_role, never on the literal id "soa". The knowledge
    # base is explicit that CAR shares this role precisely so that reform lands
    # as a relabelling. Anything matching on ids reintroduces the coupling.

    @property
    def advice_record_ids(self) -> List[str]:
        return [d["id"] for d in self.documents if d.get("advice_record_role")]

    def is_advice_record(self, doc_id: Optional[str]) -> bool:
        if doc_id is None:
            return False
        return bool(self.by_id.get(doc_id, {}).get("advice_record_role"))

    def category(self, doc_id: Optional[str]) -> Optional[str]:
        if doc_id is None:
            return None
        return self.by_id.get(doc_id, {}).get("category")

    def is_client_specific(self, doc_id: Optional[str]) -> bool:
        """False for documents that never carry a client name (FSG, PDS)."""
        if doc_id is None:
            return True
        return bool(self.by_id.get(doc_id, {}).get("client_specific", True))

    def requires_date(self, doc_id: Optional[str]) -> bool:
        if doc_id is None:
            return False
        return bool(self.by_id.get(doc_id, {}).get("requires_date", False))

    def date_role(self, doc_id: Optional[str]) -> str:
        if doc_id is None:
            return "client_event"
        return self.by_id.get(doc_id, {}).get("date_role", "client_event")

    def hints(self, doc_id: str) -> Dict[str, Any]:
        return self.doc(doc_id).get("classifier_hints", {})

    # -- scoring ------------------------------------------------------------

    @property
    def _scoring(self) -> Dict[str, Any]:
        scoring = self.data.get("scoring")
        if not scoring:
            raise KnowledgeBaseError(
                "knowledge base has no 'scoring' block; expected v0.4 or later "
                "(found v%s)" % self.version
            )
        return scoring

    @property
    def weights(self) -> Dict[str, float]:
        return self._scoring["weights"]

    @property
    def title_head_chars(self) -> int:
        return int(self._scoring["title_position"].get("head_chars", 300))

    @property
    def short_pattern_max_length(self) -> int:
        return int(self._scoring["short_pattern_rule"].get("max_length", 4))

    @property
    def confidence_threshold(self) -> float:
        return float(self._scoring["confidence"]["threshold"])

    @property
    def evidence_floor(self) -> float:
        return float(self._scoring["confidence"]["evidence_floor"])

    # -- taxonomies ---------------------------------------------------------

    @property
    def subjects(self) -> List[Dict[str, Any]]:
        return self.data.get("advice_subjects", {}).get("subjects", [])

    @property
    def risk_categories(self) -> List[str]:
        return self.data.get("risk_categories", {}).get("values", [])

    @property
    def flag_rules(self) -> List[Dict[str, Any]]:
        return self.data.get("edge_case_flags", {}).get("rules", [])

    def flag_rule(self, rule_id: str) -> Dict[str, Any]:
        for rule in self.flag_rules:
            if rule["id"] == rule_id:
                return rule
        raise KnowledgeBaseError(
            "flag rule %r is not defined in the knowledge base. Flags are domain "
            "facts: add the rule to edge_case_flags.rules rather than inventing "
            "one in code." % rule_id
        )

    @property
    def special_folders(self) -> List[Dict[str, Any]]:
        return self.data.get("filing_model", {}).get("special_folders", [])

    def special_folder_name(self, contains: str) -> str:
        """Look up a special-folder name by a distinctive substring."""
        for folder in self.special_folders:
            if contains.lower() in folder["name"].lower():
                return folder["name"]
        raise KnowledgeBaseError(
            "no special folder matching %r in filing_model.special_folders" % contains
        )

    @property
    def dbfo_t1_consent_commencement(self) -> Optional[str]:
        watch = self.data.get("reform_watch", {}).get("dbfo_tranche_1", {})
        return watch.get("consent_regime_commencement")
