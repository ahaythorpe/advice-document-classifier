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


def build() -> None:
    kb = KnowledgeBase.load()
    with open(os.path.join(HERE, "sample_documents.json")) as fh:
        records = json.load(fh)["documents"]

    payload = {}
    for name in available():
        profile = FilingProfile.load(name)
        documents = extract.from_sample_records(records)
        result = pipeline.run(kb, documents, profile=profile)
        data = integrate.manifest(result)
        # Nothing about the machine that built this belongs in a public page.
        for doc in data["documents"]:
            doc.pop("source_path", None)
        data["batch"].pop("unreadable", None)
        data["generated"] = None
        data["profile_name"] = profile.name
        data["profile_description"] = profile.description
        payload[name] = data

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
    print("web/index.html  %.1f KB, %d filing profiles, no server, no upload"
          % (size / 1024.0, len(payload)))


if __name__ == "__main__":
    build()
