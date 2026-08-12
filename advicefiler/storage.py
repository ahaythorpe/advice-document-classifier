"""Arranging classified, grouped documents into a folder plan.

filing_model.build_note: "Keep the storage layer abstracted so the folder scheme
(and later, local-folder vs cloud-bucket) can change without touching the
classifier."

So a plan is data, and the scheme that shapes it is a FilingProfile loaded from
JSON. Nothing here touches a filesystem or an API. Writing lives in integrate.py
and is gated on human approval.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .events import GroupingResult
from .kb import KnowledgeBase
from .model import Record
from .profiles import FilingProfile


class PlannedFile(object):
    """One document and where the tool proposes it should go."""

    def __init__(self, record: Record, folder: Tuple[str, ...], filename: str,
                 rationale: str, confidence: float, kind: str) -> None:
        self.record = record
        self.folder = folder
        self.filename = filename
        self.rationale = rationale
        self.confidence = confidence
        self.kind = kind

    @property
    def path(self) -> str:
        return "/".join(self.folder + (self.filename,))

    def __repr__(self) -> str:  # pragma: no cover
        return "<PlannedFile %s -> %s>" % (self.record.name, self.path)


class FolderPlan(object):
    """The proposed tree. A proposal, never an action."""

    def __init__(self, kb: KnowledgeBase, profile: FilingProfile) -> None:
        self.kb = kb
        self.profile = profile
        self.files = []  # type: List[PlannedFile]
        self._used = {}  # type: Dict[str, int]

    def add(self, record: Record, folder: Tuple[str, ...], filename: str,
            rationale: str, confidence: float, kind: str) -> PlannedFile:
        filename = self._deduplicate(folder, filename)
        planned = PlannedFile(record, folder, filename, rationale, confidence, kind)
        record.placement = "/".join(folder)
        record.proposed_filename = filename
        self.files.append(planned)
        return planned

    def _deduplicate(self, folder: Tuple[str, ...], filename: str) -> str:
        """Two documents proposing the same name must not silently collide."""
        key = "/".join(folder + (filename.lower(),))
        if key not in self._used:
            self._used[key] = 1
            return filename
        self._used[key] += 1
        stem, _, extension = filename.rpartition(".")
        if not stem:
            return "%s (%d)" % (filename, self._used[key])
        return "%s (%d).%s" % (stem, self._used[key], extension)

    def tree(self) -> Dict[str, List[PlannedFile]]:
        grouped = {}  # type: Dict[str, List[PlannedFile]]
        for planned in self.files:
            grouped.setdefault("/".join(planned.folder), []).append(planned)
        return grouped

    @property
    def filed(self) -> List[PlannedFile]:
        return [f for f in self.files if not f.record.needs_review]

    @property
    def for_review(self) -> List[PlannedFile]:
        return [f for f in self.files if f.record.needs_review]


class StorageTarget(object):
    """Legacy marker for a destination. See integrate.DestinationAdapter."""

    name = "abstract"

    def commit(self, plan: FolderPlan) -> None:
        raise NotImplementedError


class ProposalOnlyTarget(StorageTarget):
    name = "proposal-only (nothing is written)"

    def commit(self, plan: FolderPlan) -> None:
        raise NotImplementedError(
            "A plan becomes a set of moves only after a human approves it. Use "
            "integrate.LocalFolderDestination with an approvals file, or build "
            "step 5's UI. Committing a whole plan unreviewed would be exactly "
            "the silent filing SYSTEM.md forbids."
        )


# ---------------------------------------------------------------------------

def build_plan(kb: KnowledgeBase, records: List[Record],
               grouping: GroupingResult,
               batch_client: Optional[str] = None,
               profile: Optional[FilingProfile] = None) -> FolderPlan:
    profile = profile or FilingProfile.load()
    plan = FolderPlan(kb, profile)

    for record in records:
        client_specific = kb.is_client_specific(record.doc_type)
        extension = _extension(record.name)
        ctx = profile.context(kb, record, record.event)

        # 1. Anything not confidently placed goes to review, under its client
        #    where one is known so a reviewer works one file at a time.
        if record.needs_review:
            reasons = "; ".join(f.message for f in record.placement_flags)
            kind = "review_with_client" if record.family_key else "review_without_client"
            name_kind = "client_document" if (client_specific and record.family_key) \
                else "licensee_document"
            plan.add(record, profile.folder_path(kind, ctx),
                     profile.file_name(name_kind, ctx, extension),
                     reasons, record.confidence, kind)
            continue

        # 2. Placed in an advice event.
        if record.event is not None:
            plan.add(record, profile.folder_path("event_document", ctx),
                     profile.file_name(
                         "client_document" if client_specific else "licensee_document",
                         ctx, extension),
                     record.attachment_reason,
                     record.attachment_confidence or record.confidence,
                     "event_document")
            continue

        # 3. Not client-specific and not tied to an event. An FSG belongs to the
        #    relationship, so it sits at client level when the batch identifies
        #    one client; otherwise it is licensee material, not an orphan.
        if not client_specific:
            if batch_client:
                record.family_key = record.family_key or batch_client
                ctx = profile.context(kb, record, None)
                plan.add(record, profile.folder_path("client_level_document", ctx),
                         profile.file_name("licensee_document", ctx, extension),
                         "not client-specific; assigned to the only client in this "
                         "intake batch (inherited, not read from the document)",
                         0.5, "client_level_document")
            else:
                plan.add(record, profile.folder_path("licensee_document", ctx),
                         profile.file_name("licensee_document", ctx, extension),
                         "licensee-wide document, editioned by date rather than "
                         "belonging to any one client",
                         record.confidence, "licensee_document")
            continue

        # 4. Client-specific, has a client, but belongs to no single event.
        if record.family_key:
            plan.add(record, profile.folder_path("client_level_document", ctx),
                     profile.file_name("client_document", ctx, extension),
                     "tied to the client but not to any single advice event",
                     record.confidence, "client_level_document")
            continue

        plan.add(record, profile.folder_path("review_without_client", ctx),
                 profile.file_name("licensee_document", ctx, extension),
                 "no client and no advice event", record.confidence,
                 "review_without_client")

    return plan


def _extension(name: str) -> str:
    import os
    return os.path.splitext(name)[1]
