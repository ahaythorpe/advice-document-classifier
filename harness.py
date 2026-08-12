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
import sys
from typing import List, Optional

from advicefiler import evaluate, extract, integrate, pipeline, report
from advicefiler.classify import KeywordClassifier
from advicefiler.kb import KnowledgeBase, KnowledgeBaseError
from advicefiler.profiles import FilingProfile, ProfileError, available

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
    return p


def load_documents(args):
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


def do_integration(args, result) -> int:
    """Exports, then preflight, then filing. Returns an exit code."""
    if args.export_manifest:
        print("manifest : %s" % integrate.write_manifest(result, args.export_manifest))
    if args.export_csv:
        print("csv      : %s" % integrate.write_csv(result, args.export_csv))
    if args.export_script:
        root = args.dest_root or "/PATH/TO/CLIENTS"
        print("script   : %s" % integrate.write_script(
            result, args.export_script, root, args.script_shell))
    if args.emit_approvals:
        path = integrate.write_approvals(result, args.emit_approvals)
        print("approvals: %s" % path)
        print("           edit 'decision' to \"approve\", then re-run with "
              "--approved %s --dest-root DIR" % path)

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
        mirrored = backup.mirror(applied, dry_run=not args.commit)
        print()
        print(mirrored.summary())

    if not args.commit:
        print()
        print("dry run — nothing was written. Re-run with --commit to file.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

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

    result = pipeline.run(kb, documents, classifier=KeywordClassifier(kb),
                          extraction_failures=failures, profile=profile)

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
        return do_integration(args, result)
    except integrate.IntegrationError as exc:
        print("integration error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
