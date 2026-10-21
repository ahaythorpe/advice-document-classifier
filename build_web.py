#!/usr/bin/env python3
"""Build the static demonstration site.

    python3 build_web.py && vercel deploy web --prod

Runs the pipeline over the synthetic samples once per filing profile and writes
the results as JSON beside a single HTML page. The output is entirely static:
no server, no API, no upload control.

That is the point. A hosted version of the real tool would mean uploading client
files to somebody else's computer, which is a data-residency decision for the
licensee rather than a deployment choice (docs/DEPLOYMENT.md). So the public
version is a demonstration on fabricated documents with nowhere to put a real
one — not a disabled upload button, no upload button.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil

from advicefiler import extract, integrate, pipeline
from advicefiler.kb import KnowledgeBase
from advicefiler.profiles import FilingProfile, available

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "web")

# The page itself is a React app in web-react/, built to one self-contained HTML
# file (npm run build). Its only placeholder is __DATA__. The built template is
# committed so this script still runs with nothing but Python.
TEMPLATE = os.path.join(HERE, "web-react", "dist", "index.html")

# The sample sets a visitor can switch between. The fabricated folder is always
# built; the public one only when its PDFs are on this machine (they are not in
# git), so the page shows that set's results, never the documents themselves.
FABRICATED = ("fabricated", "Fabricated client folder",
              "Ten made-up documents for one invented household, written to show "
              "the whole flow: grouping, findings, and what gets held for review.")
PUBLIC = ("public", "Public sample PDFs",
          "Real PDFs that issuers publish: ASIC's annotated example SOAs and ROAs, "
          "blank fact-find and risk-profile templates, super fund PDSs, plus "
          "synthetic mocks for documents no one publishes. Blank templates name "
          "no client and carry no date, so the tool holds them all for review "
          "rather than guess where they belong. No client documents.")


def _plain(value):
    """The page uses no em or en dashes; the pipeline's own messages do."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, str):
        return value.replace(" \u2014 ", "; ").replace("\u2014", "-").replace("\u2013", "-")
    return value


def _dataset(kb, documents, key, label, note):
    """Run one batch under every filing profile, stripped for a public page."""
    profiles = {}
    for name in available():
        profile = FilingProfile.load(name)
        result = pipeline.run(kb, copy.deepcopy(documents), profile=profile)
        data = integrate.manifest(result)
        # Nothing about the machine that built this belongs in a public page.
        for doc in data["documents"]:
            doc.pop("source_path", None)
        data["batch"].pop("unreadable", None)
        data["generated"] = None
        data["profile_name"] = profile.name
        data["profile_description"] = profile.description
        data["dataset"], data["dataset_label"], data["dataset_note"] = key, label, note
        profiles[name] = _plain(data)
    return profiles


def build(public_samples=None) -> None:
    kb = KnowledgeBase.load()
    with open(os.path.join(HERE, "sample_documents.json")) as fh:
        records = json.load(fh)["documents"]

    payload = {FABRICATED[0]: _dataset(kb, extract.from_sample_records(records), *FABRICATED)}
    if public_samples:
        documents, failures = extract.extract_directory(public_samples, recursive=True)
        documents = [d for d in documents if d.name.lower().endswith(".pdf")]
        unread = [f for f in failures if f["file"].lower().endswith(".pdf")]
        if unread:
            raise SystemExit("could not read: %s" % unread)
        payload[PUBLIC[0]] = _dataset(kb, documents, *PUBLIC)

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as fh:
        with open(TEMPLATE, encoding="utf-8") as tf:
            page = tf.read()
        assert page.count("__DATA__") == 1, "web-react template must hold one __DATA__"
        # "</" inside the JSON would end the inline <script> early.
        fh.write(page.replace("__DATA__", json.dumps(payload, ensure_ascii=False)
                                              .replace("</", "<\\/")))
    with open(os.path.join(OUT, "vercel.json"), "w") as fh:
        json.dump({
            "$schema": "https://openapi.vercel.sh/vercel.json",
            "headers": [{
                "source": "/(.*)",
                "headers": [
                    {"key": "X-Content-Type-Options", "value": "nosniff"},
                    {"key": "X-Frame-Options", "value": "DENY"},
                    {"key": "Referrer-Policy", "value": "no-referrer"},
                    {"key": "Content-Security-Policy",
                     "value": "default-src 'none'; style-src 'unsafe-inline'; "
                              "script-src 'unsafe-inline'; base-uri 'none'; "
                              "form-action 'none'; frame-ancestors 'none'"},
                ],
            }],
        }, fh, indent=2)

    size = os.path.getsize(os.path.join(OUT, "index.html"))
    print("web/index.html  %.1f KB, %s, no server, no upload"
          % (size / 1024.0, ", ".join("%s: %d documents" % (k, next(iter(v.values()))["batch"]["documents"])
                                      for k, v in payload.items())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--public-samples", metavar="DIR",
                        help="folder of public sample PDFs to add as a second set")
    build(parser.parse_args().public_samples)
