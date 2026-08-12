"""Firm filing profiles.

No firm will adopt this tool's folder scheme. They already run Xplan,
AdviserLogic, Practifi, Virtual Cabinet, FYI, SharePoint or a decade-old folder
convention nobody is allowed to change. So the folder layout, filename pattern,
document vocabulary, character set and path limits are configuration, and the
classifier does not know which is in use.

A profile is a JSON file in profiles/. See docs/INTEGRATION.md.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional

PROFILE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")
DEFAULT_PROFILE = "nested-default"

# Illegal on Windows, macOS, and most DMS path APIs.
_BASE_ILLEGAL = '<>:"/\\|?*'


class ProfileError(RuntimeError):
    pass


class _Token(object):
    """A value that formats safely, including when it is missing."""

    def __init__(self, value: Any, fallback: str) -> None:
        self.value = value
        self.fallback = fallback

    def __format__(self, spec: str) -> str:
        if self.value is None:
            return self.fallback
        if spec and isinstance(self.value, (datetime.date, datetime.datetime)):
            return self.value.strftime(spec)
        return format(self.value, spec) if spec else str(self.value)

    def __str__(self) -> str:
        return self.__format__("")


class FilingProfile(object):
    def __init__(self, data: Dict[str, Any], path: Optional[str] = None) -> None:
        self.data = data
        self.path = path
        self.id = data.get("id", "unnamed")
        self.name = data.get("name", self.id)
        self.description = data.get("description", "")
        self.charset = data.get("charset", "unicode")
        self.max_path_chars = int(data.get("max_path_chars", 260))
        self.max_name_chars = int(data.get("max_name_chars", 120))
        self.illegal = _BASE_ILLEGAL + data.get("extra_illegal_chars", "")
        self.folders = data.get("folders", {})
        self.layout = data.get("layout", {})
        self.filename = data.get("filename", {})
        self.type_labels = data.get("type_labels", {})
        self.categories = data.get("categories", {})

    # -- loading ------------------------------------------------------------

    @classmethod
    def load(cls, name_or_path: Optional[str] = None) -> "FilingProfile":
        name_or_path = name_or_path or DEFAULT_PROFILE
        path = name_or_path
        if not os.path.exists(path):
            path = os.path.join(PROFILE_DIR, "%s.json" % name_or_path)
        if not os.path.exists(path):
            raise ProfileError(
                "no filing profile %r (looked in %s). Available: %s"
                % (name_or_path, PROFILE_DIR, ", ".join(available()) or "none"))
        with open(path, "r") as fh:
            return cls(json.load(fh), path=path)

    # -- sanitising ---------------------------------------------------------

    def clean(self, fragment: str, limit: Optional[int] = None) -> str:
        text = fragment or ""
        if self.charset == "ascii":
            text = (text.replace("—", "-").replace("–", "-").replace("·", "-")
                        .replace("’", "'").replace("“", '"').replace("”", '"'))
            text = unicodedata.normalize("NFKD", text)
            text = text.encode("ascii", "ignore").decode("ascii")
        text = "".join(ch for ch in text
                       if ch not in self.illegal and ord(ch) >= 32)
        text = re.sub(r"\s+", " ", text).strip().strip(".")
        limit = limit or self.max_name_chars
        if len(text) > limit:
            text = text[:limit].rstrip()
        return text or "unnamed"

    # -- rendering ----------------------------------------------------------

    def _render(self, template: str, ctx: Dict[str, Any]) -> str:
        try:
            return template.format(**ctx)
        except (KeyError, ValueError) as exc:
            raise ProfileError(
                "profile %s: cannot render %r (%s)" % (self.id, template, exc))

    def context(self, kb: Any, record: Any, event: Any = None) -> Dict[str, Any]:
        """Tokens available to every folder and filename template."""
        undated = self.filename.get("undated", "undated")
        doc_type = getattr(record, "doc_type", None)
        label = self.type_labels.get(doc_type) or kb.abbrev(doc_type)
        category = (self.categories.get(doc_type)
                    or kb.category(doc_type) or "Other")
        own = getattr(record, "own_date", None)
        # An event document takes its client from the event, not the record: a
        # PDS carries no client name of its own but belongs to the event's.
        client = getattr(record, "family_key", None)
        if event is not None and getattr(event, "family_key", None):
            client = event.family_key
        ctx = {
            "client": _Token(client, "_Unidentified client"),
            "date": _Token(own.value if own else None, undated),
            "type_label": _Token(label, "UNKNOWN"),
            "type_id": _Token(doc_type, "unknown"),
            "category": _Token(category, "Other"),
            "original": _Token(os.path.splitext(getattr(record, "name", ""))[0], "document"),
            "doc_id": _Token(getattr(record, "doc_id", None), "nodocid"),
            "subject": _Token(None, "Advice"),
            "sub_kind": _Token(None, ""),
            "event_date": _Token(None, undated),
        }
        if event is not None:
            ctx["subject"] = _Token(getattr(event, "subject_label", None), "Advice")
            ctx["event_date"] = _Token(event.date, undated)
            anchor_label = (self.type_labels.get(event.record_type)
                            or kb.abbrev(event.record_type))
            ctx["record_label"] = _Token(anchor_label, "UNKNOWN")
            ctx["sub_kind"] = _Token(event.sub_kind_label, "")
            # Ready-to-interpolate, so a template need not branch on presence.
            suffix = (" · %s" % event.sub_kind_label) if event.sub_kind_label else ""
            ctx["sub_kind_suffix"] = _Token(suffix or None, "")
        else:
            ctx["record_label"] = _Token(None, "UNKNOWN")
            ctx["sub_kind_suffix"] = _Token(None, "")
        return ctx

    def folder_name(self, key: str, ctx: Dict[str, Any]) -> str:
        template = self.folders.get(key)
        if template is None:
            raise ProfileError("profile %s has no folder template %r" % (self.id, key))
        return self.clean(self._render(template, ctx))

    def folder_path(self, kind: str, ctx: Dict[str, Any]) -> tuple:
        keys = self.layout.get(kind)
        if keys is None:
            raise ProfileError("profile %s has no layout for %r" % (self.id, kind))
        return tuple(self.folder_name(key, ctx) for key in keys)

    def file_name(self, kind: str, ctx: Dict[str, Any], extension: str) -> str:
        template = self.filename.get(kind)
        if template is None:
            raise ProfileError("profile %s has no filename template %r" % (self.id, kind))
        stem = self.clean(self._render(template, ctx))
        if self.filename.get("keep_original"):
            stem = self.clean("%s - %s" % (stem, ctx["original"]))
        return stem + (extension or "").lower()


def available() -> List[str]:
    if not os.path.isdir(PROFILE_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json"))
