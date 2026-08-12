"""Step 2 of the four steps: text -> (type, confidence).

Two things matter about this module.

**The interface is the contract.** ``Classifier.classify`` returns a
``Classification`` and nothing downstream knows or cares how it was produced.
Build step 4 replaces ``KeywordClassifier`` with an LLM reading the same
``classifier_hints``, and if this file is the only thing that changes, the swap
worked.

**The knowledge base is where fixes go.** Every weight, pattern and threshold
here is read from ``knowledge_base.json``. That is not tidiness — a fix made in
Python scoring evaporates at step 4, and a fix made in the knowledge base is
inherited by the LLM, because it reads the same entries. SYSTEM.md section 7
says to fix the SOA/ATP lookalike "in the knowledge base by weighting structural
signals over mentioned titles", and that is exactly what the v0.4 title-position
and reference-context rules do.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .extract import ExtractedDocument
from .kb import KnowledgeBase


class Classification(object):
    """What the classifier decided, and the evidence it decided on."""

    def __init__(
        self,
        doc_type: Optional[str],
        confidence: float,
        scores: Dict[str, float],
        evidence: Dict[str, List[str]],
        title_position_types: List[str],
        runner_up: Optional[str] = None,
        capped_by_quality: bool = False,
    ) -> None:
        self.doc_type = doc_type
        self.confidence = confidence
        self.scores = scores
        self.evidence = evidence
        self.title_position_types = title_position_types
        self.runner_up = runner_up
        self.capped_by_quality = capped_by_quality

    @property
    def top_score(self) -> float:
        return max(self.scores.values()) if self.scores else 0.0

    def why(self) -> str:
        """One line of evidence for the winning type — for the failure log."""
        if not self.doc_type:
            return "nothing scored above the evidence floor"
        return "; ".join(self.evidence.get(self.doc_type, [])) or "no evidence recorded"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<Classification %s conf=%.2f>" % (self.doc_type, self.confidence)


class Classifier(object):
    """Interface every classification engine implements.

    Build step 4 adds ``LLMClassifier(Classifier)`` beside ``KeywordClassifier``
    and changes one line in the pipeline. Downstream code must never branch on
    which engine is in use — SYSTEM.md section 2 keeps the engine independent of
    display mode and filing mode, and this is where that independence is kept.
    """

    name = "abstract"

    def classify(self, document: ExtractedDocument) -> Classification:
        raise NotImplementedError


class KeywordClassifier(Classifier):
    """Phase 1 stand-in: weighted pattern matching over the knowledge base."""

    name = "keyword"

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb
        self.weights = kb.weights
        self.head_chars = kb.title_head_chars
        self.short_max = kb.short_pattern_max_length
        self.evidence_floor = kb.evidence_floor
        self._compiled = {}  # type: Dict[str, Any]

    # -- pattern helpers ----------------------------------------------------

    def _pattern(self, phrase: str):
        """Compile a phrase, honouring the knowledge base's short-pattern rule.

        Abbreviations of four characters or fewer (SOA, ROA, CAR, FSG, PDS) match
        only as whole words in upper case. v0 matched them case-insensitively as
        substrings, so "CAR" hit "care" and every document became a candidate
        Client Advice Record.
        """
        key = phrase
        if key in self._compiled:
            return self._compiled[key]
        if len(phrase) <= self.short_max and phrase.isalpha():
            compiled = re.compile(r"\b%s\b" % re.escape(phrase.upper()))
        else:
            compiled = re.compile(re.escape(phrase), re.I)
        self._compiled[key] = compiled
        return compiled

    def _reference_spans(self, text: str, hints: Dict[str, Any]) -> List[Tuple[int, int]]:
        spans = []  # type: List[Tuple[int, int]]
        for phrase in hints.get("reference_patterns", []):
            for match in self._pattern(phrase).finditer(text):
                spans.append((match.start(), match.end()))
        return spans

    def _is_title_position(self, text: str, start: int, end: int) -> bool:
        """Is this occurrence worn as a title, or merely mentioned in prose?"""
        if start < self.head_chars:
            # Near the top of the document — but not if it is mid-sentence there,
            # which the reference-span check upstream has already ruled out.
            return True
        matched = text[start:end]
        if matched.isupper() and len(matched) > self.short_max:
            return True
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end].strip()
        if len(line) <= 80 and len(matched) >= 0.6 * max(1, len(line)):
            return True
        return False

    # -- scoring ------------------------------------------------------------

    def _score_type(self, text: str, doc_id: str
                    ) -> Tuple[float, List[str], bool]:
        hints = self.kb.hints(doc_id)
        score = 0.0
        evidence = []  # type: List[str]
        ref_spans = self._reference_spans(text, hints)

        # -- title patterns: position, not presence
        best_title = None  # type: Optional[str]
        best_mention = None  # type: Optional[str]
        for phrase in hints.get("title_patterns", []):
            for match in self._pattern(phrase).finditer(text):
                inside_reference = any(
                    s <= match.start() < e for s, e in ref_spans)
                if inside_reference:
                    best_mention = best_mention or phrase
                    continue
                if self._is_title_position(text, match.start(), match.end()):
                    best_title = phrase
                    break
                best_mention = best_mention or phrase
            if best_title:
                break

        has_title = best_title is not None
        if has_title:
            score += self.weights["title_in_title_position"]
            evidence.append("title '%s' in title position" % best_title)
        elif best_mention:
            score += self.weights["title_mentioned_in_body"]
            evidence.append("title '%s' only mentioned in body" % best_mention)

        # -- structural signals: how the document is built, not what it cites
        structural_hits = []  # type: List[str]
        for phrase in hints.get("structural_signals", []):
            if self._pattern(phrase).search(text):
                structural_hits.append(phrase)
        if structural_hits:
            score += self.weights["structural_signal"] * len(structural_hits)
            evidence.append("structural: %s" % ", ".join(
                "'%s'" % h for h in structural_hits[:4]))

        # -- key fields: weak corroboration only
        field_hits = []  # type: List[str]
        for field in hints.get("key_fields", []):
            cue = field.lower().split(" / ")[0].split(" (")[0].strip()
            if len(cue) < 4:
                continue
            if self._pattern(cue).search(text):
                field_hits.append(cue)
        if field_hits:
            score += self.weights["key_field"] * len(field_hits)
            evidence.append("fields: %s" % ", ".join(
                "'%s'" % h for h in field_hits[:3]))

        # -- negative signals
        negative_hits = []  # type: List[str]
        for phrase in hints.get("negative_signals", []):
            if self._pattern(phrase).search(text):
                negative_hits.append(phrase)
        if negative_hits:
            score += self.weights["negative_signal"] * len(negative_hits)
            evidence.append("against: %s" % ", ".join(
                "'%s'" % h for h in negative_hits))

        return max(0.0, score), evidence, has_title

    # -- public -------------------------------------------------------------

    def classify(self, document: ExtractedDocument) -> Classification:
        text = document.text
        scores = {}  # type: Dict[str, float]
        evidence = {}  # type: Dict[str, List[str]]
        title_types = []  # type: List[str]

        for doc in self.kb.documents:
            doc_id = doc["id"]
            score, why, has_title = self._score_type(text, doc_id)
            scores[doc_id] = round(score, 2)
            evidence[doc_id] = why
            if has_title and score >= self.evidence_floor:
                title_types.append(doc_id)

        if not scores or max(scores.values()) <= 0:
            return Classification(None, 0.0, scores, evidence, title_types)

        # Deterministic ordering: score first, then knowledge-base order as the
        # tie-break. v0 relied on dict iteration order alone, which is why a
        # 4-all tie between ATP and SOA silently resolved to SOA — the first
        # entry in the file, not the better answer.
        order = {doc["id"]: i for i, doc in enumerate(self.kb.documents)}
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], order[kv[0]]))
        best_id, top = ranked[0]
        runner_id, runner = (ranked[1] if len(ranked) > 1 else (None, 0.0))

        margin = (top - runner) / top if top else 0.0
        strength = min(1.0, top / self.evidence_floor) if self.evidence_floor else 1.0
        confidence = margin * strength

        # A document we could barely read cannot be classified confidently,
        # however well its noise happened to score. SYSTEM.md section 7: bad
        # scans must score low and flag, not classify confidently.
        capped = False
        if document.quality.score < confidence:
            confidence = document.quality.score
            capped = True

        if top < self.evidence_floor * 0.25:
            # Below a quarter of the floor there is no meaningful evidence for
            # any type; calling that a weak answer overstates it.
            return Classification(None, 0.0, scores, evidence, title_types,
                                  runner_up=runner_id, capped_by_quality=capped)

        return Classification(
            doc_type=best_id,
            confidence=round(min(1.0, max(0.0, confidence)), 2),
            scores=scores,
            evidence=evidence,
            title_position_types=title_types,
            runner_up=runner_id,
            capped_by_quality=capped,
        )
