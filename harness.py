#!/usr/bin/env python3
"""Advice-file classification and nested-filing harness (Phase 1, local).

Classify and inspect:

    python3 harness.py                          # ten synthetic samples
    python3 harness.py --input input/smith      # a real intake batch
    python3 harness.py --calibrate              # sweep the confidence threshold
    python3 harness.py --list-profiles          # available filing schemes

Hand the result to whatever the firm already runs:

    python3 harness.py --input input/smith --profile category-flat \\
        --export-manifest out/manifest.json --export-csv out/plan.csv

File it, desktop first, with a human decision in between:

    python3 harness.py --input input/smith --emit-approvals out/approvals.json
    $EDITOR out/approvals.json                  # set decision to "approve"
    python3 harness.py --input input/smith --approved out/approvals.json \\
        --dest-root "/Volumes/Advice/Clients"   # dry run
    python3 harness.py --input input/smith --approved out/approvals.json \\
        --dest-root "/Volumes/Advice/Clients" --commit \\
        --backup-root ~/OneDrive/AdviceBackup --backup-region ap-southeast-2

Nothing is written without --commit, and nothing is written for a document the
approvals file does not approve. Filing to a real destination is build step 5;
this is its command-line form.

The v0 keyword prototype is preserved at legacy/harness_v0.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import List, Optional

from advicefiler import evaluate, extract, integrate, pipeline, report
from advicefiler.classify import KeywordClassifier
from advicefiler.kb import KnowledgeBase, KnowledgeBaseError
from advicefiler.clients import ClientEntry, ClientRegister
from advicefiler.profiles import FilingProfile, ProfileError, available
from advicefiler.security import harden, redact_manifest

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SAMPLES = os.path.join(HERE, "sample_documents.json")
DEFAULT_GROUND_TRUTH = os.path.join(HERE, "ground_truth.json")
DEFAULT_LOG = os.path.join(HERE, "output", "failure_log.jsonl")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Classify and file Australian financial-advice documents.",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    src = p.add_argument_group("input")
    src.add_argument("--input", metavar="DIR",
                     help="folder of real documents (one intake batch)")
    src.add_argument("--samples", default=DEFAULT_SAMPLES, metavar="PATH")
    src.add_argument("--kb", default=None, metavar="PATH")
    src.add_argument("--ground-truth", default=None, metavar="PATH")

    out = p.add_argument_group("output and display")
    out.add_argument("--display", choices=[report.NEW_TO_INDUSTRY, report.EXPERIENCED],
                     default=report.EXPERIENCED)
    out.add_argument("--threshold", type=float, default=None, metavar="F")
    out.add_argument("--calibrate", action="store_true")
    out.add_argument("--failure-log", default=DEFAULT_LOG, metavar="PATH")
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--quiet-tree", action="store_true")

    integ = p.add_argument_group("integration")
    integ.add_argument("--profile", default=None, metavar="NAME",
                       help="filing profile (default: nested-default)")
    integ.add_argument("--list-profiles", action="store_true")
    integ.add_argument("--export-manifest", metavar="PATH",
                       help="full machine-readable result for a downstream system")
    integ.add_argument("--export-csv", metavar="PATH")
    integ.add_argument("--export-script", metavar="PATH",
                       help="a reviewable copy script for the firm's IT to run")
    integ.add_argument("--script-shell", choices=["bash", "powershell"], default="bash")
    integ.add_argument("--emit-approvals", metavar="PATH",
                       help="write a decision sheet for a human to edit")
    integ.add_argument("--clients", metavar="PATH",
                       help="the firm's existing client list: a CSV or JSON "
                            "export, or a directory to read client folders from. "
                            "Without it, client matching is off and the name read "
                            "from the document is used as-is.")
    integ.add_argument("--emit-new-clients", metavar="PATH",
                       help="write the clients this batch would create, for "
                            "confirmation before they exist")
    integ.add_argument("--redact", action="store_true",
                       help="strip client names and paths from exported files, "
                            "keeping types, confidences, flags and structure")

    filing = p.add_argument_group("filing (desktop primary, cloud backup)")
    filing.add_argument("--dest-root", metavar="DIR",
                        help="primary destination: desktop, network drive, or a "
                             "cloud sync folder")
    filing.add_argument("--approved", metavar="PATH",
                        help="edited approvals file; required to file anything")
    filing.add_argument("--mode", choices=["copy", "move"], default="copy")
    filing.add_argument("--commit", action="store_true",
                        help="actually write. Without it, filing is a dry run.")
    filing.add_argument("--backup-root", metavar="DIR",
                        help="second, verified copy of what was filed")
    filing.add_argument("--backup-region", metavar="REGION",
                        help="required with --backup-root, e.g. ap-southeast-2")
    filing.add_argument("--allow-non-au-backup", action="store_true",
                        help="acknowledge backing up outside Australia")

    reorg = p.add_argument_group("reorganising an existing filed tree")
    reorg.add_argument("--reorganise", metavar="DIR",
                       help="read an already-filed client tree and propose a "
                            "re-filing. Implies recursive reading, uses the tree "
                            "itself as the client register, and moves rather than "
                            "copies. Documents already in the right place are not "
                            "touched; documents that cannot be placed confidently "
                            "are left exactly where they are.")
    reorg.add_argument("--undo", metavar="PATH",
                       help="a rollback file from a previous reorganisation")
    reorg.add_argument("--accept-new-clients", metavar="PATH",
                       help="an --emit-new-clients file with confirm set to true; "
                            "merges those clients into the register so their "
                            "documents can file")
    reorg.add_argument("--register-out", metavar="PATH",
                       help="where to write the grown register (default: in place)")
    return p


def load_documents(args):
    if args.reorganise:
        return extract.extract_directory(args.reorganise, recursive=True)
    if args.input:
        return extract.extract_directory(args.input)
    with open(args.samples, "r") as fh:
        payload = json.load(fh)
    return extract.from_sample_records(payload["documents"]), []


def resolve_ground_truth(args):
    path = args.ground_truth
    if path is None and not args.input and os.path.exists(DEFAULT_GROUND_TRUTH):
        path = DEFAULT_GROUND_TRUTH
    if not path:
        return None
    if not os.path.exists(path):
        print("ground truth not found: %s" % path, file=sys.stderr)
        return None
    return evaluate.GroundTruth.load(path)


def do_reorganise(args, result) -> int:
    """Report what would change in an existing filed tree, and optionally do it."""
    root = args.reorganise
    reorg = integrate.plan_reorganisation(result, root)

    print("=" * 78)
    print("REORGANISATION — %s" % root)
    print("=" * 78)
    print(reorg.summary())
    print()

    cross = reorg.cross_client_moves()
    if cross:
        print("MOVES THAT CHANGE CLIENT (%d) — read these first" % len(cross))
        for item in cross:
            print("  %s" % item["current"])
            print("    -> %s" % item["proposed"])
            print("       %s (%s, conf %.2f)"
                  % (item["note"], item["type"], item["confidence"]))
        print()

    other = [i for i in reorg.moves if i not in cross]
    if other:
        print("MOVES WITHIN THE SAME CLIENT (%d)" % len(other))
        for item in other[:40]:
            print("  %s\n    -> %s" % (item["current"], item["proposed"]))
        if len(other) > 40:
            print("  ... and %d more" % (len(other) - 40))
        print()

    left = [i for i in reorg.items if i["action"] == integrate.LEAVE]
    if left:
        print("LEFT WHERE THEY ARE (%d) — not confidently placed, not disturbed"
              % len(left))
        for item in left[:20]:
            print("  %-50s %s" % (item["current"][:50], item["note"][:60]))
        print()

    if not args.approved:
        print("Nothing has moved. To act on this:")
        print("  1. re-run with --emit-approvals out/approvals.json")
        print("  2. edit it — decision \"approve\" per document, or correct the "
              "destination")
        print("  3. re-run with --approved out/approvals.json          (dry run)")
        print("  4. re-run with --approved out/approvals.json --commit (moves)")
        print()
        return 0

    approvals = integrate.load_approvals(args.approved)
    if not reorg.approved_move_ids(approvals):
        print("no approved moves in %s" % args.approved)
        return 0

    rollback = None
    if args.commit:
        # Written BEFORE anything moves, so an interrupted run is still undoable.
        rollback = integrate.write_rollback(
            reorg.rollback_entries(approvals), root,
            evaluate.run_id(result.started))
        print("rollback file: %s" % rollback)

    destination = integrate.LocalFolderDestination(root, "move")
    applied = reorg.apply(result.plan, destination, approvals,
                          dry_run=not args.commit)
    print()
    print(applied.summary())
    if not args.commit:
        print("dry run — nothing moved. Add --commit to reorganise.")
    else:
        print("undo with:  python3 harness.py --undo %s --commit" % rollback)
    return 0


def do_accept_new_clients(args, kb) -> int:
    """Confirm proposed clients, so their documents can file on the next run."""
    with open(args.accept_new_clients, "r") as fh:
        payload = json.load(fh)
    rows = payload.get("clients", [])
    confirmed = [r for r in rows if r.get("confirm", True)]
    if not confirmed:
        print("no clients marked confirm: true in %s" % args.accept_new_clients)
        return 0
    if not args.clients:
        print("--accept-new-clients needs --clients (the register to grow)",
              file=sys.stderr)
        return 2

    register = ClientRegister.load(args.clients, kb)
    existing = set(e.folder_name for e in register.entries)
    added = 0
    for row in confirmed:
        row.pop("confirm", None)
        if row.get("folder_name") in existing:
            continue
        register.add(ClientEntry(**row))
        added += 1
    out = args.register_out or (args.clients if not os.path.isdir(args.clients)
                                else None)
    if out is None:
        print("--clients points at a directory; pass --register-out to say where "
              "the grown register should be written", file=sys.stderr)
        return 2
    register.save(out)
    print("register: %d client(s) added, %d total, written to %s"
          % (added, len(register), out))
    print("re-run without --accept-new-clients and their documents will file.")
    return 0


def _redaction_vocabulary(kb) -> List[str]:
    """Words that identify nobody and must survive redaction.

    All from closed sets in the knowledge base: document labels, advice subjects,
    special folder names. Keeping them is what makes a redacted manifest legible
    enough that people actually use it.
    """
    words = []
    for doc in kb.documents:
        words += [doc["id"], kb.abbrev(doc["id"]), doc.get("category") or ""]
        words += re.split(r"[\s/]+", doc.get("name", ""))
    for subject in kb.subjects:
        words += re.split(r"[\s/&]+", subject.get("label", ""))
    for folder in kb.special_folders:
        words += re.split(r"[\s/_]+", folder.get("name", ""))
    return [w for w in words if len(w) > 1]


def do_exports(args, result) -> None:
    """Manifest, CSV, script, approvals, proposed new clients."""
    if args.export_manifest:
        if args.redact:
            import json as _json
            data = redact_manifest(integrate.manifest(result),
                                   keep=_redaction_vocabulary(result.kb))
            integrate._ensure_parent(args.export_manifest)
            with open(args.export_manifest, "w") as fh:
                _json.dump(data, fh, indent=2)
                fh.write("\n")
            harden(args.export_manifest)
            print("manifest : %s (redacted)" % args.export_manifest)
        else:
            print("manifest : %s"
                  % integrate.write_manifest(result, args.export_manifest))
            harden(args.export_manifest)
    if args.export_csv:
        print("csv      : %s" % integrate.write_csv(result, args.export_csv))
    if args.export_script:
        root = args.dest_root or "/PATH/TO/CLIENTS"
        print("script   : %s" % integrate.write_script(
            result, args.export_script, root, args.script_shell))
    if args.emit_new_clients and result.new_clients:
        import json as _json
        integrate._ensure_parent(args.emit_new_clients)
        with open(args.emit_new_clients, "w") as fh:
            _json.dump({"clients": [dict(c.to_dict(), confirm=False)
                                    for c in result.new_clients]},
                       fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        harden(args.emit_new_clients)
        print("new clients: %d written to %s" % (len(result.new_clients),
                                                  args.emit_new_clients))
        print("             set \"confirm\": true on the real ones, then re-run "
              "with --accept-new-clients %s" % args.emit_new_clients)

    if args.emit_approvals:
        path = integrate.write_approvals(result, args.emit_approvals)
        print("approvals: %s" % path)
        print("           edit 'decision' to \"approve\", then re-run with "
              "--approved %s --dest-root DIR" % path)

def do_integration(args, result) -> int:
    """Preflight, then filing. Returns an exit code."""
    if not args.dest_root:
        return 0

    issues = integrate.preflight(result, args.dest_root)
    errors = [i for i in issues if i.level == "error"]
    if issues:
        print()
        print("PREFLIGHT (%d error, %d warning)"
              % (len(errors), len(issues) - len(errors)))
        for issue in issues:
            print("  %-7s %s" % (issue.level, issue.message))
    if errors:
        print()
        print("refusing to file with preflight errors outstanding", file=sys.stderr)
        return 1

    if not args.approved:
        print()
        print("--dest-root given but no --approved file. Nothing is filed without")
        print("a human decision. Run --emit-approvals first.", file=sys.stderr)
        return 1

    approvals = integrate.load_approvals(args.approved)
    primary = integrate.LocalFolderDestination(args.dest_root, args.mode)
    applied = primary.apply(result.plan, approvals, dry_run=not args.commit)
    print()
    print(applied.summary())
    for item in applied.items:
        if item.action in ("filed", "failed"):
            print("  %-13s %s" % (item.action, item.destination or item.source))
            if item.action == "failed":
                print("                %s" % item.note)

    if args.backup_root:
        try:
            backup = integrate.CloudBackupDestination(
                args.backup_root, args.backup_region or "",
                allow_non_au=args.allow_non_au_backup)
        except integrate.IntegrationError as exc:
            print("backup refused: %s" % exc, file=sys.stderr)
            return 1
        mirrored = backup.mirror(applied, args.dest_root,
                                 dry_run=not args.commit)
        print()
        print(mirrored.summary())

    if not args.commit:
        print()
        print("dry run — nothing was written. Re-run with --commit to file.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.undo:
        try:
            undone = integrate.undo(args.undo, dry_run=not args.commit)
        except (IOError, integrate.IntegrationError) as exc:
            print("undo failed: %s" % exc, file=sys.stderr)
            return 2
        print(undone.summary())
        for item in undone.items:
            print("  %-9s %s" % (item.action, item.destination or item.source))
        if not args.commit:
            print("\ndry run — nothing moved back. Add --commit to undo.")
        return 0

    if args.list_profiles:
        for name in available():
            profile = FilingProfile.load(name)
            print("%-20s %s" % (profile.id, profile.name))
            print("%-20s %s" % ("", profile.description))
            print()
        return 0

    try:
        kb = KnowledgeBase.load(args.kb)
        profile = FilingProfile.load(args.profile)
    except (KnowledgeBaseError, ProfileError) as exc:
        print("configuration error: %s" % exc, file=sys.stderr)
        return 2

    if args.threshold is not None:
        kb.data["scoring"]["confidence"]["threshold"] = args.threshold

    try:
        documents, failures = load_documents(args)
    except extract.ExtractionError as exc:
        print("extraction error: %s" % exc, file=sys.stderr)
        return 2

    if args.accept_new_clients:
        try:
            return do_accept_new_clients(args, kb)
        except (IOError, ValueError) as exc:
            print("could not accept new clients: %s" % exc, file=sys.stderr)
            return 2

    # Reorganising reads the tree it is about to rewrite, and uses that tree's
    # own client folders as the register — the firm's existing structure is the
    # thing being conformed to, not replaced.
    if args.reorganise and not args.clients:
        args.clients = args.reorganise

    register = None
    if args.clients:
        try:
            register = ClientRegister.load(args.clients, kb)
        except (IOError, ValueError, OSError) as exc:
            print("could not read client register %s: %s" % (args.clients, exc),
                  file=sys.stderr)
            return 2
        print("client register: %d existing clients from %s\n"
              % (len(register), args.clients))

    result = pipeline.run(kb, documents, classifier=KeywordClassifier(kb),
                          extraction_failures=failures, profile=profile,
                          register=register)

    report.print_header(result, extract.backend_status())
    report.print_scorecard(result, args.display)
    report.print_events(result)
    if not args.quiet_tree:
        report.print_tree(result, args.display)
    report.print_flags(result)
    report.print_coverage(kb)

    truth = resolve_ground_truth(args)
    if truth is not None:
        comparisons = evaluate.compare(result, truth)
        if comparisons:
            stats = evaluate.score(comparisons)
            report.print_failure_log(comparisons, stats)
            if not args.no_log:
                rows = evaluate.failure_log_rows(
                    comparisons, evaluate.run_id(result.started), kb.version,
                    result.classifier_name)
                if args.redact:
                    from advicefiler.security import redact_failure_row
                    rows = [redact_failure_row(r) for r in rows]
                path = evaluate.write_failure_log(rows, args.failure_log)
                print("failure log: %d row(s) appended to %s" % (len(rows), path))
                print()
            if args.calibrate:
                rows = evaluate.calibrate(kb, documents, truth)
                recommended, rationale = evaluate.recommend_threshold(rows)
                report.print_calibration(rows, recommended, rationale,
                                         kb.confidence_threshold)
    else:
        print("=" * 78)
        print("NO GROUND TRUTH — no failure log, no calibration. SYSTEM.md section")
        print("8 needs the correct-answer column. Label the batch and pass")
        print("--ground-truth.")
        print()

    try:
        do_exports(args, result)
        if args.reorganise:
            return do_reorganise(args, result)
        return do_integration(args, result)
    except integrate.IntegrationError as exc:
        print("integration error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
