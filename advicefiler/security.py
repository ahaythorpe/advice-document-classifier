"""Handling client data carefully.

The threat here is not an attacker. Phase 1 runs on one machine, reads local
files and makes no network calls. The realistic ways this leaks are mundane:

* a manifest or failure log emailed to a developer, a vendor, or pasted into a
  chat, carrying client names and full paths;
* run output committed to a repository;
* filed documents left world-readable on a shared drive;
* a client register — a list of every client the firm has — sitting at default
  permissions.

So the controls are mundane too: redact what gets shared, tighten what gets
written, hash what gets filed, and record what happened.

What this module does NOT do is encrypt anything. Encryption at rest belongs to
the volume — FileVault, BitLocker, the DMS, the bucket — and a home-grown layer
on top of a tool that has not been penetration-tested would be worse than
honest reliance on the platform. SYSTEM.md section 10 lists the penetration test
as a pilot-stage requirement, and it stays there.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, List, Optional

# Fields in the manifest that name a person or reveal where their file lives.
_NAME_FIELDS = ("client", "correct_client", "tool_client")
_PATH_FIELDS = ("source_path",)


def pseudonym(value: Optional[str], salt: str = "") -> Optional[str]:
    """A stable, non-reversible stand-in for a client name.

    Stable so that a redacted manifest is still analysable — the same client is
    the same token across documents and across runs — and non-reversible so the
    name cannot be recovered from it. Pass a per-firm salt if redacted output
    will be compared across firms.
    """
    if value is None:
        return None
    digest = hashlib.sha256((salt + "|" + value).encode("utf-8")).hexdigest()
    return "client-%s" % digest[:10]


def redact_manifest(data: Dict[str, Any], salt: str = "",
                    keep: Optional[List[str]] = None) -> Dict[str, Any]:
    """Strip client identity from a manifest without destroying its usefulness.

    Types, confidences, flags, events and the shape of the tree all survive, so a
    redacted manifest is still enough to debug a classification, review accuracy,
    or show a vendor what the integration receives. What does not survive is any
    way to say whose file it was.

    ``keep`` is a vocabulary that must survive — document labels, advice subjects,
    special folder names. These come from a closed set in the knowledge base, so
    they identify nobody, and keeping them is what makes redacted output worth
    reading. Output nobody can read is not a safe default: it is the reason
    somebody sends the unredacted version instead.
    """
    out = _walk(data, salt, frozenset(k.lower() for k in (keep or [])))
    out["redacted"] = True
    out["redaction_note"] = (
        "Client names, folder paths and filenames have been replaced with stable "
        "pseudonyms. Types, confidences, flags and event structure are unchanged.")
    return out


def _walk(value: Any, salt: str, keep: frozenset = frozenset()) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in _NAME_FIELDS and isinstance(item, str):
                out[key] = pseudonym(item, salt)
            elif key in _PATH_FIELDS and isinstance(item, str):
                out[key] = "<redacted path>"
            elif key in ("filename", "path", "source_name") and isinstance(item, str):
                out[key] = _redact_filename(item, salt, keep)
            elif key == "folder" and isinstance(item, list):
                out[key] = [_redact_filename(p, salt, keep) for p in item]
            elif key in ("message", "rationale", "attachment_reason",
                         "client_provenance", "why", "classification_evidence"):
                out[key] = (_redact_text(item, salt, keep)
                            if isinstance(item, str) else item)
            else:
                out[key] = _walk(item, salt, keep)
        return out
    if isinstance(value, list):
        return [_walk(v, salt, keep) for v in value]
    return value


_FILENAME_SAFE = re.compile(
    r"(?i)\b(soa|roa|car|atp|fsg|pds|fds|fact\s*find|risk\s*profile|"
    r"authority\s+to\s+proceed|client\s+advice\s+record|undated|unknown|"
    r"needs\s+review|licensee|client[- ]level|advice|documents?)\b")


def _redact_filename(name: str, salt: str,
                     keep: frozenset = frozenset()) -> str:
    """Keep the parts that describe the document, replace the parts that name
    a person. Dates and type labels stay; anything else becomes a token."""
    kept = []
    for chunk in re.split(r"[/\\]", name):
        pieces = []
        for token in re.split(r"[\s_]+", chunk):
            if not token:
                continue
            bare = token.strip("[]()·-").lower()
            if (re.match(r"^[\d\-\.\(\)\[\]]+$", token)
                    or _FILENAME_SAFE.match(token) or bare in keep or bare in ("&", "")):
                pieces.append(token)
            elif token.startswith(".") or re.match(r"^\.\w+$", token):
                pieces.append(token)
            else:
                pieces.append(pseudonym(token, salt) or "x")
        kept.append(" ".join(pieces))
    return "/".join(kept)


def _redact_text(text: str, salt: str, keep: frozenset = frozenset()) -> str:
    """Blank out capitalised name-shaped words in free prose."""
    def replace(match):
        word = match.group(0)
        if _FILENAME_SAFE.match(word) or word.lower() in keep:
            return word
        return pseudonym(word, salt) or word
    return re.sub(r"\b[A-Z][\w'\-]{2,}\b", replace, text)


def redact_failure_row(row: Dict[str, Any], salt: str = "") -> Dict[str, Any]:
    out = dict(row)
    for field in _NAME_FIELDS:
        if isinstance(out.get(field), str):
            out[field] = pseudonym(out[field], salt)
    if isinstance(out.get("input"), str):
        out["input"] = _redact_filename(out["input"], salt)
    if isinstance(out.get("why"), str):
        out["why"] = _redact_text(out["why"], salt)
    out["redacted"] = True
    return out


# ---------------------------------------------------------------------------
# Filesystem hygiene
# ---------------------------------------------------------------------------

DIR_MODE = 0o700     # owner only
FILE_MODE = 0o600    # owner only


def harden(path: str) -> None:
    """Restrict a file or directory to its owner.

    Best effort: a network share or a synced cloud folder may not honour POSIX
    modes, and failing the run over that would be worse than the exposure. What
    matters is that we do not *widen* anything.
    """
    try:
        mode = DIR_MODE if os.path.isdir(path) else FILE_MODE
        os.chmod(path, mode)
    except (OSError, NotImplementedError):
        pass


def harden_tree(root: str) -> None:
    for current, directories, files in os.walk(root):
        harden(current)
        for name in directories + files:
            harden(os.path.join(current, name))


def file_digest(path: str) -> str:
    """SHA-256 of a filed document, for the audit trail.

    Records that the copy is the document that was classified — which is the
    question a compliance reviewer asks about an automated filing step.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def network_modules_used(package_dir: Optional[str] = None) -> List[str]:
    """Which modules import networking. Should be empty, and is tested.

    Phase 1 makes no network calls at all. That is a property worth being able
    to demonstrate to a licensee rather than assert, so it is checked rather
    than promised.
    """
    package_dir = package_dir or os.path.dirname(os.path.abspath(__file__))
    offenders = []
    pattern = re.compile(
        r"^\s*(?:import|from)\s+(socket|http|urllib|requests|httpx|ftplib|"
        r"smtplib|telnetlib|xmlrpc|aiohttp|websocket)\b", re.M)
    for name in sorted(os.listdir(package_dir)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(package_dir, name), "r") as fh:
            if pattern.search(fh.read()):
                offenders.append(name)
    return offenders
