"""Matching a document's client to the firm's existing client list.

Reading a name off a document is only half the job. A firm with 800 client
folders needs the document to land in the *existing* one — not in an 801st,
spelled slightly differently.

That failure is the quiet one. Creating `Nguyen` beside an existing
`Nguyen, Linh & David` raises no error, loses no file, and looks completely
normal in a folder listing. The client's file is simply in two places now, and
somebody finds out during a compliance review years later while trying to
reconstruct an advice event. A visible refusal is much cheaper.

Deliberately not an LLM. Client identity has to be consistent and auditable —
the same name must resolve the same way every time, and a reviewer must be able
to see why. Deterministic matching against a register does that; a model asked
the same question twice may not. Where the LLM earns its place is upstream, at
build step 4: pulling an identity out of a document that never states one
plainly. Whatever it extracts still comes through this matcher.
"""

from __future__ import annotations

import csv
import difflib
import json
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from .kb import KnowledgeBase


# Letters that do NOT decompose under NFKD, so stripping combining marks leaves
# them untouched. This is the gotcha: "Sørensen" normalises to "sørensen", which
# is 0.875 similar to "sorensen" — under a 0.88 fuzzy threshold, and therefore a
# different client. Every one of these appears in Australian client lists.
_TRANSLITERATE = {
    "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ł": "l", "đ": "d",
    "ð": "d", "þ": "th", "ħ": "h", "ı": "i", "ŋ": "n", "ŧ": "t", "ơ": "o",
    "ư": "u", "ə": "e",
}


def normalise(name: str) -> str:
    """Casefold and strip diacritics, for comparison only — never for display.

    A scanner, an old export or a Windows-1252 round-trip is what turns Sørensen
    into Sorensen. They are the same client, and the comparison has to see that.
    """
    text = (name or "").lower()
    for source, target in _TRANSLITERATE.items():
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s'-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip().lower()


def _tokens(name: str) -> List[str]:
    return [t for t in re.split(r"[\s,&]+", normalise(name)) if t and t != "and"]


class ClientEntry(object):
    """One client as the firm already holds them."""

    def __init__(self, client_id: str, folder_name: str,
                 surnames: Optional[List[str]] = None,
                 given_names: Optional[List[str]] = None,
                 aliases: Optional[List[str]] = None,
                 external_id: Optional[str] = None) -> None:
        self.client_id = client_id
        self.folder_name = folder_name
        self.surnames = [s for s in (surnames or []) if s]
        self.given_names = [g for g in (given_names or []) if g]
        self.aliases = aliases or []
        self.external_id = external_id

    @property
    def key(self) -> str:
        return "-".join(sorted(set(self.surnames)))

    @property
    def normalised_surnames(self) -> set:
        return set(normalise(s) for s in self.surnames)

    @property
    def normalised_givens(self) -> set:
        return set(normalise(g) for g in self.given_names)

    def to_dict(self) -> Dict[str, Any]:
        return {"client_id": self.client_id, "folder_name": self.folder_name,
                "surnames": self.surnames, "given_names": self.given_names,
                "aliases": self.aliases, "external_id": self.external_id}

    @classmethod
    def from_folder_name(cls, folder_name: str, client_id: Optional[str] = None
                         ) -> "ClientEntry":
        """Parse an existing folder name into a client.

        Handles the two conventions firms actually use: "Nguyen, Linh & David"
        and "Linh & David Nguyen". Surname-first is detected by the comma.
        """
        raw = folder_name.strip()
        if "," in raw:
            surname_part, _, given_part = raw.partition(",")
            surnames = _tokens(surname_part)
            givens = _tokens(given_part)
        else:
            parts = _tokens(raw)
            # Hyphenated multi-surname keys as this tool writes them.
            if len(parts) == 1 and "-" in parts[0]:
                surnames, givens = parts[0].split("-"), []
            elif len(parts) >= 2:
                surnames, givens = [parts[-1]], parts[:-1]
            else:
                surnames, givens = parts, []
        return cls(client_id or normalise(raw).replace(" ", "-"),
                   folder_name,
                   [s.title() for s in surnames],
                   [g.title() for g in givens])


# What the register concluded. Callers branch on this, never on the wording of
# `reason` — a flag that depends on a phrase in a human-readable string breaks
# the moment somebody improves the sentence.
MATCHED = "matched"        # this is that client
AMBIGUOUS = "ambiguous"    # two or more fit; choosing would be a coin toss
UNCERTAIN = "uncertain"    # one is close but not close enough to file on
NEW = "new"                # nobody in the register resembles them


class Match(object):
    def __init__(self, entry: Optional[ClientEntry], score: float, reason: str,
                 verdict: str = NEW,
                 runners: Optional[List[Tuple[ClientEntry, float]]] = None) -> None:
        self.entry = entry
        self.score = score
        self.reason = reason
        self.verdict = verdict
        self.runners = runners or []

    @property
    def matched(self) -> bool:
        return self.verdict == MATCHED and self.entry is not None


class ClientRegister(object):
    """The firm's existing clients, and the decision about which one this is."""

    def __init__(self, entries: List[ClientEntry], kb: KnowledgeBase) -> None:
        self.entries = entries
        config = kb.data.get("client_matching", {})
        thresholds = config.get("thresholds", {})
        self.match_threshold = float(thresholds.get("match", 0.80))
        self.ambiguous_margin = float(thresholds.get("ambiguous_margin", 0.12))
        self.propose_new_below = float(thresholds.get("propose_new_below", 0.55))

    def __len__(self) -> int:
        return len(self.entries)

    # -- loading ------------------------------------------------------------

    @classmethod
    def load(cls, path: str, kb: KnowledgeBase) -> "ClientRegister":
        if os.path.isdir(path):
            return cls.from_directory(path, kb)
        if path.lower().endswith(".csv"):
            return cls.from_csv(path, kb)
        with open(path, "r") as fh:
            payload = json.load(fh)
        rows = payload.get("clients", payload) if isinstance(payload, dict) else payload
        return cls([ClientEntry(**row) for row in rows], kb)

    @classmethod
    def from_csv(cls, path: str, kb: KnowledgeBase) -> "ClientRegister":
        """A practice-management export. Column names are matched loosely."""
        entries = []
        with open(path, "r") as fh:
            for row in csv.DictReader(fh):
                low = {(k or "").strip().lower(): (v or "").strip()
                       for k, v in row.items()}
                folder = (low.get("folder_name") or low.get("folder")
                          or low.get("client") or low.get("client_name")
                          or low.get("name") or "")
                if not folder:
                    continue
                surnames = low.get("surnames") or low.get("surname") or low.get("last_name")
                givens = low.get("given_names") or low.get("given_name") or low.get("first_name")
                entry = (ClientEntry.from_folder_name(folder) if not surnames
                         else ClientEntry(
                             low.get("client_id") or normalise(folder).replace(" ", "-"),
                             folder,
                             [s.strip() for s in re.split(r"[;&,]", surnames) if s.strip()],
                             [g.strip() for g in re.split(r"[;&,]", givens or "") if g.strip()]))
                entry.external_id = low.get("external_id") or low.get("id") or None
                entries.append(entry)
        return cls(entries, kb)

    @classmethod
    def from_directory(cls, root: str, kb: KnowledgeBase) -> "ClientRegister":
        """Read the destination itself as the register.

        The firm's existing folder tree is the most accurate client list they
        have, and the one that needs no export, no API and no IT ticket.
        """
        entries = []
        for name in sorted(os.listdir(root)):
            if name.startswith(".") or name.startswith("_"):
                continue
            if not os.path.isdir(os.path.join(root, name)):
                continue
            entries.append(ClientEntry.from_folder_name(name))
        return cls(entries, kb)

    # -- matching -----------------------------------------------------------

    def _score(self, entry: ClientEntry, surnames: List[str],
               givens: List[str]) -> Tuple[float, str]:
        theirs = entry.normalised_surnames
        ours = set(normalise(s) for s in surnames)
        if not ours or not theirs:
            return 0.0, "no surnames to compare"

        mine_givens = set(normalise(g) for g in givens)
        overlap = entry.normalised_givens & mine_givens

        # Given names are not decoration here. Where surnames match, they are the
        # ONLY thing separating two households called Nguyen — so agreement must
        # be able to decide the match, and disagreement must be able to sink it.
        # Treating them as a small bonus left "Linh & David Nguyen" and
        # "Bao Nguyen" 0.10 apart, close enough to be called ambiguous.
        if not entry.normalised_givens or not mine_givens:
            evidence, detail = "unknown", " (no given names to compare)"
        elif overlap:
            evidence = "agree"
            detail = " and given name%s %s" % ("s" if len(overlap) > 1 else "",
                                               ", ".join(sorted(overlap)))
        else:
            evidence = "conflict"
            detail = (" but different given names (%s vs %s)"
                      % (", ".join(sorted(mine_givens)),
                         ", ".join(sorted(entry.normalised_givens))))

        if ours == theirs:
            score = {"agree": 0.98, "unknown": 0.85, "conflict": 0.55}[evidence]
            return score, "surnames match exactly" + detail
        if ours < theirs or theirs < ours:
            # One document naming one partner of a couple. Real, and also exactly
            # what a different household with a shared surname looks like.
            score = {"agree": 0.88, "unknown": 0.62, "conflict": 0.45}[evidence]
            return score, "surnames overlap" + detail

        best = 0.0
        pair = ("", "")
        for mine in ours:
            for theirs_one in theirs:
                ratio = difflib.SequenceMatcher(None, mine, theirs_one).ratio()
                if ratio > best:
                    best, pair = ratio, (mine, theirs_one)
        if best >= 0.85:
            adjust = {"agree": 0.10, "unknown": 0.0, "conflict": -0.25}[evidence]
            return max(0.0, min(0.95, best) + adjust), (
                "surname '%s' is a near match for '%s'%s" % (pair[0], pair[1], detail))
        return best * 0.5, "surnames differ"

    def match(self, surnames: List[str], givens: Optional[List[str]] = None
              ) -> Match:
        givens = givens or []
        if not self.entries:
            return Match(None, 0.0, "register is empty")

        scored = []
        for entry in self.entries:
            score, reason = self._score(entry, surnames, givens)
            scored.append((score, reason, entry))
        scored.sort(key=lambda s: (-s[0], s[2].folder_name))

        top_score, top_reason, top_entry = scored[0]
        runners = [(e, s) for s, _, e in scored[1:4] if s > 0]

        if top_score < self.propose_new_below:
            return Match(None, top_score,
                         "nobody in the register resembles them (closest was %s "
                         "at %.2f)" % (top_entry.folder_name, top_score),
                         NEW, runners)

        if len(scored) > 1:
            second_score, _, second_entry = scored[1]
            if top_score - second_score < self.ambiguous_margin and second_score > 0:
                return Match(None, top_score,
                             "fits both %s (%.2f) and %s (%.2f) too closely to "
                             "choose between them"
                             % (top_entry.folder_name, top_score,
                                second_entry.folder_name, second_score),
                             AMBIGUOUS, runners)

        if top_score >= self.match_threshold:
            return Match(top_entry, top_score,
                         "%s: %s" % (top_entry.folder_name, top_reason),
                         MATCHED, runners)

        return Match(top_entry, top_score,
                     "closest is %s at %.2f, under the %.2f needed to file on"
                     % (top_entry.folder_name, top_score, self.match_threshold),
                     UNCERTAIN, runners)

    # -- growth -------------------------------------------------------------

    def add(self, entry: ClientEntry) -> None:
        self.entries.append(entry)

    def save(self, path: str) -> str:
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, "w") as fh:
            json.dump({"clients": [e.to_dict() for e in self.entries]},
                      fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        try:
            os.chmod(path, 0o600)   # a client list is itself sensitive
        except OSError:
            pass
        return path
