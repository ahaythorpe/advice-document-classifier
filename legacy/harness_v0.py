#!/usr/bin/env python3
"""
Advice-file classification + nested-filing test harness (Phase 1, local, no cloud).

WHAT THIS IS: a deliberately simple, dependency-free stand-in for the real system,
so you can WATCH the design work (and fail) on sample documents before building anything bigger.

The real system will swap the keyword matcher below for an LLM classifier that reads
the same knowledge_base.json 'classifier_hints'. Everything else — event grouping,
folder tree, flags, scorecard — stays the same shape.
"""

import json
import re
from collections import defaultdict

KB = json.load(open("knowledge_base.json"))
SAMPLES = json.load(open("sample_documents.json"))["documents"]

# ---- 1. CLASSIFY -----------------------------------------------------------
# Stand-in classifier: score each doc against each type's title patterns + signals.
# Confidence = normalised signal hits. The LLM version returns type+confidence too,
# so the downstream code is identical.

def classify(text):
    text_low = text.lower()
    scores = {}
    for doc in KB["documents"]:
        hints = doc["classifier_hints"]
        terms = []
        terms += [t.lower() for t in hints.get("title_patterns", [])]
        terms += [f.lower() for f in hints.get("key_fields", [])]
        terms += [s.lower() for s in hints.get("distinguishing_signals", [])]
        # title patterns are strong signals; weight them heavily
        hits = 0
        for t in hints.get("title_patterns", []):
            if t.lower() in text_low:
                hits += 3
        for f in hints.get("key_fields", []):
            # match on the first word or two of each field cue
            cue = f.lower().split(" / ")[0].split(" (")[0]
            if cue and cue in text_low:
                hits += 1
        scores[doc["id"]] = hits
    if not scores or max(scores.values()) == 0:
        return None, 0.0
    best = max(scores, key=scores.get)
    top = scores[best]
    # crude confidence: top score over (top + runner-up), capped
    ordered = sorted(scores.values(), reverse=True)
    runner = ordered[1] if len(ordered) > 1 else 0
    conf = top / (top + runner) if (top + runner) else 0
    return best, round(conf, 2)

CONF_THRESHOLD = 0.60

# ---- 2. EXTRACT client + linkage cues --------------------------------------

def extract_client(text):
    m = re.search(r"(?:Client|prepared for)[:\s]+([A-Z][A-Za-z ,&]+?)(?:\.|Adviser|AFSL|I authorise|Assets|Responses|Further|$)", text)
    if m:
        name = m.group(1).strip().rstrip(".")
        # normalise "Linh Nguyen and David Nguyen" / "Linh & David Nguyen" to a family key
        surnames = re.findall(r"\b([A-Z][a-z]+)\b", name)
        if surnames:
            return name, surnames[-1]  # family key = last surname seen
    return None, None

def extract_referenced_date(text):
    m = re.search(r"(?:Statement of Advice|SOA) dated (\d{1,2} \w+ \d{4})", text)
    return m.group(1) if m else None

def extract_own_date(text):
    m = re.search(r"(?:Date of advice|Date signed|Date|Effective date|Completed)[:\s]+(\d{1,2} \w+ \d{4})", text)
    return m.group(1) if m else None

# ---- 3. RUN classification -------------------------------------------------

records = []
for s in SAMPLES:
    doc_id, conf = classify(s["text"])
    client_full, family = extract_client(s["text"])
    rec = {
        "file": s["file"],
        "type": doc_id,
        "confidence": conf,
        "client_full": client_full,
        "family": family,
        "ref_soa_date": extract_referenced_date(s["text"]),
        "own_date": extract_own_date(s["text"]),
        "flags": [],
    }
    records.append(rec)

# ---- 4. GROUP into advice events -------------------------------------------
# An advice event is anchored by an advice record (SOA/ROA/CAR).
# Inputs (fact find, risk profile), implementation (ATP), and PDS attach to the
# nearest advice record for the same family.

ADVICE_RECORDS = {"soa", "car", "roa"}
INPUTS = {"fact_find", "risk_profile"}
CLIENT_LEVEL = {"fsg"}

# Index advice records by family
events = []  # each: {family, anchor_file, type, date, subject, members[]}
for r in records:
    if r["type"] in ADVICE_RECORDS and r["family"]:
        subject = "Super/Retirement" if "super" in " ".join(str(v) for v in r.values()).lower() else \
                  "Insurance" if False else "Advice"
        events.append({
            "family": r["family"],
            "anchor": r["file"],
            "type": r["type"],
            "date": r["own_date"],
            "members": [r["file"]],
        })

def find_event(family, ref_date=None):
    cands = [e for e in events if e["family"] == family]
    if not cands:
        return None
    if ref_date:
        for e in cands:
            if e["date"] == ref_date:
                return e
    # else attach to the (single) or earliest event
    return cands[0] if len(cands) == 1 else sorted(cands, key=lambda e: e["date"] or "")[0]

# Attach non-anchor documents
for r in records:
    if r["type"] in ADVICE_RECORDS:
        continue
    if r["type"] is None or r["confidence"] < CONF_THRESHOLD:
        r["flags"].append("low_confidence / unknown_type -> _Needs review")
        continue
    if r["type"] in CLIENT_LEVEL:
        r["placement"] = "_Client-level documents"
        continue
    if not r["family"]:
        r["flags"].append("no client identified -> _Needs review")
        continue
    ev = find_event(r["family"], r["ref_soa_date"])
    if ev is None:
        # ATP or input with a client but no matching advice event on file
        r["flags"].append(f"{r['type']} for {r['family']} but NO advice event on file -> _Needs review")
        continue
    ev["members"].append(r["file"])
    r["placement"] = f"{r['family']} / event anchored by {ev['anchor']}"

# Flag anchors' own low confidence
for r in records:
    if r["type"] in ADVICE_RECORDS and r["confidence"] < CONF_THRESHOLD:
        r["flags"].append("advice record but low confidence -> _Needs review")

# ---- 5. BUILD folder tree --------------------------------------------------

tree = defaultdict(lambda: {"events": defaultdict(list), "client_level": [], "review": []})

for r in records:
    fam = r["family"]
    if r["flags"]:
        # route to review under family if known, else global review
        key = fam or "UNASSIGNED"
        tree[key]["review"].append((r["file"], r["type"], r["confidence"], r["flags"]))
        continue
    if r.get("placement") == "_Client-level documents":
        tree[fam]["client_level"].append(r["file"])
        continue
    if r["type"] in ADVICE_RECORDS:
        tree[fam]["events"][r["file"]].append(r["file"])  # anchor listed under itself
    elif "placement" in r:
        anchor = r["placement"].split("anchored by ")[-1]
        tree[fam]["events"][anchor].append(r["file"])

# ---- 6. PRINT --------------------------------------------------------------

print("=" * 70)
print("CLASSIFICATION SCORECARD")
print("=" * 70)
for r in records:
    status = "OK " if not r["flags"] else "FLAG"
    print(f"[{status}] {r['file']:14} -> {str(r['type']):22} conf={r['confidence']:.2f}  client={r['family']}")

print()
print("=" * 70)
print("PROPOSED FOLDER TREE (client outer / advice-event inner)")
print("=" * 70)
for fam, content in tree.items():
    print(f"\n[CLIENT] {fam}")
    for anchor, members in content["events"].items():
        # find anchor record for a label
        arec = next((x for x in records if x["file"] == anchor), None)
        label = f"{arec['own_date']} [{arec['type'].upper()}]" if arec else anchor
        print(f"   [EVENT] {label}  (anchor: {anchor})")
        for m in sorted(set(members)):
            mrec = next((x for x in records if x["file"] == m), None)
            print(f"        - {m}  ({mrec['type']})")
    if content["client_level"]:
        print(f"   [_Client-level documents]")
        for f in content["client_level"]:
            print(f"        - {f}")
    if content["review"]:
        print(f"   [_Needs review]")
        for (f, t, c, flags) in content["review"]:
            print(f"        - {f}  (type={t}, conf={c}) :: {'; '.join(flags)}")

print()
print("=" * 70)
print("FAILURE LOG (every flag, for your improvement loop)")
print("=" * 70)
any_flags = False
for r in records:
    for fl in r["flags"]:
        any_flags = True
        print(f"- {r['file']}: {fl}")
if not any_flags:
    print("(no flags — suspicious on real data; means nothing surfaced for review)")
