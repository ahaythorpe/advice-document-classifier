# Connecting to a firm's existing filing system

The firm already has a filing system. It has years of files in it, staff habits
built around it, and often a licensee rule about it. This tool has to fit into
that, not replace it.

So nothing about the destination is baked in. There are three ways to connect,
in increasing order of how much the firm has to trust us, and every firm can
start at the first.

---

## 1. Three ways in

### A. Take the manifest (no write access at all)

We classify, group and propose. The firm's own system does the filing.

```bash
python3 harness.py --input input/smith \
    --export-manifest out/manifest.json \
    --export-csv out/plan.csv
```

`manifest.json` is the full contract: every document with its type, client,
advice event, confidence, flags, provenance and proposed destination, keyed by a
stable content id. `plan.csv` is the same thing flattened, because a great many
practice-management systems import a spreadsheet.

This is the right starting point for almost every firm. It needs no credentials,
no IT approval, and no write access to anything.

### B. Take a script (write access, but through a channel IT already trusts)

```bash
python3 harness.py --input input/smith --export-script out/file-them.sh \
    --dest-root "/Volumes/Advice/Clients"
python3 harness.py --input input/smith --export-script out/file-them.ps1 \
    --script-shell powershell --dest-root "D:\\Clients"
```

A plain, reviewable list of `mkdir` and `cp`. Documents queued for review appear
as commented-out lines with the reason, so nothing is filed by accident and
nothing is hidden. Some firms will not let an unfamiliar tool write to the
document store, which is a reasonable position; this gets the work done anyway.

### C. Let the tool file (desktop primary, cloud backup)

```bash
# 1. propose, and emit a decision sheet
python3 harness.py --input input/smith --emit-approvals out/approvals.json

# 2. a human edits it: decision -> "approve", and corrects folder/filename
$EDITOR out/approvals.json

# 3. dry run — shows exactly what would happen, writes nothing
python3 harness.py --input input/smith --approved out/approvals.json \
    --dest-root "/Volumes/Advice/Clients"

# 4. file it, with a verified second copy
python3 harness.py --input input/smith --approved out/approvals.json \
    --dest-root "/Volumes/Advice/Clients" --commit \
    --backup-root ~/OneDrive/AdviceBackup --backup-region ap-southeast-2
```

Documents queued for review default to `reject` in the approvals file, so the
safe outcome is the one you get by doing nothing.

---

## 2. Why desktop first and cloud second

**Desktop or network drive is the primary.** It is where advisers actually work,
it is what the practice-management system indexes, and it keeps working when the
internet does not.

**Cloud is a backup, and a verified one.** The backup mirrors what was actually
filed — taken after the primary succeeded — and every copy is hash-checked after
writing. A backup nobody has verified is a belief, not a backup.

**The same adapter reaches most clouds already.** OneDrive, SharePoint-synced
libraries, Teams document libraries, Dropbox and Google Drive all appear on an
adviser's machine as ordinary folders. Pointing `--backup-root` at one is a
working cloud backup with no API, no token and no integration project. That is
deliberately the first thing that works.

**Region is required, not optional.** `--backup-root` demands
`--backup-region`, and refuses anything that is not an Australian region unless
`--allow-non-au-backup` is passed explicitly. SYSTEM.md section 10 defers data
residency to pilot stage, and that is fine only while client files stay in the
building — a cloud copy is the moment it stops being true. Refusing by default is
cheaper than explaining it during a licensee audit.

---

## 3. Matching the firm's folder scheme: profiles

A profile is a JSON file in `profiles/`. It owns the folder layout, filename
pattern, document vocabulary, character set and path limits. The classifier does
not know which is loaded.

```bash
python3 harness.py --list-profiles
python3 harness.py --input input/smith --profile category-flat
```

| Profile | For |
|---|---|
| `nested-default` | Client outer, advice event inner. Best accuracy — the two axes cross-check each other. Use unless the firm's system dictates otherwise. |
| `category-flat` | One folder per client, subdivided by document category. How most practice-management systems organise a client file. |
| `sharepoint-safe` | ASCII only, no characters SharePoint mangles, shorter path budget. |
| `preserve-original` | Nested folders, original filenames appended, for firms whose registers cite documents by their existing name. |

**Advice events survive a scheme that has no folder for them.** Under
`category-flat` the event is not in the path, but it is still computed, still
drives the flags and the document links, and still appears in the manifest with
its id and members. Nothing is lost by adopting a flatter scheme; it is just not
expressed as folders.

### Writing one for a firm

Copy the closest profile and edit. Folder and filename templates use these
tokens:

| Token | Value |
|---|---|
| `{client}` | family key, e.g. `Okafor-Tran` (from the event, where there is one) |
| `{date:%Y-%m-%d}` | the document's own date; any strftime format |
| `{event_date:%Y-%m}` | the advice record's date |
| `{subject}` | e.g. `Retirement & Super Consolidation` |
| `{type_label}` | `SOA`, or the firm's own label via `type_labels` |
| `{record_label}` | the event's anchor type |
| `{sub_kind_suffix}` | ` · further advice`, or empty |
| `{category}` | `Advice Documents`, or the firm's own via `categories` |
| `{original}` | the original filename without extension |
| `{doc_id}` | stable content id |

`layout` maps the five placement kinds — `event_document`,
`client_level_document`, `licensee_document`, `review_with_client`,
`review_without_client` — onto sequences of folder templates.

`type_labels` and `categories` are the vocabulary mapping. This is where the
firm's words replace ours: if their DMS calls it a *Financial Plan* rather than a
*Statement of Advice*, map it, and the classifier is unaffected.

---

## 4. Writing an adapter for a real system

Implement `integrate.DestinationAdapter`:

```python
class MyDmsDestination(DestinationAdapter):
    name = "Acme DMS"
    is_cloud = True

    def apply(self, plan, approvals, dry_run=True) -> ApplyResult:
        ...
```

The contract:

* **Only file what was approved.** `approvals[doc_id]["decision"] == "approve"`.
  Anything else is `rejected` or `skipped`, never filed.
* **Honour edits.** A human may have changed `folder` or `filename` in the
  approvals file. Those win over the proposal.
* **Be idempotent.** `record.doc_id` is a content hash. The same batch applied
  twice must not produce two copies — record what you filed and recognise it on
  the next run. `LocalFolderDestination` keeps `_advicefiler/filed.json` for
  this.
* **Never overwrite.** If something different is already at the target path,
  fail that item and carry on. Report it; do not resolve it.
* **Respect `dry_run`.** It must be a complete rehearsal.
* **Leave an audit trail.** What was filed, from where, to where, when, at what
  confidence.

Then run `integrate.preflight()` first. It checks path length, illegal
characters, collisions and existing files against the profile's limits. Path
length is the one that bites: a nested scheme under a deep network share, synced
to SharePoint which URL-encodes every space, overruns limits that look generous
on paper — and it fails halfway through a batch, not at the start.

### Notes per system

| System | Route |
|---|---|
| **Network drive / desktop** | `LocalFolderDestination`. Works today. |
| **OneDrive, SharePoint, Teams, Dropbox, Google Drive** | Sync folder + `LocalFolderDestination` + `sharepoint-safe` profile. Works today, no API. |
| **SharePoint (server-side)** | Graph API adapter. Needed only when sync is not deployed; watch the URL-encoded path limit. |
| **Xplan, AdviserLogic** | `category-flat` as the starting profile, then map `type_labels` and `categories` to their document categories. Manifest-first (route A) until an API is available to the firm. |
| **Practifi / Salesforce** | CSV import of the manifest against ContentVersion, or an API adapter. |
| **Virtual Cabinet, iManage, Objective** | Adapter against their document-add API; the manifest supplies every metadata field these want. |
| **FYI** | Manifest-first; their import expects client + category + date, all present in the CSV. |

---

## 5. The manifest

`advicefiler/manifest@1`. Stable keys; additions are backwards-compatible.

```
schema, generated, knowledge_base_version, classifier,
filing_profile, confidence_threshold
batch     { client, documents, auto_filed, needs_review, unreadable[] }
events[]  { event_id, client, date, subject, record_type, record_label,
            sub_kind, anchor_doc_id, member_doc_ids[] }
documents[] { doc_id, source_name, source_path, extracted_by, pages,
              type, type_label, category, confidence,
              classification_evidence, extraction_quality, extraction_issues[],
              client, client_provenance, date, date_provenance,
              event_id, attachment_reason, attachment_confidence,
              needs_review, flags[{id,severity,class,blocks_filing,message}],
              destination{folder[],filename,path,kind,rationale} }
```

`doc_id` is a content hash — reconcile on it across runs. `client_provenance`
and `date_provenance` say *how* each was determined, which matters when a
reviewer is deciding whether to trust a placement: a client read from the
document is not the same as one inherited from the batch.

---

## 6. Rollout, in the order that survives contact with a firm

1. **Manifest only.** No write access. Compare our answer with where the firm
   actually filed things. This is also how the failure log gets real data.
2. **Dry-run filing to a scratch folder.** Nothing at risk, real paths exercised,
   preflight surfaces the path-length problems before they matter.
3. **Approvals + `--commit` on one adviser's new work**, `copy` mode, desktop
   primary. Old files stay where they are.
4. **Add the verified cloud backup**, region declared.
5. **`move` mode**, once the firm trusts the destination — and only then.
6. Their own adapter, if they want one, against a contract that has by then been
   exercised on their real files.

## 7. Not built

* API adapters for named systems — the interface is defined and the local
  implementation exercises it, but no vendor adapter exists yet.
* Reading *from* a DMS. Input is a folder today; a `SourceAdapter` mirroring
  `DestinationAdapter` is the obvious next step.
* Conflict resolution beyond refusing to overwrite. Deliberate: guessing which of
  two versions is current is the `superseding_ambiguity` flag's job, and it asks
  a human.
