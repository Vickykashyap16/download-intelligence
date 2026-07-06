# Tests

Executable validation datasets for running the pipeline against — scenario-based, not category-based. For canonical single examples of each file type (what does an invoice actually look like), see `Samples/` instead; this folder is deliberately scenario-focused with no overlap.

Files go directly in the relevant subfolder (real or realistic synthetic examples — same privacy care as production: no real bank account numbers, etc.).

- `Small Batch/` — a handful of files (5–10), one or two per category. First thing to validate against — the whole pipeline should run cleanly on this before anything else.
- `Mixed Downloads/` — a realistic messy folder snapshot: several categories at once, some junk/ignorable files mixed in, roughly what a real Downloads folder looks like on a given day.
- `Duplicate Files/` — exact duplicates and near-duplicate images, plus a version chain (e.g. `Resume_v8.pdf` / `Resume_v9.pdf`) to validate `04 Duplicate & Version Detection`.
- `Corrupted Files/` — a locked/password-protected PDF, a truncated/corrupted file, a zero-byte file — validates that these get routed to review rather than crashing a batch.
- `Large Batch/` — volume testing (50–100+ files) once the core pipeline is proven on the smaller sets.

## Priority order
Don't feel obligated to populate all five before building anything. Recommended order: **Small Batch → Mixed Downloads → Duplicate Files → Corrupted Files → Large Batch.** Volume/stress testing (`Large Batch`) matters far less than correctness testing until the core pipeline is already working — treat it as the last one populated, not a v1 blocker.

Nothing here yet — populate as example files become available.
