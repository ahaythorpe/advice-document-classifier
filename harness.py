#!/usr/bin/env python3
"""Advice-file classification and nested-filing harness (Phase 1, local, no cloud).

Run it with no arguments and it works the way it always did — the ten synthetic
documents in sample_documents.json, straight through the pipeline, no
dependencies required:

    python3 harness.py

Point it at a folder of real PDFs and Word files (build step 3) and it takes the
identical path, having read them first:

    python3 harness.py --input input/smith-family
    python3 harness.py --input input/smith-family --ground-truth input/ground_truth.json

Sweep the confidence threshold against ground truth:

    python3 harness.py --calibrate

Nothing is ever written to the proposed tree. The tool proposes; a human
approves, edits or rejects. Filing is build step 5.

The v0 keyword prototype is preserved at legacy/harness_v0.py so the before and
after can be compared on the same inputs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from advicefiler import evaluate, extract, pipeline, report
from advicefiler.classify import KeywordClassifier
from advicefiler.kb import KnowledgeBase, KnowledgeBaseError

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SAMPLES = os.path.join(HERE, "sample_documents.json")
DEFAULT_GROUND_TRUTH = os.path.join(HERE, "ground_truth.json")
DEFAULT_LOG = os.path.join(HERE, "output", "failure_log.jsonl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify and file Australian financial-advice documents.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", metavar="DIR",
                        help="folder of real documents (one intake batch). "
                             "Defaults to the synthetic samples.")
    parser.add_argument("--samples", default=DEFAULT_SAMPLES, metavar="PATH",
                        help="sample document JSON (default: sample_documents.json)")
    parser.add_argument("--kb", default=None, metavar="PATH",
                        help="knowledge base path (default: knowledge_base.json)")
    parser.add_argument("--ground-truth", default=None, metavar="PATH",
                        help="labelled correct answers. Defaults to ground_truth.json "
                             "for the samples; supply your own for real documents "
                             "(keep it under input/, which git ignores).")
    parser.add_argument("--display", choices=[report.NEW_TO_INDUSTRY, report.EXPERIENCED],
                        default=report.EXPERIENCED,
                        help="how much each document card teaches (SYSTEM.md section 2)")
    parser.add_argument("--threshold", type=float, default=None, metavar="F",
                        help="override the knowledge base's confidence threshold "
                             "for this run only")
    parser.add_argument("--calibrate", action="store_true",
                        help="re-run the pipeline across a range of thresholds and "
                             "recommend one (needs ground truth)")
    parser.add_argument("--failure-log", default=DEFAULT_LOG, metavar="PATH",
                        help="append the failure log here (default: output/failure_log.jsonl)")
    parser.add_argument("--no-log", action="store_true",
                        help="do not write a failure log")
    parser.add_argument("--quiet-tree", action="store_true",
                        help="skip the folder tree (useful when calibrating)")
    return parser


def load_documents(args: argparse.Namespace) -> tuple:
    if args.input:
        documents, failures = extract.extract_directory(args.input)
        if not documents and not failures:
            print("no supported documents found in %s" % args.input, file=sys.stderr)
        return documents, failures
    with open(args.samples, "r") as fh:
        payload = json.load(fh)
    return extract.from_sample_records(payload["documents"]), []


def resolve_ground_truth(args: argparse.Namespace) -> Optional[evaluate.GroundTruth]:
    path = args.ground_truth
    if path is None and not args.input and os.path.exists(DEFAULT_GROUND_TRUTH):
        path = DEFAULT_GROUND_TRUTH
    if not path:
        return None
    if not os.path.exists(path):
        print("ground truth not found: %s" % path, file=sys.stderr)
        return None
    return evaluate.GroundTruth.load(path)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        kb = KnowledgeBase.load(args.kb)
    except KnowledgeBaseError as exc:
        print("knowledge base error: %s" % exc, file=sys.stderr)
        return 2

    if args.threshold is not None:
        kb.data["scoring"]["confidence"]["threshold"] = args.threshold

    try:
        documents, failures = load_documents(args)
    except extract.ExtractionError as exc:
        print("extraction error: %s" % exc, file=sys.stderr)
        return 2

    result = pipeline.run(kb, documents, classifier=KeywordClassifier(kb),
                          extraction_failures=failures)

    report.print_header(result, extract.backend_status())
    report.print_scorecard(result, args.display)
    report.print_events(result)
    if not args.quiet_tree:
        report.print_tree(result, args.display)
    report.print_flags(result)
    report.print_coverage(kb)

    truth = resolve_ground_truth(args)
    if truth is None:
        print("=" * 78)
        print("NO GROUND TRUTH")
        print("=" * 78)
        print("Without labelled correct answers there is no failure log and no")
        print("way to calibrate confidence — SYSTEM.md section 8 needs the")
        print("correct-answer column. Label this batch and pass --ground-truth.")
        print()
        return 0

    comparisons = evaluate.compare(result, truth)
    if not comparisons:
        print("ground truth has no labels matching these documents", file=sys.stderr)
        return 1

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
