"""Pulling clients, dates, risk categories and product names out of text.

Three v0 bugs live here, and all three were silent:

1. Dates were kept as strings and compared with ``sorted()``, so
   "10 September 2025" sorted before "14 March 2024" because '0' < '4'. That one
   line attached the March fact find and risk profile to the September insurance
   event and left the March SOA holding nothing.
2. The family key was the last capitalised word in the client line, which works
   for the Nguyens and breaks for any couple with two surnames.
3. Dates arrive in Australian order. 03/04/2024 is 3 April, not 4 March.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

# Ordered most-specific first. Each yields (year, month, day) once interpreted.
_DATE_PATTERNS = [
    ("dmy_word", re.compile(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(%s)\.?\,?\s+(\d{4})\b" % _MONTH_ALT, re.I)),
    ("mdy_word", re.compile(
        r"\b(%s)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\,?\s+(\d{4})\b" % _MONTH_ALT, re.I)),
    ("iso", re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")),
    ("numeric", re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")),
]

DATE_REGEX_FRAGMENT = (
    r"(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:%s)\.?,?\s+\d{4}"
    r"|(?:%s)\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r"|\d{4}-\d{1,2}-\d{1,2}"
    r"|\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})" % (_MONTH_ALT, _MONTH_ALT)
)


class ParsedDate(object):
    """A date plus how sure we are that we read it the way it was written."""

    def __init__(self, value: datetime.date, raw: str, style: str,
                 ambiguous: bool = False) -> None:
        self.value = value
        self.raw = raw
        self.style = style
        self.ambiguous = ambiguous

    def iso(self) -> str:
        return self.value.isoformat()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<ParsedDate %s from %r%s>" % (
            self.iso(), self.raw, " AMBIGUOUS" if self.ambiguous else "")


def parse_date(raw: str) -> Optional[ParsedDate]:
    """Parse a single date string, Australian day-first convention."""
    raw = raw.strip()
    for style, pattern in _DATE_PATTERNS:
        match = pattern.search(raw)
        if not match or match.group(0).strip() != raw:
            continue
        return _build(match, style, raw)
    return None


def _build(match, style: str, raw: str) -> Optional[ParsedDate]:
    try:
        if style == "dmy_word":
            day, month, year = int(match.group(1)), _MONTHS[match.group(2).lower().rstrip(".")], int(match.group(3))
            ambiguous = False
        elif style == "mdy_word":
            month, day, year = _MONTHS[match.group(1).lower().rstrip(".")], int(match.group(2)), int(match.group(3))
            ambiguous = False
        elif style == "iso":
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            ambiguous = False
        else:  # numeric — Australian convention is day first
            first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if year < 100:
                year += 2000 if year < 70 else 1900
            if first > 12 and second <= 12:
                day, month, ambiguous = first, second, False
            elif second > 12 and first <= 12:
                # Written month-first. Read it that way but say so.
                month, day, ambiguous = first, second, True
            else:
                day, month, ambiguous = first, second, first != second
        return ParsedDate(datetime.date(year, month, day), raw, style, ambiguous)
    except (ValueError, KeyError):
        return None


def find_dates(text: str) -> List[ParsedDate]:
    """Every date in the text, in order of appearance, de-duplicated by value."""
    found = []  # type: List[ParsedDate]
    seen = set()  # type: Set[Tuple[int, int, int]]
    spans = []  # type: List[Tuple[int, int]]
    for style, pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            if any(s <= match.start() < e for s, e in spans):
                continue
            parsed = _build(match, style, match.group(0))
            if parsed is None:
                continue
            spans.append((match.start(), match.end()))
            key = (parsed.value.year, parsed.value.month, parsed.value.day)
            if key in seen:
                continue
            seen.add(key)
            found.append(parsed)
    return found


# Generic labels, used after the type's own knowledge-base cues are tried.
_GENERIC_DATE_LABELS = [
    "date of advice", "date signed", "date completed", "date of this advice",
    "effective date", "date issued", "date prepared", "completed on",
    "completed", "dated", "date",
]


def extract_own_date(text: str, key_field_labels: Optional[List[str]] = None
                     ) -> Tuple[Optional[ParsedDate], str]:
    """The document's own date, preferring labelled dates over loose ones.

    ``key_field_labels`` comes from the classified type's knowledge-base
    ``key_fields`` — so an SOA looks for "date of advice" before anything else
    and an ATP looks for "date signed", without either label being hardcoded.

    Returns (date, provenance). Provenance matters: a date read from a label is
    worth more than the only number on the page, and the reviewer should be able
    to see which they are looking at.
    """
    labels = []  # type: List[str]
    for label in (key_field_labels or []):
        low = label.lower()
        if "date" in low or "completed" in low or "effective" in low:
            labels.append(low.split(" / ")[0].split(" (")[0].strip())
    labels.extend(_GENERIC_DATE_LABELS)

    seen_labels = set()  # type: Set[str]
    for label in labels:
        if label in seen_labels:
            continue
        seen_labels.add(label)
        pattern = re.compile(
            re.escape(label) + r"\s*[:\-]?\s*(" + DATE_REGEX_FRAGMENT + r")", re.I)
        match = pattern.search(text)
        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                return parsed, "labelled '%s'" % label

    loose = find_dates(text)
    if len(loose) == 1:
        return loose[0], "only date in document (unlabelled)"
    if len(loose) > 1:
        # Several dates and none of them labelled as the document's own. Refusing
        # here is the point: picking one would be a guess, and every downstream
        # sequencing decision would inherit it.
        return None, "%d unlabelled dates, none identifiable as the document's own" % len(loose)
    return None, "no date found"


def extract_referenced_dates(text: str, reference_patterns_by_type: Dict[str, List[str]]
                             ) -> Dict[str, ParsedDate]:
    """Dates of *other* documents this one cites.

    Driven entirely by each type's ``reference_patterns`` in the knowledge base,
    so "Statement of Advice dated 14 March 2024" resolves to a reference to an
    SOA on that date without this module knowing what an SOA is.
    """
    out = {}  # type: Dict[str, ParsedDate]
    for doc_id, patterns in reference_patterns_by_type.items():
        for phrase in patterns:
            pattern = re.compile(
                re.escape(phrase) + r"\s*[:\-]?\s*(" + DATE_REGEX_FRAGMENT + r")", re.I)
            match = pattern.search(text)
            if match:
                parsed = parse_date(match.group(1))
                if parsed:
                    out[doc_id] = parsed
                    break
    return out


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

# A bare "client" is not a label. "FACT FIND - CLIENT DATA FORM" begins with the
# word and names nobody, and reading a name out of it produced a client called
# FORM. So the label form requires a separator, and the prose form requires one
# of a few fixed phrases.
_CLIENT_LABELS = re.compile(
    r"(?:client(?:\(s\))?s?(?:\s+name)?\s*[:\-]\s*"
    r"|(?:prepared\s+(?:exclusively\s+)?for|advice\s+for|advice\s+prepared\s+for)"
    r"\s*[:\-]?\s+)",
    re.I)

_NAME_TITLES = frozenset(["mr", "mrs", "ms", "miss", "dr", "prof", "sir", "dame"])
_NAME_STOPWORDS = frozenset([
    "adviser", "afsl", "authorised", "representative", "pty", "ltd", "limited",
    "advice", "statement", "record", "the", "and", "date", "signature", "signed",
    "assets", "responses", "further", "scope", "i", "we", "client", "clients",
])


def _clean_name_fragment(fragment: str) -> str:
    fragment = fragment.strip().strip(".,;:")
    fragment = re.sub(r"\s+", " ", fragment)
    return fragment


def extract_client(text: str) -> Tuple[Optional[str], List[str], Optional[str]]:
    """Return (as-written client string, surnames, family key).

    Handles the shared-surname convention: "Linh & David Nguyen" is two people
    called Nguyen, while "Linh Nguyen and David Tran" is two surnames and the
    family key carries both. v0 took the last capitalised word and would have
    filed the Trans under Nguyen without comment.
    """
    for match in _CLIENT_LABELS.finditer(text):
        found = _read_names_at(text, match.end())
        if found[2]:
            return found
    return None, [], None


def _read_names_at(text: str, start: int) -> Tuple[Optional[str], List[str], Optional[str]]:
    tail = text[start:]
    # Stop at the first sentence break or line end — the client line is short.
    stop = re.search(r"(?:\.\s|\.$|\n|\||;)", tail)
    raw = _clean_name_fragment(tail[:stop.start()] if stop else tail[:80])
    if not raw or not raw[0].isupper():
        return None, [], None

    parts = re.split(r"\s*(?:&|\band\b|,)\s*", raw)
    parsed = []  # type: List[List[str]]
    for part in parts:
        tokens = [t for t in re.findall(r"[A-Za-z'\-]+", part)
                  if t.lower() not in _NAME_TITLES]
        tokens = [t for t in tokens if t.lower() not in _NAME_STOPWORDS]
        tokens = [t for t in tokens if t[:1].isupper()]
        if tokens:
            parsed.append(tokens)

    if not parsed:
        return None, [], None

    # A part with two or more tokens carries its own surname; a lone given name
    # borrows the surname of the next part that has one.
    surnames = [None] * len(parsed)  # type: List[Optional[str]]
    for i, tokens in enumerate(parsed):
        if len(tokens) >= 2:
            surnames[i] = tokens[-1]
    last_known = None
    for i in range(len(parsed) - 1, -1, -1):
        if surnames[i]:
            last_known = surnames[i]
        elif last_known:
            surnames[i] = last_known
    # Anything still unresolved sits before every surname; borrow forwards.
    first_known = next((s for s in surnames if s), None)
    surnames = [s or first_known for s in surnames]

    unique = sorted(set(s for s in surnames if s))
    if not unique:
        return raw, [], None
    return raw, unique, "-".join(unique)


def merge_family_keys(keys: List[str]) -> Dict[str, str]:
    """Map narrower family keys onto wider ones where that is unambiguous.

    A fact find naming only "Nguyen" and an SOA naming "Nguyen-Tran" are probably
    the same household. Probably is not certain, so the merge only happens when
    exactly one wider key contains the narrower one; two candidates means the
    tool does not know, and saying so is the whole point of the review queue.
    """
    unique = sorted(set(k for k in keys if k))
    mapping = {k: k for k in unique}
    for narrow in unique:
        narrow_set = set(narrow.split("-"))
        containers = [w for w in unique
                      if w != narrow and narrow_set < set(w.split("-"))]
        if len(containers) == 1:
            mapping[narrow] = containers[0]
    return mapping


# ---------------------------------------------------------------------------
# Risk category and product names
# ---------------------------------------------------------------------------

def extract_risk_category(text: str, cue_patterns: List[str],
                          categories: List[str]) -> Optional[str]:
    """The risk category a risk profile lands on, e.g. 'Balanced'."""
    ordered = sorted(categories, key=len, reverse=True)
    for cue in cue_patterns:
        pattern = re.compile(re.escape(cue) + r"\s*[:\-]?\s*([A-Za-z ]{3,30})", re.I)
        match = pattern.search(text)
        if match:
            tail = match.group(1).lower()
            for category in ordered:
                if tail.strip().startswith(category):
                    return category
    low = text.lower()
    for category in ordered:
        if re.search(r"\b%s\b" % re.escape(category), low):
            return category
    return None


_PRODUCT_TOKEN = re.compile(r"\b(?:[A-Z][a-z]{2,}){2,}\b")


def extract_product_tokens(text: str) -> Set[str]:
    """Distinctive product names, for linking issuer material to an event.

    Australian financial products are overwhelmingly CamelCase brand words —
    AwesomeSuper, AustralianSuper, MacquarieWrap. Matching on those links a PDS
    to the advice record that recommends it without needing a product register.
    """
    return set(_PRODUCT_TOKEN.findall(text))
