# Where this runs: desktop, or hosted?

Short answer: **desktop.** A hosted version can exist, but not as the way real
client files are processed, and a Vercel deployment is a *demo*, not the product.

## Why not hosted

The documents are on the adviser's machine or the firm's network drive, and the
tool's whole posture is that they stay there. Hosting means uploading a client's
fact find — assets, liabilities, income, dependants, health disclosures for
insurance advice — to somebody else's computer.

That is not a deployment choice. It is:

* a **data-residency** decision. SYSTEM.md section 10 defers Australian residency
  to pilot stage, which holds precisely because nothing currently leaves the
  building. Vercel serves from the US by default;
* a **licensee** decision, not the adviser's and not ours;
* the end of the **no-network-egress** property that `security.py` currently
  tests for and that a licensee can be shown rather than promised.

None of that makes hosting impossible. It makes it build step 6 — "move storage
to Australian-region cloud, **only when a pilot needs it**" — with tenant
isolation, audit logging and a penetration test alongside it.

## What runs where

| Target | What it is | Status |
|---|---|---|
| **Local web UI** | `python3 -m advicefiler.ui` — serves on 127.0.0.1, reads local files, uploads nothing | works now |
| **Packaged desktop app** | the same server wrapped so nobody opens a terminal | next |
| **Vercel demo** | the same interface over the synthetic samples, no upload, for showing people | easy, and worth doing |
| **Hosted multi-tenant** | AU region, isolation, audit, pen test | build step 6, gated on a pilot |

One codebase. The UI talks to a small JSON API; what changes between targets is
what is behind it and where the files live.

## Running it now

No dependencies for the demo:

```bash
python3 -m advicefiler.ui --demo
```

Opens `http://127.0.0.1:8765/` with the ten synthetic documents — including the
illegible scan and the authority to proceed with no advice record behind it, so
the flags and the review queue have something to show.

Against real files:

```bash
python3 -m pip install -r requirements.txt      # PDF and Word support
python3 -m advicefiler.ui --input ~/Documents/smith-family \
                          --clients "/Volumes/Advice/Clients" \
                          --dest "/Volumes/Advice/Clients"
```

Bound to `127.0.0.1`, never `0.0.0.0` — it is not reachable from the network,
including from another machine on the same desk.

## Packaging it as a desktop app

The local server is already the hard part. Wrapping it is mechanical, and the
options differ mainly in what the firm's IT has to approve:

* **PyInstaller / py2app** — one binary per platform, no Python install needed.
  Smallest change: the same `ui.py`, started by a launcher, opening the browser.
* **Tauri or Electron shell** — a real application window instead of a browser
  tab, with a native folder picker. Worth it mainly because "type a path into a
  text box" is a poor experience for the people who will actually use this.
* **Code signing** — the step that is easy to forget and blocks deployment.
  Apple notarisation and a Windows certificate, both with lead time.

The folder picker is the substantive gap: a browser cannot give a web page a real
directory path, which is why the current UI asks for one to be typed. A desktop
shell fixes that properly.

## The Vercel demo

Worth building, as a **showcase with synthetic data only**:

* the same interface, the same sample documents, no upload, no file writing;
* precomputed output — a static manifest, so there is no server and no place for
  a real document to be sent even by accident;
* a clear label saying it is a demonstration on fabricated documents.

That is genuinely useful for showing a firm what the tool does before asking them
for anything. What it must not become is a place someone drags a real client
folder, so it should have no upload control at all rather than a disabled one.
