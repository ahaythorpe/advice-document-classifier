# Security and client data

Phase 1 is a local tool. It reads files on one machine, makes no network calls,
stores no credentials, and writes nothing without a human decision. That shape is
most of the security posture, and keeping it is worth more than any control added
on top.

## What is actually being protected

Real advice files contain client names and addresses, assets and liabilities,
income, dependants, tax file numbers on older forms, and — where insurance advice
is involved — health disclosures. The client register is worse again: it is a
list of *every* client the firm has, in one file.

Retention is 7 years for advice records (`reg 7.7.09C`), so this data is kept for
a long time, and a leak found later is still a leak.

## The realistic threats

Not an attacker. Phase 1 is not internet-facing and has no attack surface worth
the name. The ways this actually leaks are mundane, and the controls are aimed at
them:

| How it leaks | Control |
|---|---|
| A manifest or failure log sent to a developer, a vendor, or pasted into a chat | `--redact` |
| Run output committed to a repository | deny-by-default `.gitignore`, verified |
| Filed documents left readable by everyone on a shared drive | owner-only file modes |
| A client register at default permissions | written `0600` |
| Client data sent to a third-party API without anyone deciding to | no network calls, and that is tested |
| A cloud backup landing offshore | region required, non-AU refused |
| Nobody able to say what the tool did to a file | audit log with a content digest |

## Controls, and what each is worth

**No network egress.** `advicefiler/` imports nothing that opens a socket, and
`security.network_modules_used()` checks it. There is a test asserting it comes
back empty. This is the control that matters most today, because it means client
text cannot leave the machine by accident — and it is stated as a demonstrable
property rather than a promise, because a licensee will ask.

This changes at build step 4. An LLM classifier sends document text to a model
provider, and that is a decision needing the licensee's agreement, a data
processing agreement, and a documented region — not a library upgrade.

**Redaction.** `--redact` replaces client names, filenames and paths with stable,
non-reversible pseudonyms while keeping types, confidences, flags, dates and
event structure. Stable, so a redacted manifest is still analysable — the same
client is the same token across documents and runs. The knowledge base's own
vocabulary survives (document labels, advice subjects, folder names), because
those come from a closed set and identify nobody.

That last part is a security decision, not a convenience one. Redacted output
nobody can read is not a safe default: it is the reason somebody attaches the
unredacted version instead.

**Owner-only permissions.** Filed documents, the audit log, the idempotency
state and any written register are `0600`, their directories `0700`. Best effort
— a network share or a synced cloud folder may not honour POSIX modes — but
nothing is ever *widened*.

**Audit trail.** Every filed document appends to `_advicefiler/audit.jsonl`: when,
from where, to where, what type, which client, at what confidence, and the
SHA-256 of the file as written. The digest answers the question a compliance
reviewer actually asks about an automated filing step — is the document in the
file the document that was classified.

**Nothing is written without a decision.** No `--commit`, no write. No approval
for that document, no write. Never overwrite a different file. Documents queued
for review default to `reject`, so the safe outcome is the one you get by doing
nothing.

**Data residency.** A cloud backup must declare its region and must be Australian
unless explicitly overridden. See SYSTEM.md section 10 — residency is deferred to
pilot stage, which holds only while files stay in the building.

## What is deliberately NOT done

**Encryption at rest.** That belongs to the volume: FileVault, BitLocker, the
DMS, the bucket. A home-grown encryption layer inside a tool that has not been
penetration-tested would be worse than honest reliance on the platform — it moves
key management into an application nobody has reviewed, and invites the firm to
believe a guarantee that has not been earned.

**What to do instead:** run this on an encrypted volume. On macOS confirm
FileVault, on Windows confirm BitLocker. If the destination is a network share,
that is the firm's IT question, and the honest answer is that this tool does not
change it either way.

**Access control.** There is one user: whoever is at the keyboard. Multi-user
isolation arrives with the hosted version at build step 6, alongside the
penetration test.

**Secure deletion.** `--mode move` leaves whatever the filesystem leaves. For
anything sensitive enough to need shredding, use `copy` and let the firm's own
process handle the original.

## Before real client data

- [ ] Encrypted volume confirmed
- [ ] `git status` clean of anything under `input/` or `output/`
- [ ] `--redact` used for anything leaving the machine
- [ ] Backup region declared, and Australian
- [ ] The firm knows the tool is running against their files

## Before a pilot

From SYSTEM.md section 10, none of which are build-blockers today and all of
which block a firm's real data at scale: Australian data residency,
multi-tenant isolation, audit logging at the account level, penetration test,
PI and cyber insurance, and a financial-services lawyer on the AFSL boundary and
liability terms.

Add one: if step 4's LLM classifier is in the pilot, the model provider's terms,
region and retention are part of the residency answer, not separate from it.
