"""Arranging classified, grouped documents into a folder plan.

filing_model.build_note: "Client-outer/event-inner is a nesting rule over results
already produced. Keep the storage layer abstracted so the folder scheme (and
later, local-folder vs cloud-bucket) can change without touching the classifier."

So a plan is data. Nothing here touches the filesystem. Writing is a separate,
later, human-approved act, and build step 5 (the approve/edit/reject UI) is what
turns a plan into one.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .events import AdviceEvent, GroupingResult
from .kb import KnowledgeBase
from .model import Record
from .naming import client_folder_name, event_folder_name, proposed_filename


class PlannedFile(object):
    """One document and where the tool proposes it should go."""

    def __init__(self, record: Record, folder: Tuple[str, ...], filename: str,
                 rationale: str, confidence: float) -> None:
        self.record = record
        self.folder = folder
        self.filename = filename
        self.rationale = rationale
        self.confidence = confidence

    @property
    def path(self) -> str:
        return "/".join(self.folder + (self.filename,))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<PlannedFile %s -> %s>" % (self.record.name, self.path)


class FolderPlan(object):
    """The proposed tree. A proposal, never an action."""

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb
        self.files = []  # type: List[PlannedFile]
        self._used = {}  # type: Dict[str, int]

    def add(self, record: Record, folder: Tuple[str, ...], filename: str,
            rationale: str, confidence: float) -> PlannedFile:
        filename = self._deduplicate(folder, filename)
        planned = PlannedFile(record, folder, filename, rationale, confidence)
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

    # -- views --------------------------------------------------------------

    def tree(self) -> Dict[str, List[PlannedFile]]:
        """Grouped by folder path, ordered for printing."""
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
    """Where an approved plan would be written.

    Phase 1 has exactly one target and it refuses to write. That is deliberate:
    SYSTEM.md section 1 says the tool never files silently, and the approve /
    edit / reject step that would authorise a write is build step 5. A local
    target and an Australian-region cloud target both implement this interface
    later without the classifier or the grouper knowing which is in use.
    """

    name = "abstract"

    def commit(self, plan: FolderPlan) -> None:
        raise NotImplementedError


class ProposalOnlyTarget(StorageTarget):
    name = "proposal-only (nothing is written)"

    def commit(self, plan: FolderPlan) -> None:
        raise NotImplementedError(
            "Phase 1 does not write files. A plan becomes a set of moves only "
            "after a human approves it, which is build step 5 (approve/edit/"
            "reject UI). Committing before then would be exactly the silent "
            "filing SYSTEM.md forbids."
        )


# ---------------------------------------------------------------------------
# Building the plan
# ---------------------------------------------------------------------------

def build_plan(kb: KnowledgeBase, records: List[Record],
               grouping: GroupingResult,
               batch_client: Optional[str] = None) -> FolderPlan:
    plan = FolderPlan(kb)
    review_folder = kb.special_folder_name("Needs review")
    client_level_folder = kb.special_folder_name("Client-level")
    licensee_folder = kb.special_folder_name("Licensee")

    events_by_key = {}  # type: Dict[str, AdviceEvent]
    for event in grouping.events:
        events_by_key[event.key] = event

    for record in records:
        client_specific = kb.is_client_specific(record.doc_type)

        # 1. Anything not confidently placed goes to review, under its client
        #    where one is known so a reviewer works one file at a time.
        if record.needs_review:
            reasons = "; ".join(f.message for f in record.placement_flags)
            folder = (client_folder_name(record.family_key), review_folder) \
                if record.family_key else (review_folder,)
            plan.add(record, folder,
                     proposed_filename(kb, record, client_specific),
                     reasons, record.confidence)
            continue

        # 2. Placed in an advice event.
        if record.event is not None:
            folder = (client_folder_name(record.event.family_key),
                      event_folder_name(kb, record.event))
            plan.add(record, folder,
                     proposed_filename(kb, record, client_specific),
                     record.attachment_reason,
                     record.attachment_confidence or record.confidence)
            continue

        # 3. Not client-specific and not tied to an event. An FSG belongs to the
        #    relationship, so it sits at client level when the batch identifies
        #    one client; otherwise it is licensee material, not an orphan.
        if not client_specific:
            if batch_client:
                plan.add(record, (client_folder_name(batch_client), client_level_folder),
                         proposed_filename(kb, record, False),
                         "not client-specific; assigned to the only client in this "
                         "intake batch (inherited, not read from the document)",
                         0.5)
            else:
                plan.add(record, (licensee_folder,),
                         proposed_filename(kb, record, False),
                         "licensee-wide document, editioned by date rather than "
                         "belonging to any one client",
                         record.confidence)
            continue

        # 4. Client-specific, has a client, but belongs to no single event.
        if record.family_key:
            plan.add(record, (client_folder_name(record.family_key), client_level_folder),
                     proposed_filename(kb, record, True),
                     "tied to the client but not to any single advice event",
                     record.confidence)
            continue

        plan.add(record, (review_folder,),
                 proposed_filename(kb, record, client_specific),
                 "no client and no advice event", record.confidence)

    return plan
