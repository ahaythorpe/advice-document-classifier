"""Connecting to what the firm already runs.

Three things have to be true for this tool to be usable inside a firm.

**It must not own the filing system.** The firm has one. So the destination is an
adapter, the folder scheme is a profile, and the plan is data that something else
can act on. A firm that wants nothing but the manifest can take the manifest.

**Desktop first, cloud as backup.** Advisers file to a local or network drive and
that is where the working copy lives. Cloud is a second copy, verified by hash,
never the primary. This also happens to be how OneDrive, SharePoint, Dropbox and
Google Drive already appear on an adviser's machine — as a sync folder — so the
same local adapter reaches them without an API, a token, or an integration
project.

**Nothing is written without a human decision.** Approvals are a file: emit it,
edit it, apply it. That is the approve/edit/reject loop of build step 5 in the
crudest possible form, and it keeps the guarantee that nothing is ever filed
silently.

Data residency: SYSTEM.md section 10 defers Australian data residency to pilot
stage, which is fine while nothing leaves the building. A cloud destination
leaves the building, so it must declare its region and this module refuses to
write to one that has not.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import json
import os
import shutil
from typing import Any, Dict, List, Optional, Tuple

from .pipeline import PipelineResult
from .storage import FolderPlan, PlannedFile

MANIFEST_SCHEMA = "advicefiler/manifest@1"
APPROVAL_SCHEMA = "advicefiler/approvals@1"
STATE_DIR = "_advicefiler"

APPROVE, REJECT, PENDING = "approve", "reject", "pending"

# Regions that satisfy an Australian advice firm's residency expectation.
AU_REGIONS = ("ap-southeast-2", "ap-southeast-4", "australiaeast",
              "australiasoutheast", "australia-southeast1",
              "australia-southeast2", "au", "australia")


class IntegrationError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Manifest — the machine-readable contract
# ---------------------------------------------------------------------------

def _event_id(event: Any) -> str:
    return "evt-%s" % hashlib.sha1(event.key.encode("utf-8")).hexdigest()[:10]


def manifest(result: PipelineResult) -> Dict[str, Any]:
    """Everything a downstream system needs, in one document.

    This is the integration surface. A firm that never runs our writer still gets
    a complete, typed description of what was found and what is proposed, keyed
    by a stable content id so it can be reconciled across runs.
    """
    kb = result.kb
    events = []
    ids = {}
    for event in (result.grouping.events if result.grouping else []):
        eid = _event_id(event)
        ids[event.key] = eid
        events.append({
            "event_id": eid,
            "client": event.family_key,
            "date": event.date.isoformat() if event.date else None,
            "subject": event.subject_label,
            "record_type": event.record_type,
            "record_label": kb.abbrev(event.record_type),
            "sub_kind": event.sub_kind_label,
            "anchor_doc_id": event.anchor.doc_id,
            "member_doc_ids": [m.doc_id for m in event.members],
        })

    plan_by_record = {}
    for planned in (result.plan.files if result.plan else []):
        plan_by_record[id(planned.record)] = planned

    documents = []
    for record in result.records:
        planned = plan_by_record.get(id(record))
        documents.append({
            "doc_id": record.doc_id,
            "source_name": record.name,
            "source_path": record.document.source_path,
            "extracted_by": record.document.backend,
            "pages": record.document.page_count,
            "type": record.doc_type,
            "type_label": kb.abbrev(record.doc_type),
            "category": kb.category(record.doc_type),
            "confidence": record.confidence,
            "classification_evidence": record.classification.why(),
            "extraction_quality": record.document.quality.score,
            "extraction_issues": record.document.quality.reasons,
            "client": record.family_key,
            "client_provenance": record.client_provenance,
            "date": record.own_date.iso() if record.own_date else None,
            "date_provenance": record.date_provenance,
            "event_id": ids.get(record.event.key) if record.event else None,
            "attachment_reason": record.attachment_reason,
            "attachment_confidence": record.attachment_confidence,
            "needs_review": record.needs_review,
            "flags": [{"id": f.rule_id, "severity": f.severity,
                       "class": f.flag_class, "blocks_filing": f.blocks_filing,
                       "message": f.message} for f in record.flags],
            "destination": {
                "folder": list(planned.folder),
                "filename": planned.filename,
                "path": planned.path,
                "kind": planned.kind,
                "rationale": planned.rationale,
            } if planned else None,
        })

    return {
        "schema": MANIFEST_SCHEMA,
        "generated": result.started.isoformat() if result.started else None,
        "knowledge_base_version": kb.version,
        "classifier": result.classifier_name,
        "filing_profile": result.profile.id if result.profile else None,
        "confidence_threshold": kb.confidence_threshold,
        "batch": {
            "client": result.batch_client,
            "documents": len(result.records),
            "auto_filed": len(result.plan.filed) if result.plan else 0,
            "needs_review": len(result.plan.for_review) if result.plan else 0,
            "unreadable": result.extraction_failures,
        },
        "events": events,
        "documents": documents,
    }


def write_manifest(result: PipelineResult, path: str) -> str:
    _ensure_parent(path)
    with open(path, "w") as fh:
        json.dump(manifest(result), fh, indent=2, sort_keys=False)
        fh.write("\n")
    return path


CSV_COLUMNS = ["doc_id", "source_name", "source_path", "type", "type_label",
               "confidence", "client", "date", "event_id", "destination_folder",
               "destination_filename", "needs_review", "flags", "rationale"]


def write_csv(result: PipelineResult, path: str) -> str:
    """Flat export, for the many systems whose import step is a spreadsheet."""
    data = manifest(result)
    _ensure_parent(path)
    with open(path, "w") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for doc in data["documents"]:
            dest = doc.get("destination") or {}
            writer.writerow({
                "doc_id": doc["doc_id"],
                "source_name": doc["source_name"],
                "source_path": doc["source_path"] or "",
                "type": doc["type"] or "",
                "type_label": doc["type_label"],
                "confidence": doc["confidence"],
                "client": doc["client"] or "",
                "date": doc["date"] or "",
                "event_id": doc["event_id"] or "",
                "destination_folder": "/".join(dest.get("folder", [])),
                "destination_filename": dest.get("filename", ""),
                "needs_review": "yes" if doc["needs_review"] else "no",
                "flags": "; ".join(f["id"] for f in doc["flags"]),
                "rationale": dest.get("rationale", ""),
            })
    return path


# ---------------------------------------------------------------------------
# Approvals — the human decision, as a file
# ---------------------------------------------------------------------------

def write_approvals(result: PipelineResult, path: str) -> str:
    """Emit a decision sheet: every document pending, with its proposal.

    Editing `decision` to "approve" authorises that one document. Editing
    `folder` or `filename` corrects the proposal before it is applied — which is
    the "edit" in approve/edit/reject, available before the UI exists.

    Documents queued for review default to `reject` rather than `pending`, so
    the safe outcome is the one you get by doing nothing.
    """
    data = manifest(result)
    items = []
    for doc in data["documents"]:
        dest = doc.get("destination") or {}
        items.append({
            "doc_id": doc["doc_id"],
            "source_name": doc["source_name"],
            "decision": REJECT if doc["needs_review"] else PENDING,
            "folder": "/".join(dest.get("folder", [])),
            "filename": dest.get("filename", ""),
            "_type": doc["type_label"],
            "_confidence": doc["confidence"],
            "_why": dest.get("rationale", ""),
            "_flags": [f["id"] for f in doc["flags"]],
        })
    payload = {
        "schema": APPROVAL_SCHEMA,
        "generated": data["generated"],
        "filing_profile": data["filing_profile"],
        "instructions": (
            "Set decision to 'approve' for each document you want filed. Edit "
            "folder or filename to correct a proposal. Fields beginning with an "
            "underscore are context and are ignored on apply. Nothing is written "
            "for documents left pending or rejected."),
        "items": items,
    }
    _ensure_parent(path)
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    return path


def load_approvals(path: str) -> Dict[str, Dict[str, Any]]:
    with open(path, "r") as fh:
        payload = json.load(fh)
    if payload.get("schema") != APPROVAL_SCHEMA:
        raise IntegrationError("%s is not an %s file" % (path, APPROVAL_SCHEMA))
    out = {}
    for item in payload.get("items", []):
        out[item["doc_id"]] = item
    return out


# ---------------------------------------------------------------------------
# Preflight — catch what a destination will reject, before touching it
# ---------------------------------------------------------------------------

class Issue(object):
    def __init__(self, level: str, doc_id: str, message: str) -> None:
        self.level = level
        self.doc_id = doc_id
        self.message = message

    def __repr__(self) -> str:  # pragma: no cover
        return "<%s %s: %s>" % (self.level.upper(), self.doc_id, self.message)


def preflight(result: PipelineResult, root: Optional[str] = None) -> List[Issue]:
    """Check the plan against the profile's limits and the destination's state.

    Path length is the one that bites in practice. A nested client/event scheme
    under a deep network share, synced to SharePoint which URL-encodes every
    space, overruns limits that look generous on paper — and the failure arrives
    halfway through a batch, not at the start.
    """
    issues = []  # type: List[Issue]
    plan = result.plan
    profile = result.profile
    if plan is None or profile is None:
        return [Issue("error", "-", "no plan to check")]

    seen = {}  # type: Dict[str, str]
    for planned in plan.files:
        doc_id = planned.record.doc_id
        full = os.path.join(root, *planned.folder) if root else "/".join(planned.folder)
        full = os.path.join(full, planned.filename)

        if len(full) > profile.max_path_chars:
            issues.append(Issue(
                "error", doc_id,
                "path is %d characters, over the %s profile limit of %d: %s"
                % (len(full), profile.id, profile.max_path_chars, full)))

        illegal = set(planned.filename) & set(profile.illegal)
        if illegal:
            issues.append(Issue("error", doc_id,
                                "filename contains %s, illegal for this profile"
                                % ", ".join(sorted(illegal))))

        key = full.lower()
        if key in seen:
            issues.append(Issue("error", doc_id,
                                "collides with %s at %s" % (seen[key], full)))
        seen[key] = planned.record.name

        if planned.record.document.source_path is None:
            issues.append(Issue(
                "warning", doc_id,
                "%s has no source file on disk (synthetic sample); it can be "
                "exported but not filed" % planned.record.name))

        if root and os.path.exists(full):
            issues.append(Issue("warning", doc_id,
                                "destination already exists: %s" % full))
    return issues


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------

class AppliedItem(object):
    def __init__(self, doc_id: str, source: str, destination: str,
                 action: str, note: str = "") -> None:
        self.doc_id = doc_id
        self.source = source
        self.destination = destination
        self.action = action     # filed | skipped | already-filed | failed | rejected
        self.note = note


class ApplyResult(object):
    def __init__(self, destination: str, dry_run: bool) -> None:
        self.destination = destination
        self.dry_run = dry_run
        self.items = []  # type: List[AppliedItem]

    def count(self, action: str) -> int:
        return sum(1 for i in self.items if i.action == action)

    def summary(self) -> str:
        return ("%s%s: %d filed, %d already filed, %d skipped, %d rejected, %d failed"
                % (self.destination, " (dry run)" if self.dry_run else "",
                   self.count("filed"), self.count("already-filed"),
                   self.count("skipped"), self.count("rejected"),
                   self.count("failed")))


class DestinationAdapter(object):
    """What a filing destination must implement.

    Implement this for Xplan, SharePoint's Graph API, Virtual Cabinet, iManage,
    an S3 bucket, or anything else. `apply` receives the plan and the human's
    approvals and is responsible for idempotency — the same batch applied twice
    must not produce two copies. See docs/INTEGRATION.md.
    """

    name = "abstract"
    is_cloud = False

    def apply(self, plan: FolderPlan, approvals: Dict[str, Dict[str, Any]],
              dry_run: bool = True) -> ApplyResult:
        raise NotImplementedError


class LocalFolderDestination(DestinationAdapter):
    """The primary: a desktop folder, a network drive, or a cloud sync folder.

    OneDrive, SharePoint-synced libraries, Dropbox and Google Drive all present
    as ordinary directories on an adviser's machine, so this one adapter reaches
    all of them with no API and no credentials. That is deliberately the first
    integration: it works on day one in a firm that will not approve an
    integration project.
    """

    name = "local folder"

    def __init__(self, root: str, mode: str = "copy") -> None:
        if mode not in ("copy", "move"):
            raise IntegrationError("mode must be copy or move, not %r" % mode)
        self.root = os.path.abspath(root)
        self.mode = mode

    # -- idempotency state --------------------------------------------------

    @property
    def _state_path(self) -> str:
        return os.path.join(self.root, STATE_DIR, "filed.json")

    def _load_state(self) -> Dict[str, str]:
        try:
            with open(self._state_path, "r") as fh:
                return json.load(fh)
        except (IOError, ValueError):
            return {}

    def _save_state(self, state: Dict[str, str]) -> None:
        _ensure_parent(self._state_path)
        with open(self._state_path, "w") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)

    def _audit(self, rows: List[Dict[str, Any]]) -> None:
        path = os.path.join(self.root, STATE_DIR, "audit.jsonl")
        _ensure_parent(path)
        with open(path, "a") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")

    # -- apply --------------------------------------------------------------

    def apply(self, plan: FolderPlan, approvals: Dict[str, Dict[str, Any]],
              dry_run: bool = True) -> ApplyResult:
        result = ApplyResult("%s -> %s" % (self.name, self.root), dry_run)
        state = self._load_state()
        audit = []  # type: List[Dict[str, Any]]
        stamp = datetime.datetime.now().isoformat()

        for planned in plan.files:
            record = planned.record
            doc_id = record.doc_id
            decision = approvals.get(doc_id, {})
            verdict = decision.get("decision", PENDING)

            if verdict != APPROVE:
                result.items.append(AppliedItem(
                    doc_id, record.name, "", "rejected" if verdict == REJECT else "skipped",
                    "decision is %r" % verdict))
                continue

            source = record.document.source_path
            if not source or not os.path.exists(source):
                result.items.append(AppliedItem(
                    doc_id, record.name, "", "failed",
                    "no source file on disk"))
                continue

            # A human may have corrected the destination in the approvals file.
            folder = decision.get("folder") or "/".join(planned.folder)
            filename = decision.get("filename") or planned.filename
            target = os.path.join(self.root, *[p for p in folder.split("/") if p])
            target = os.path.join(target, filename)

            if state.get(doc_id) == target and os.path.exists(target):
                result.items.append(AppliedItem(
                    doc_id, source, target, "already-filed",
                    "same content id already at this path"))
                continue

            if os.path.exists(target):
                if _same_content(source, target):
                    state[doc_id] = target
                    result.items.append(AppliedItem(
                        doc_id, source, target, "already-filed",
                        "identical file already present"))
                    continue
                result.items.append(AppliedItem(
                    doc_id, source, target, "failed",
                    "a different file already exists at this path; not overwriting"))
                continue

            if dry_run:
                result.items.append(AppliedItem(doc_id, source, target, "filed",
                                                "dry run — nothing written"))
                continue

            try:
                _ensure_parent(target)
                if self.mode == "move":
                    shutil.move(source, target)
                else:
                    shutil.copy2(source, target)
            except (IOError, OSError) as exc:
                result.items.append(AppliedItem(doc_id, source, target, "failed",
                                                str(exc)))
                continue

            state[doc_id] = target
            result.items.append(AppliedItem(doc_id, source, target, "filed", self.mode))
            audit.append({"at": stamp, "doc_id": doc_id, "action": self.mode,
                          "source": source, "destination": target,
                          "type": record.doc_type, "client": record.family_key,
                          "confidence": record.confidence})

        if not dry_run:
            self._save_state(state)
            if audit:
                self._audit(audit)
        return result


class CloudBackupDestination(LocalFolderDestination):
    """A second, verified copy. Never the working copy.

    Backup is a mirror of what was actually filed, taken after the primary
    succeeded, and every file is verified by hash after writing. A backup nobody
    has verified is a belief, not a backup.

    `region` is required and must be Australian. SYSTEM.md section 10 defers data
    residency to pilot stage, which holds only while client files stay in the
    building; a cloud copy is the moment that stops being true. Refusing here is
    cheaper than discovering it during a licensee audit.
    """

    name = "cloud backup"
    is_cloud = True

    def __init__(self, root: str, region: str, allow_non_au: bool = False) -> None:
        LocalFolderDestination.__init__(self, root, mode="copy")
        region_key = (region or "").strip().lower()
        if not region_key:
            raise IntegrationError(
                "a cloud backup destination must declare its region. Client "
                "files leaving the building is exactly what SYSTEM.md section 10 "
                "defers to pilot stage.")
        if region_key not in AU_REGIONS and not allow_non_au:
            raise IntegrationError(
                "region %r is not an Australian region (%s). Backing an advice "
                "firm's client files to offshore storage is a data-residency "
                "decision for the licensee, not a default. Pass "
                "allow_non_au=True only with that decision recorded."
                % (region, ", ".join(AU_REGIONS[:4])))
        self.region = region

    def mirror(self, applied: ApplyResult, primary_root: str,
               dry_run: bool = True) -> ApplyResult:
        """Copy what the primary actually filed, then verify each copy.

        The mirror is computed against the primary's root, so the backup is the
        same tree. An earlier version kept the last three path segments, which
        happened to work for a three-level profile and silently dropped the
        client folder for anything deeper — putting two clients' documents in
        one backup folder.
        """
        primary_root = os.path.abspath(primary_root)
        result = ApplyResult("%s -> %s (%s)" % (self.name, self.root, self.region),
                             dry_run)
        state = self._load_state()
        for item in applied.items:
            if item.action not in ("filed", "already-filed") or not item.destination:
                continue
            if not os.path.exists(item.destination):
                result.items.append(AppliedItem(item.doc_id, item.destination, "",
                                                "skipped", "primary file missing"))
                continue
            relative = os.path.relpath(os.path.abspath(item.destination),
                                       primary_root)
            if relative.startswith(os.pardir):
                result.items.append(AppliedItem(
                    item.doc_id, item.destination, "", "failed",
                    "filed outside the primary root; refusing to guess where it "
                    "belongs in the backup"))
                continue
            target = os.path.join(self.root, relative)

            if os.path.exists(target) and _same_content(item.destination, target):
                result.items.append(AppliedItem(item.doc_id, item.destination,
                                                target, "already-filed", "verified"))
                continue
            if dry_run:
                result.items.append(AppliedItem(item.doc_id, item.destination,
                                                target, "filed", "dry run"))
                continue
            try:
                _ensure_parent(target)
                shutil.copy2(item.destination, target)
            except (IOError, OSError) as exc:
                result.items.append(AppliedItem(item.doc_id, item.destination,
                                                target, "failed", str(exc)))
                continue
            if not _same_content(item.destination, target):
                result.items.append(AppliedItem(item.doc_id, item.destination,
                                                target, "failed",
                                                "hash mismatch after copy"))
                continue
            state[item.doc_id] = target
            result.items.append(AppliedItem(item.doc_id, item.destination, target,
                                            "filed", "verified"))
        if not dry_run:
            self._save_state(state)
        return result


# ---------------------------------------------------------------------------
# Script export — for firms whose IT will not run our writer
# ---------------------------------------------------------------------------

def write_script(result: PipelineResult, path: str, root: str,
                 shell: str = "bash") -> str:
    """Emit the approved moves as a script a firm's IT can read before running.

    Some firms will not let an unfamiliar tool write to the document store, and
    that is a reasonable position. A reviewable script gets the same work done
    through a channel they already trust.
    """
    plan = result.plan
    lines = []
    if shell == "powershell":
        lines += ["# Generated by advicefiler. Review before running.",
                  "$ErrorActionPreference = 'Stop'"]
        mk, cp = "New-Item -ItemType Directory -Force -Path %s | Out-Null", "Copy-Item -LiteralPath %s -Destination %s"
        quote = lambda s: "'%s'" % s.replace("'", "''")
    else:
        lines += ["#!/usr/bin/env bash",
                  "# Generated by advicefiler. Review before running.",
                  "set -euo pipefail"]
        mk, cp = 'mkdir -p %s', "cp -n %s %s"
        quote = lambda s: "'%s'" % s.replace("'", "'\\''")

    made = set()
    for planned in (plan.files if plan else []):
        if planned.record.needs_review:
            lines.append("# SKIPPED (needs review): %s — %s"
                         % (planned.record.name, planned.rationale))
            continue
        source = planned.record.document.source_path
        if not source:
            lines.append("# SKIPPED (no source file): %s" % planned.record.name)
            continue
        folder = os.path.join(root, *planned.folder)
        if folder not in made:
            lines.append(mk % quote(folder))
            made.add(folder)
        lines.append(cp % (quote(source), quote(os.path.join(folder, planned.filename))))

    _ensure_parent(path)
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    if shell != "powershell":
        os.chmod(path, 0o755)
    return path


# ---------------------------------------------------------------------------

def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same_content(a: str, b: str) -> bool:
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        return _hash_file(a) == _hash_file(b)
    except (IOError, OSError):
        return False

