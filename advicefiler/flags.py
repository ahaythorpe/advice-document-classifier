"""Step 4 of the four steps: file or flag.

Every rule in ``edge_case_flags.rules`` gets an implementation registered here
under its knowledge-base id. ``coverage()`` compares the registry against the
knowledge base and reports which rules are not implemented, so a gap in the
safety net is visible in the run output rather than being invisible by
construction. v0 implemented four of eleven rules and said nothing about the
other seven; a reviewer reading its clean output would reasonably have assumed
it had checked.

Flags never reclassify and never move a document on their own. Placement flags
route to _Needs review; compliance flags ride along with a correctly filed
document. Which is which is a knowledge-base fact.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import clients
from .entities import parse_date
from .events import AdviceEvent, GroupingResult
from .kb import KnowledgeBase
from .model import Record

RuleFn = Callable[..., None]
_REGISTRY = {}  # type: Dict[str, RuleFn]


def rule(rule_id: str) -> Callable[[RuleFn], RuleFn]:
    def register(fn: RuleFn) -> RuleFn:
        _REGISTRY[rule_id] = fn
        return fn
    return register


class Context(object):
    """Everything a rule may look at."""

    def __init__(self, kb: KnowledgeBase, records: List[Record],
                 grouping: GroupingResult,
                 batch_client: Optional[str] = None) -> None:
        self.kb = kb
        self.records = records
        self.grouping = grouping
        self.events = grouping.events
        self.batch_client = batch_client

    def events_for(self, family_key: Optional[str]) -> List[AdviceEvent]:
        return [e for e in self.events if e.family_key == family_key]

    def unanchored_reason(self, record: Record) -> Optional[str]:
        for rec, reason in self.grouping.unanchored:
            if rec is record:
                return reason
        return None


# ---------------------------------------------------------------------------
# Type-level rules
# ---------------------------------------------------------------------------

@rule("unknown_type")
def _unknown_type(ctx: Context) -> None:
    for record in ctx.records:
        if record.doc_type is None:
            detail = ""
            if record.document.quality.reasons:
                detail = " Extraction quality %.2f: %s." % (
                    record.document.quality.score,
                    "; ".join(record.document.quality.reasons))
            record.flag(ctx.kb, "unknown_type",
                        "no document type matched with sufficient evidence." + detail)


@rule("low_confidence")
def _low_confidence(ctx: Context) -> None:
    threshold = ctx.kb.confidence_threshold
    for record in ctx.records:
        if record.doc_type is None or record.confidence >= threshold:
            continue
        detail = "best guess %s at %.2f, below the %.2f threshold" % (
            ctx.kb.abbrev(record.doc_type), record.confidence, threshold)
        if record.classification.capped_by_quality:
            detail += "; confidence capped by extraction quality (%.2f)" % (
                record.document.quality.score)
        runner = record.classification.runner_up
        if runner:
            detail += "; runner-up %s" % ctx.kb.abbrev(runner)
        record.flag(ctx.kb, "low_confidence", detail)


@rule("multi_doc_bundle")
def _multi_doc_bundle(ctx: Context) -> None:
    for record in ctx.records:
        titled = record.classification.title_position_types
        if len(titled) < 2:
            continue
        record.flag(ctx.kb, "multi_doc_bundle",
                    "%d document titles appear in title position (%s) — this file "
                    "probably contains more than one document and needs splitting "
                    "before its links are trustworthy"
                    % (len(titled), ", ".join(ctx.kb.abbrev(t) for t in titled)))


@rule("advice_record_label_shift")
def _label_shift(ctx: Context) -> None:
    for record in ctx.records:
        if not ctx.kb.is_advice_record(record.doc_type):
            continue
        runner = record.classification.runner_up
        if not runner or not ctx.kb.is_advice_record(runner):
            continue
        scores = record.classification.scores
        top, second = scores.get(record.doc_type or "", 0.0), scores.get(runner, 0.0)
        if top <= 0 or second < 0.7 * top:
            continue
        record.flag(ctx.kb, "advice_record_label_shift",
                    "plays the advice-record role but the statutory label is "
                    "ambiguous between %s (%.1f) and %s (%.1f)"
                    % (ctx.kb.abbrev(record.doc_type), top,
                       ctx.kb.abbrev(runner), second))


# ---------------------------------------------------------------------------
# Identity rules
# ---------------------------------------------------------------------------

@rule("no_date")
def _no_date(ctx: Context) -> None:
    for record in ctx.records:
        if record.doc_type is None or not ctx.kb.requires_date(record.doc_type):
            continue
        if record.own_date is not None:
            continue
        record.flag(ctx.kb, "no_date",
                    "a %s needs a date for sequencing and none could be read (%s)"
                    % (ctx.kb.abbrev(record.doc_type), record.date_provenance))


@rule("client_unidentified")
def _client_unidentified(ctx: Context) -> None:
    for record in ctx.records:
        if record.doc_type is None:
            continue
        if not ctx.kb.is_client_specific(record.doc_type):
            continue          # an FSG has no client because it never had one
        if record.family_key:
            continue
        if ctx.batch_client:
            # The batch pointing at one client is a strong hint, not a fact, and
            # it is deliberately not applied on its own. An advice record only
            # anchors an event on a client read from its own text; inheriting
            # here would build a whole event on an assumption, and every document
            # that then attached to it would inherit the assumption silently.
            detail = ("every other document in this batch is %s — confirm whether "
                      "this one is too" % ctx.batch_client)
        else:
            detail = "and the intake batch does not resolve to a single client"
        record.flag(ctx.kb, "client_unidentified",
                    "a %s is client-specific but no client name could be read; %s"
                    % (ctx.kb.abbrev(record.doc_type), detail))


@rule("client_ambiguous_match")
def _client_ambiguous_match(ctx: Context) -> None:
    for record in ctx.records:
        match = record.client_match
        if match is None or match.verdict != clients.AMBIGUOUS:
            continue
        record.flag(ctx.kb, "client_ambiguous_match",
                    "read the client as '%s', which %s"
                    % (record.client_raw or record.family_key, match.reason))


@rule("new_client_proposed")
def _new_client_proposed(ctx: Context) -> None:
    for record in ctx.records:
        match = record.client_match
        if match is None or match.verdict not in (clients.NEW, clients.UNCERTAIN):
            continue
        if match.verdict == clients.UNCERTAIN:
            detail = ("%s. Confirm whether that is the same client under a "
                      "different spelling, a married name, or one partner of the "
                      "household — or genuinely somebody new" % match.reason)
        else:
            detail = ("%s. Confirm this is a new client; approving adds them to "
                      "the register and no later document will ask again"
                      % match.reason)
        record.flag(ctx.kb, "new_client_proposed",
                    "'%s' is not in the client register — %s."
                    % (record.family_key or record.client_raw, detail))


@rule("superseding_ambiguity")
def _superseding_ambiguity(ctx: Context) -> None:
    buckets = {}  # type: Dict[Tuple[Any, ...], List[Record]]
    for record in ctx.records:
        if record.doc_type is None or record.needs_review:
            continue
        scope = record.event.subject_id if record.event else None
        key = (record.family_key, record.doc_type, scope,
               record.own_date.value if record.own_date else None)
        buckets.setdefault(key, []).append(record)

    for (family, doc_type, _scope, when), group in sorted(
            buckets.items(), key=lambda kv: [str(x) for x in kv[0]]):
        if len(group) < 2:
            continue
        where = "dated %s" % when.isoformat() if when else "both undated"
        for record in group:
            others = [r.name for r in group if r is not record]
            record.flag(ctx.kb, "superseding_ambiguity",
                        "%d %ss for %s %s (also: %s) — cannot tell which is current"
                        % (len(group), ctx.kb.abbrev(doc_type),
                           family or "an unidentified client", where, ", ".join(others)))


# ---------------------------------------------------------------------------
# Placement rules
# ---------------------------------------------------------------------------

@rule("atp_without_advice_record")
def _atp_without_advice_record(ctx: Context) -> None:
    for record in ctx.records:
        if ctx.kb.category(record.doc_type) != "implementation":
            continue
        if record.event is not None:
            continue
        reason = ctx.unanchored_reason(record)
        if reason is None:
            continue
        record.flag(ctx.kb, "atp_without_advice_record",
                    "authorises implementation of advice that is not in this batch: %s"
                    % reason)


@rule("event_ambiguous")
def _event_ambiguous(ctx: Context) -> None:
    for record, reason in ctx.grouping.unanchored:
        if record.event is not None:
            continue
        if ctx.kb.category(record.doc_type) == "implementation":
            continue          # handled by atp_without_advice_record
        if any(f.rule_id in ("no_date", "client_unidentified") for f in record.flags):
            continue          # the more specific cause is already on the record
        record.flag(ctx.kb, "event_ambiguous",
                    "cannot be attached to exactly one advice event: %s" % reason)


# ---------------------------------------------------------------------------
# Sequence and consistency rules
# ---------------------------------------------------------------------------

@rule("roa_without_soa")
def _roa_without_soa(ctx: Context) -> None:
    for record in ctx.records:
        if record.doc_type != "roa":
            continue
        if record.confidence < ctx.kb.confidence_threshold:
            continue
        sub_kind = record.roa_sub_kind
        if sub_kind is not None and not sub_kind.get("requires_prior_soa", False):
            continue          # a hold or small-investment ROA needs no prior SOA

        own = record.own_date.value if record.own_date else None
        priors = []
        for event in ctx.events_for(record.family_key):
            if event.anchor is record or event.date is None:
                continue
            if not ctx.kb.is_advice_record(event.record_type):
                continue
            if event.record_type == "roa":
                continue
            if own is None or event.date <= own:
                priors.append(event)
        if priors:
            continue

        if sub_kind is None:
            message = ("no prior full advice record on file for %s, and the text does "
                       "not say which of the four ROA kinds this is. Further advice "
                       "needs a prior SOA; hold, small-investment and no-buy/sell "
                       "ROAs do not. Confirm the kind." % (record.family_key or "this client"))
        else:
            message = ("identified as the %s kind, which depends on a prior SOA, but "
                       "no prior advice record is on file for %s"
                       % (sub_kind.get("label", "further advice"),
                          record.family_key or "this client"))
        record.flag(ctx.kb, "roa_without_soa", message)


@rule("fact_find_after_soa")
def _fact_find_after_soa(ctx: Context) -> None:
    for record in ctx.records:
        if ctx.kb.category(record.doc_type) != "input":
            continue
        if record.event is None or record.own_date is None:
            continue
        anchor_date = record.event.date
        if anchor_date is None or record.own_date.value <= anchor_date:
            continue
        gap = (record.own_date.value - anchor_date).days
        record.flag(ctx.kb, "fact_find_after_soa",
                    "dated %s, %d days AFTER the %s it feeds (%s) — the advice may "
                    "predate the information it was based on"
                    % (record.own_date.iso(), gap,
                       ctx.kb.abbrev(record.event.record_type), anchor_date.isoformat()))


@rule("risk_mismatch")
def _risk_mismatch(ctx: Context) -> None:
    for record in ctx.records:
        if record.doc_type != "risk_profile" or record.event is None:
            continue
        category = record.risk_category
        if not category:
            continue
        anchor = record.event.anchor
        if category.lower() in anchor.text.lower():
            continue
        record.flag(ctx.kb, "risk_mismatch",
                    "assessed the client as '%s', but that category does not appear "
                    "in the %s it feeds (%s). Check the recommendations match the "
                    "assessed tolerance."
                    % (category, ctx.kb.abbrev(record.event.record_type), anchor.name))


@rule("fds_era_mismatch")
def _fds_era_mismatch(ctx: Context) -> None:
    boundary_raw = ctx.kb.dbfo_t1_consent_commencement
    if not boundary_raw:
        return
    parsed = parse_date(boundary_raw)
    if parsed is None:
        return
    boundary = parsed.value

    for record in ctx.records:
        if ctx.kb.category(record.doc_type) != "ongoing_service":
            continue
        if record.own_date is None:
            continue
        era = ctx.kb.hints(record.doc_type or "").get("era_signals", {})
        low = record.text.lower()
        pre = [p for p in era.get("pre_dbfo_t1", []) if p.lower() in low]
        post = [p for p in era.get("post_dbfo_t1", []) if p.lower() in low]
        own = record.own_date.value

        problem = None
        if own >= boundary and pre and not post:
            problem = ("dated %s (on or after the DBFO Tranche 1 consent regime) but "
                       "carries pre-reform wording: %s" % (own.isoformat(), ", ".join(pre)))
        elif own < boundary and post and not pre:
            problem = ("dated %s (before the DBFO Tranche 1 consent regime) but carries "
                       "post-reform wording: %s" % (own.isoformat(), ", ".join(post)))
        if problem:
            record.flag(ctx.kb, "fds_era_mismatch",
                        problem + ". Note the commencement date used here (%s) is "
                        "marked UNVERIFIED in the knowledge base — confirm it before "
                        "treating this as a finding." % boundary.isoformat())


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

# Order matters only where one rule suppresses another (event_ambiguous defers to
# no_date and client_unidentified), so the specific causes run first.
_ORDER = [
    "unknown_type", "low_confidence", "multi_doc_bundle",
    "advice_record_label_shift", "no_date", "client_unidentified",
    "client_ambiguous_match", "new_client_proposed",
    "atp_without_advice_record", "event_ambiguous",
    "roa_without_soa", "fact_find_after_soa", "risk_mismatch",
    "fds_era_mismatch", "superseding_ambiguity",
]


def run_all(kb: KnowledgeBase, records: List[Record],
            grouping: GroupingResult,
            batch_client: Optional[str] = None) -> None:
    ctx = Context(kb, records, grouping, batch_client)
    for rule_id in _ORDER:
        _REGISTRY[rule_id](ctx)


def coverage(kb: KnowledgeBase) -> Dict[str, List[str]]:
    """Which knowledge-base rules have implementations, and which do not.

    Reported in every run. A rule defined in the domain model but not checked by
    the tool is a silent gap in the safety net, and silence is the failure mode
    this whole system is built to avoid.
    """
    defined = [r["id"] for r in kb.flag_rules]
    implemented = [r for r in defined if r in _REGISTRY]
    missing = [r for r in defined if r not in _REGISTRY]
    orphaned = [r for r in _REGISTRY if r not in defined]
    return {"implemented": implemented, "not_implemented": missing,
            "not_in_knowledge_base": orphaned}
