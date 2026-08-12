"""Folder and file names, both read from the knowledge base's patterns.

v0 printed the anchor's raw date string as the event label ("14 March 2024
[SOA]") and never proposed a filename at all, although SYSTEM.md section 1
promises both a destination and a rename.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from .events import AdviceEvent
from .kb import KnowledgeBase
from .model import Record

# Characters that are illegal or merely painful in a folder name on Windows,
# macOS or a cloud bucket key. Firms open these trees in Explorer and Finder.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitise(fragment: str, max_length: int = 80) -> str:
    cleaned = _UNSAFE.sub("", fragment or "").strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip()
    return cleaned or "unnamed"


def client_folder_name(family_key: Optional[str]) -> str:
    return sanitise(family_key or "_Unidentified client")


def event_folder_name(kb: KnowledgeBase, event: AdviceEvent) -> str:
    """Per filing_model.advice_event.naming_pattern:

        YYYY-MM - <subject matter> [<record type>  <sub-kind if ROA>]
    """
    when = event.date.strftime("%Y-%m") if event.date else "undated"
    label = kb.abbrev(event.record_type)
    if event.sub_kind_label:
        label = "%s · %s" % (label, event.sub_kind_label)
    return sanitise("%s — %s [%s]" % (when, event.subject_label, label), 120)


def proposed_filename(kb: KnowledgeBase, record: Record,
                      client_specific: bool = True) -> str:
    """Per filing_model.filename_pattern. The original extension is kept."""
    pattern = kb.data.get("filing_model", {}).get("filename_pattern", {})
    undated = pattern.get("undated_prefix", "undated")
    when = record.own_date.iso() if record.own_date else undated
    abbrev = kb.abbrev(record.doc_type)
    extension = os.path.splitext(record.name)[1] or ""

    if client_specific and record.family_key:
        stem = "%s - %s - %s" % (when, record.family_key, abbrev)
    else:
        stem = "%s - %s" % (when, abbrev)
    return sanitise(stem, 120) + extension.lower()
