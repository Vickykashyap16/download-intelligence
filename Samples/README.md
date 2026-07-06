# Samples

Canonical example files — a few real, illustrative examples of each kind of input this automation handles. These are for *reference*: what does a real invoice/photo/video/document actually look like, so the spec and rules can be checked against reality.

This is distinct from `Tests/`, which holds *executable validation datasets* (scenario-based batches used to run and check the pipeline, including duplicates/corrupted files/mixed folders). Samples answers "what does an Invoice look like"; Tests answers "does the pipeline handle a folder full of these correctly." Deliberately no overlap: this folder does not have Duplicate/Corrupted/Mixed subfolders — those scenarios belong in `Tests/`.

- `Invoices/` — a real invoice or two (ideally one simple, one messier — multiple line items, a foreign currency, etc.)
- `Images/` — a product photo and, separately, a real screenshot (both help validate the Screenshot vs. Image split in `Rules/Classification Rules.md`)
- `Videos/` — one example video file
- `Documents/` — one of each other document type you actually get: a resume, a bank statement, a contract, and a generic document (manual/certificate/letter) if you have one — this last one validates the new `Document` (generic) category

## Note
This folder replaces the example-holding role originally planned for `Build-out/00 Pre-build context & examples/`. Drop your example files here instead of there.

Nothing here yet — populate when convenient, no rush before implementation starts.
