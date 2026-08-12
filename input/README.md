# input/

Real client documents go here, one folder per intake batch (normally one client
folder from the firm).

```
input/
  nguyen-family/        <- one intake batch
    scan_001.pdf
    ...
  ground_truth.json     <- your labels for real documents
```

**Everything in this directory except this file is git-ignored**, and
`.gitignore` additionally excludes `*.pdf` and `*.docx` anywhere in the tree.
Real advice files contain client names, assets and liabilities, income,
dependants, and health disclosures where insurance advice is involved. None of
that may enter version control, including extracted text and run output.

Ground truth for real documents belongs in `input/ground_truth.json`, **not** in
the repository's `ground_truth.json` — that one is for the synthetic samples, and
adding real labels to it would put client names into git history.

```bash
python3 harness.py --input input/nguyen-family \
                   --ground-truth input/ground_truth.json
```

See `docs/STEP3-RUNBOOK.md` for the whole loop.
