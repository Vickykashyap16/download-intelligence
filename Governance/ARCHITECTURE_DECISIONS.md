# Architecture Decisions — Downloads Intelligence Pipeline

The permanent architectural reference for this project. Every entry below is a decision already made and frozen (Modules 01–03) — this document doesn't propose anything new; it records what was decided, why, and what it cost, so a future contributor (or a future Claude session) never has to reverse-engineer intent from code alone. New decisions get a new entry when they're made, following the same five-part format, numbered sequentially after the last existing entry (never renumbered, never reusing a removed number); existing entries are never rewritten to look like they were obvious from the start — a revised decision gets a new, dated entry with a forward pointer added to the original, per `Governance/DOCUMENT_GROWTH_POLICY.md`.

Format for every decision: **Context** (the problem being solved) → **Decision** (what was chosen) → **Why it was chosen** (the reasoning) → **Trade-offs** (what was given up) → **Consequences** (what this means for everything built afterward).

---

## 1. UUID file IDs (not path- or content-derived)

**Context:** Module 01 needs a permanent identity for every discovered file, assigned once and never recomputed, that survives the file being moved/renamed later (Module 07's job) without breaking continuity with its existing Database record.

**Decision:** `file_id` is an arbitrary UUID4, assigned once at first discovery, never derived from the file's path or its byte content.

**Why it was chosen:** Two alternatives were considered and rejected during design. A path-derived ID (e.g. hashing the absolute path) breaks the moment Module 07 moves or renames a file — the ID would either change (severing continuity with the existing record) or require perfect discipline never to re-derive it post-move. A content-derived ID (hashing file bytes) would make two different physical files with identical content collide onto the same ID, silently merging their Database records before Module 04 (Duplicate & Version Detection) ever gets a chance to decide what to do about the duplicate — Module 04's entire job is comparing content across *different* IDs to find duplicates; a content-derived ID would make that comparison meaningless.

**Trade-offs:** An arbitrary ID carries no inherent meaning — you can't look at a `file_id` and infer anything about the file without a Database lookup. This is accepted as strictly better than either alternative's failure mode.

**Consequences:** `content_hash` (SHA-256 of bytes) and `current_path` (live location) are kept as separate, independently-meaningful fields rather than folded into identity. `find_by_current_path()` exists specifically to let re-scanning recognize "I've already seen this file at this path" and reuse its existing `file_id`/`discovered_at` rather than minting a duplicate record — this is re-identification convenience, explicitly *not* duplicate detection (which is Module 04's job, comparing `content_hash` across different paths).

---

## 2. FileRecord ownership model

**Context:** Eight modules will eventually all read and write different parts of one shared data record per file. Without an explicit ownership model, it becomes easy for one module to accidentally overwrite another's work, or to silently depend on a field before the module that populates it has actually run.

**Decision:** Every field on `FileRecord` is owned by exactly one module, stated explicitly in that module's `MODULE_CONTRACT.md` under both "Guarantees" (what it populates) and every *other* module's contract under "DOES NOT MODIFY" (confirming it never touches that field).

**Why it was chosen:** This is the only way multiple modules can depend on a shared, growing record without a coordination mechanism heavier than a pipeline should need (no locks, no transactions — just a documented, tested convention). It also makes a whole class of defect mechanically checkable: an immutability regression test can assert every non-owned field is byte-identical before and after a module runs, rather than relying on code review alone to catch an accidental write.

**Trade-offs:** Requires discipline to keep contracts and code in sync — a module that starts touching a field outside its ownership without updating its contract is a silent contract violation, not something Python itself prevents. Mitigated by requiring the immutability test as a standing regression test (`ENGINEERING_STANDARD.md` §11), not an optional nicety.

**Consequences:** `category`/`classification_signals` are Module 02's; `extracted_metadata` is Module 03's; `suggested_name`/`suggested_destination` are reserved for Module 05; `duplicate_of`/`version_group_id`/`version_rank` for Module 04; `confidence_score`/`confidence_breakdown`/`tier` for Module 06; `processed_at`/`approved_by`/`approved_at`/`reversible` for Module 07. Every module built so far reads earlier modules' fields freely but never writes them — verified independently at both the implementation-audit and release-audit stage for every module, not assumed from the contract alone.

---

## 3. Module ownership boundaries (contract-first, not code-first)

**Context:** With eight modules eventually chaining together, some explicit mechanism is needed to prevent scope creep — a module quietly doing part of a later module's job because it was convenient at implementation time.

**Decision:** Every module's design document states, explicitly, a list of "responsibilities reserved for later modules" — not just what it does, but what it deliberately does *not* do — before implementation begins. Both the implementation audit and the release audit check the actual code against this list, not just against what the module's own contract claims.

**Why it was chosen:** A design review process that only asks "does this do what it's supposed to" misses scope creep, because scope creep usually *looks* helpful in the moment (e.g. Module 03 could have "helpfully" started guessing at a suggested filename while it already has the extracted fields in hand — that's explicitly Module 05's job, not Module 03's, and the design says so).

**Trade-offs:** Some genuinely useful capability is deliberately deferred even when the code to add it would be small, because it belongs to a module that doesn't exist yet and hasn't had its own design review. This is a deliberate cost, not an oversight.

**Consequences:** Module 03 extracts metadata but never suggests a name or destination, even though it has every field a naming template would need. Module 02 detects `ambiguous`/`non_english_detected`/etc. signals but never acts on them to adjust confidence — that's Module 06's job. This keeps each module's review scope bounded and its contract meaningful.

---

## 4. Engine → Provider architecture (three-layer pattern)

**Context:** Modules 02 and 03 both need to combine deterministic logic (which category, which fields are machine-derivable) with judgment-dependent logic (what does this document actually say) in a way that keeps the deterministic parts testable without needing live Claude judgment in every test run.

**Decision:** Both modules are layered identically: a public batch-orchestration function (`classify_batch()` / `extract_metadata_batch()`) → an Engine (`ClassificationEngine` / `MetadataExtractionEngine`) that owns all deterministic-vs-judgment-vs-fallback decision-making → a Provider (an abstract class) that performs the raw judgment call only and knows nothing about when it's appropriate to call it.

**Why it was chosen:** This cleanly separates "what decision gets made" (Engine — pure, deterministic, fully testable with a fake provider) from "how is judgment actually obtained" (Provider — the one piece that can't be unit-tested in the traditional sense, because it requires either live Claude reasoning or a network call to some other model). Without this split, testing the Engine's fallback logic would require either a real Claude session in every test run (impractical) or conflating "the decision logic is wrong" with "the judgment was wrong" (undebuggable).

**Trade-offs:** More classes and indirection than a single function would need for a module where most categories are deterministic anyway (Module 03's own Design Review 1, finding F8, named this explicitly: the full three-layer split is only exercised by roughly seven of twelve categories in Module 03's case). Accepted as a deliberate trade-off: consistency and future extensibility (a category could move from deterministic to judgment-dependent later without an architecture change) outweigh the cost of an unused interface for categories that don't need it today.

**Consequences:** Every future judgment-dependent module (05's naming suggestions, if they end up needing live judgment) should default to this same three-layer shape unless a specific, disclosed reason argues against it — but see decision 5 below for why it's *not* code-shared between modules.

---

## 5. Provider abstraction (deliberately not shared across modules)

**Context:** Module 03's Engine/Provider classes are structurally near-identical to Module 02's. The obvious efficiency move would be to have Module 03 import and extend Module 02's classes.

**Decision:** Module 03 defines its own `MetadataExtractionEngine`/`MetadataExtractionProvider`/`ProviderResponse`/`ProviderMetadata`/`_sanitize_error()` — zero cross-imports from `classification.py` beyond the shared `Category` enum.

**Why it was chosen:** Coupling two modules' internal implementation details (even when they're currently identical) creates a hidden dependency: a future change to Module 02's Engine for Module 02's own reasons could silently affect Module 03's behavior, or block Module 02 from changing at all without a cross-module impact review. Each module's provider boundary is explicitly *not* part of the external contract other modules can depend on (`MODULE_CONTRACT.md`'s "Provider boundary" section states this for both modules) — so nothing outside either module should ever have assumed they were shared in the first place.

**Trade-offs:** Real, acknowledged duplication — the same `_sanitize_error()` logic, the same ABC-enforcement pattern, exists twice in the codebase. This is disclosed explicitly in both modules' design docs as deliberate convention-following, not an oversight, and re-confirmed at every audit stage rather than "fixed" by introducing a shared base class.

**Consequences:** A future module needing this same pattern (e.g. Module 05, if naming ever needs live judgment for ambiguous cases) should write its own Engine/Provider classes following the same shape, not import Module 02's or Module 03's. If a genuine, disclosed reason ever emerges to share this code (e.g. three+ modules with byte-identical logic and a real maintenance cost from the duplication), that would itself be a new architectural decision requiring its own review — not a refactor done casually.

---

## 6. Deterministic before AI (never call a provider when a real answer already exists)

**Context:** Every judgment-dependent module has some categories/fields where a real, non-judgment source of truth exists (a file extension, an EXIF tag, an ID3 tag, a zip's central directory) and some where genuine content understanding is required.

**Decision:** Every Engine checks and exhausts every deterministic source before ever considering a provider call, and for categories where every field has a deterministic source, the provider is never called at all — enforced and verified by tests asserting `provider.received_requests == []` for exactly those categories/fields.

**Why it was chosen:** A provider call (real or, in production, a live Claude judgment call) has a real cost — time, and in a future networked-provider world, money and latency. It's also strictly less reliable than a deterministic read when a deterministic read is available (an EXIF timestamp is either present or not; it's never "probably" present the way a judgment call has a confidence gradient). Calling a provider for something already knowable deterministically is waste at best and a source of inconsistent results at worst.

**Trade-offs:** None identified — this is a strict improvement over calling a provider unconditionally. The only cost is architectural discipline: every new category/field added to a taxonomy must be explicitly assigned to the deterministic or judgment path, not left ambiguous.

**Consequences:** Archive, Application, Video, and Audio never call Module 03's provider at all. Image/Screenshot call it only for the judgment field(s) remaining after EXIF's `capture_date` is resolved. This same discipline should apply to any future module: check what's deterministically knowable first, and never spend a judgment call on it.

---

## 7. `Unknown` instead of guessing

**Context:** Every classification/extraction decision could, in principle, be forced to produce *some* answer even when the actual signal is weak or absent (an unreadable file, a provider failure, content that matches no known pattern).

**Decision:** When a module genuinely cannot determine an answer, it produces an explicit `Unknown` (Module 02's `Category.UNKNOWN`) or `null` (Module 03's per-field fallback) — never a fabricated best-guess presented as if it were a real finding.

**Why it was chosen:** A wrong answer that looks confident is worse than an honest "don't know," because a wrong-but-confident answer can silently propagate through the rest of the pipeline (a fabricated vendor name would flow into a naming template; a fabricated category would route a file to the wrong destination folder) with nothing downstream aware it should be double-checked. An honest `Unknown`/`null` is visible, auditable, and — critically — feeds directly into the confidence-scoring hard floors (`Rules/Confidence Rules.md`: "Unknown category → always `review_required`") that force human review rather than silent misfiling.

**Trade-offs:** More files end up flagged for manual review than would if the system were willing to guess — a deliberate cost in exchange for never silently misfiling something based on a fabricated answer.

**Consequences:** `category=None` (Module 01 never had readable bytes) and `Category.UNKNOWN` (Module 02 tried and failed) are deliberately different states, not conflated — a distinction every module downstream must respect, and one that's already been flagged as "an easy mistake for a future module to make" in Module 02's own `KNOWN_LIMITATIONS.md`. Every fallback path across both Module 02 and Module 03 follows this same honesty-over-confidence principle.

---

## 8. Privacy-first metadata storage

**Context:** `extracted_metadata` is populated by a provider (live Claude judgment, or in the future, potentially another model) reading arbitrary file content — content that could, in principle, contain far more than what any category's defined field set actually needs.

**Decision:** Every category has a **closed taxonomy** — an exhaustive, named list of required and optional fields. Any field name a provider returns that isn't on that list is dropped before it ever reaches `extracted_metadata`, the on-disk store, or the action log. This is enforced structurally at the Engine's validation boundary, not merely requested via a prompt instruction to the provider.

**Why it was chosen:** A prompt instruction ("only extract these fields") can be wrong, ignored, or bypassed by an imperfect or adversarial provider response — trusting it alone would make the privacy guarantee only as strong as the provider's behavior on any given call. A structural check at the trust boundary holds regardless of what the provider actually returns, verified adversarially (a stub/live provider deliberately returning an out-of-taxonomy field like `"ssn"` is dropped every time, confirmed by test and by a real UAT run).

**Trade-offs:** A genuinely useful field a provider happens to notice, but that isn't in the taxonomy, is discarded rather than opportunistically kept — a deliberate cost in exchange for a guarantee that doesn't depend on trusting the provider's judgment about what's safe to keep.

**Consequences:** Adding a new field to any category's taxonomy is a business-rule decision (owned by the project owner, formalized in the module's design and eventually `Rules/`), not something Module 03's code can be casually extended to capture more of "just in case." This same closed-taxonomy principle should be the default for any future module that persists provider-derived content.

---

## 9. Redaction philosophy

**Context:** Some fields are *designed* to hold a deliberately truncated, safe view of a value that would itself be unsafe to store in full (Bank Statement's `account_last4`).

**Decision:** For any field with this specific shape (a truncated-safe view of an otherwise-prohibited value), the Engine applies an exact, deterministic, testable redaction rule at the trust boundary — not a qualitative prompt instruction. Module 03's concrete rule: strip non-digits, redact to `null` if more than 4 digits remain, pass through unchanged at 4 digits or fewer (including empty). Only the field *name*, never the value, is recorded when redaction occurs.

**Why it was chosen:** This is the same reasoning as decision 8, applied specifically to the one field type where the *risk* isn't "an unrequested field slipped through" but "the requested field itself might contain more than it should." A qualitative rule ("looks like an account number") would need to be invented ad hoc by whoever implements it and would vary in strictness by implementer — Module 03's own first design review (finding F2) caught exactly this gap and required the rule be made precise enough to unit-test deterministically before implementation, not descriptive enough to vary.

**Trade-offs:** The rule is deliberately scoped to the one field type it was designed for (`account_last4`), not generalized into a blanket digit-pattern scanner across every field — a blanket scanner was explicitly considered and rejected as actively harmful, because it would misfire on fields meant to legitimately hold long numbers (e.g. `invoice_number`). This means a future category with a similarly-shaped risk (a truncated-safe view of a prohibited value) needs its own explicit redaction rule design, not automatic coverage from an existing one.

**Consequences:** Verified adversarially, not just against well-behaved test doubles — Module 03's UAT deliberately fed the *full, real* account number as the "live" judgment answer (not a pre-truncated one) specifically to prove the Engine's redaction catches an imperfect provider response, not only a well-behaved one. Any future field identified as having this same "truncated-safe view of a prohibited value" shape should get the same treatment: an exact rule, specified before implementation, tested at every boundary case, and verified adversarially during UAT.

---

## 10. Action log philosophy

**Context:** Every module needs to record what happened to every file it touched, in a way that's both machine-readable (for a future undo mechanism) and complete enough to reconstruct why a decision was made without re-running the pipeline.

**Decision:** One append-only, JSON-lines file (`Runtime/Logs/action_log.jsonl`), one line per action, with a shared minimal shape (`batch_id`, `file_id`, `action`, `from`, `to`, `timestamp`, `approved_by`) plus an `action`-specific `details` object carrying whatever that action type needs to be fully reconstructable (mode, fallback reason, provider metadata, redacted fields, etc.). Every module adds its own `action` value to this shared vocabulary, and — a rule established after being violated twice — the canonical schema doc must be updated in the *same* release cycle that introduces a new action type, not left for a later audit to catch.

**Why it was chosen:** A single append-only log is simple to reason about, trivially supports "replay every line for a batch_id with from/to swapped" as the undo mechanism (Module 07's eventual job), and keeps every module's logging behavior consistent rather than each module inventing its own log format. JSON-lines specifically (rather than one large JSON array) means a crash mid-write only ever corrupts the last, incomplete line, not the entire log.

**Trade-offs:** The log grows unboundedly and is never rotated or pruned in v1 — accepted as fine at v1 volumes, flagged as a `Version 2` concern if it ever becomes one. The shared minimal shape means some action types have `details` fields that don't apply to others (e.g. `to` is always `null` for `discover`/`classify`/`extract_metadata`, only populated for eventual `move_rename`) — accepted as simpler than a per-action-type top-level schema.

**Consequences:** `discover` (Module 01), `classify` (Module 02), and `extract_metadata` (Module 03) have each, in turn, needed to be added to the canonical schema doc — and twice now (`classify`, then `extract_metadata`), that addition was missed at release time and only caught by a subsequent audit. This has now been elevated to an explicit rule (§10 of `ENGINEERING_STANDARD.md`) precisely because it recurred: any future module adding a new action type must update the schema doc as part of that module's own release, not rely on the next module's audit to catch the omission.

---

## 11. Metadata store philosophy

**Context:** Every module needs to read and write a shared, per-file, cumulative record (`FileRecord`) across potentially many scan sessions over the file's lifetime.

**Decision:** `Database/Metadata/metadata_store.json` is one cumulative JSON array, upserted by `file_id` on every `save_file_record()` call — never a per-scan/per-batch snapshot, never truncated automatically. Every module's field-of-ownership (decision 2) is what makes concurrent-in-spirit (though not concurrent-in-execution — the pipeline is strictly sequential) enrichment of this one shared record safe.

**Why it was chosen:** A per-batch snapshot would lose a file's history the moment a second scan ran; upserting by permanent `file_id` (decision 1) keeps exactly one, ever-growing-in-detail record per real file, regardless of how many times it's been scanned or which modules have processed it so far.

**Trade-offs:** `save_file_record()` performs a full read-modify-write of the *entire* cumulative store on every single call, and every batch-processing module (`classify_batch()`, `extract_metadata_batch()`) calls it once per file in its loop — an O(N×M) cost (N files being processed times M total records in the store) that's explicitly disclosed as a known limitation in both Module 02's and Module 03's `KNOWN_LIMITATIONS.md`, not silently accepted as free. Not a problem at v1 volumes; flagged as the first thing worth optimizing (batch-level load/write instead of per-file) if store size or batch frequency grows materially.

**Consequences:** Every future module's own batch orchestration should call `save_file_record()` once per file, consistent with the existing pattern, and should re-disclose this same O(N×M) cost in its own `KNOWN_LIMITATIONS.md` as its own problem too, rather than treating it as fully "owned" by whichever module first raised it.

---

## 12. Database philosophy (plain JSON in v1, deliberately)

**Context:** `Database/` needs a persistence mechanism for `Metadata/`, `FileIndex/`, `History/`, and `Learning/`.

**Decision:** Plain JSON files in v1 (no SQLite, no other database engine), with an explicitly planned migration path documented (`Database/README.md`) for if/when it's needed.

**Why it was chosen:** At v1's expected volume (a single user's Downloads folder, scanned on-demand or on a schedule — not a high-throughput multi-tenant system), a real database engine's operational complexity (schema migrations, a connection/driver dependency, transaction semantics the pipeline doesn't actually need since it's strictly sequential) isn't justified by anything JSON can't already do. This is the same "avoid over-engineering" discipline applied elsewhere in this project (e.g. rejecting a blanket redaction scanner, decision 9).

**Trade-offs:** No real indexing, no query language, no concurrent-write safety beyond "the pipeline only ever runs one batch at a time" — accepted because none of these are currently needed. `find_by_current_path()`'s linear scan and `save_file_record()`'s full read-modify-write (decision 11) are both direct costs of this choice, both disclosed rather than hidden.

**Consequences:** A future SQLite migration (named explicitly in `ROADMAP.md` Version 2) would be a genuine architectural change requiring its own design review, not a drop-in swap — every module's `storage/database.py` usage would need re-verification against the new engine's actual behavior, not assumed identical.

---

## 13. Independent module versioning

**Context:** Eight modules will evolve at different paces once all are built — some frozen for a long time, others iterating.

**Decision:** Each module has its own independent semver (`MAJOR.MINOR.PATCH`), tracked in its own `MODULE_STATUS.md` and cross-referenced in the shared `Release/VERSIONS.md` ledger. A separate, single **Pipeline Version** tracks the whole project's overall maturity, bumped deliberately at milestones, never derived automatically from the module versions.

**Why it was chosen:** Coupling every module to one shared version number would force an unrelated module's version to bump every time any other module changed, destroying the signal a version number is supposed to carry (does *this* module's contract still hold). Independent versioning lets a downstream module declare a dependency on a specific upstream contract version, in principle, once that becomes relevant.

**Trade-offs:** Two numbers to track and keep consistent (module version and pipeline version) rather than one — accepted as necessary given decision 2's ownership model already implies modules are meant to evolve somewhat independently.

**Consequences:** `MAJOR` is reserved specifically for a `MODULE_CONTRACT.md`-breaking change (decision 17 in `ENGINEERING_STANDARD.md`'s breaking-change policy) — not for any implementation change, however large, that doesn't touch the external contract.

---

## 14. Pipeline versioning

**Context:** Beyond each module's own version, some single number is useful for communicating "how far along is this project, overall."

**Decision:** Pipeline Version is bumped once per module release (currently `0.1.0` → `0.2.0` → `0.3.0` for Modules 01/02/03's releases respectively), with `1.0.0` reserved for "all 8 modules built and passing end-to-end" as a deliberately meaningful milestone, not an automatic function of the module count or versions.

**Why it was chosen:** Gives the project owner (and any future reader of `Release/VERSIONS.md`) a single, at-a-glance signal of overall progress without needing to cross-reference eight separate module versions.

**Trade-offs:** Somewhat arbitrary exactly *when* it bumps within a module's own release cycle (chosen here: once per module's full release, not at intermediate stages like design-freeze or implementation-complete) — a convention, not a law of nature, but a documented and consistently-applied one.

**Consequences:** `Governance/PROJECT_ROADMAP.md` tracks this number as the primary at-a-glance milestone marker; every future module release bumps it by the same convention.

---

## 15. Module contracts (as the primary inter-module dependency mechanism)

**Context:** With no shared type system enforcing cross-module field access at compile time (Python, dataclasses, no static contracts), some other mechanism is needed to make "what can I safely depend on from an earlier module" a checkable fact rather than an assumption.

**Decision:** `MODULE_CONTRACT.md` per module (starting with Module 01) is the authoritative, tested statement of INPUT/OUTPUT/guarantees/DOES NOT MODIFY — and it is explicitly the *only* part of a module's design that later modules may depend on. A module's internal architecture (its Engine/Provider split, its private helper functions) is never part of the contract and may change freely as long as the contract's behavior holds.

**Why it was chosen:** This is what lets Module 03 be built with confidence about what Module 02 guarantees, without needing to read or understand `classification.py`'s internals — and, symmetrically, lets Module 02's internals be refactored later (if ever needed) without necessarily being a breaking change to Module 03, as long as `classify_batch()`'s documented behavior doesn't change.

**Trade-offs:** Requires every module's contract to be written thoroughly and kept honest — a contract that's incomplete or stale is worse than no contract, because it creates false confidence. Mitigated by requiring both the implementation audit and release audit to re-verify the contract against actual code, not just re-cite the document.

**Consequences:** `Governance/PIPELINE_CONTRACT_VERIFICATION.md` formalizes exactly how this re-verification happens at every future freeze, rather than being reinvented ad hoc each time.

---

## 16. Frozen module policy

**Context:** Once a module has been through its full review/audit lifecycle and approved, some explicit statement is needed that later work (a new module, a bug elsewhere) will not casually reopen it.

**Decision:** A module is "Frozen" per the definition in `ENGINEERING_STANDARD.md` §15 — and once frozen, it is not modified except for a project-owner-authorized genuine-defect fix or a deliberate new version release. This is now an explicit, standing instruction going into Module 04's work: "Do not modify Modules 01, 02, or 03 unless explicitly requested."

**Why it was chosen:** Without this discipline, every new module's implementation risks becoming an opportunity to "improve" something upstream informally, which erodes the entire point of having gone through a rigorous freeze process in the first place — a frozen module's guarantees are only as trustworthy as the project's actual discipline in leaving it alone.

**Trade-offs:** A genuinely better idea for an already-frozen module has to wait for an explicit request and its own mini-review, rather than being applied opportunistically while working nearby. Accepted as the cost of the guarantee being real.

**Consequences:** Every audit performed on a new module explicitly checks (via mtime comparison and isolated regression re-runs) that no earlier, frozen module's source was touched — not assumed from "I don't remember touching it."

---

## 17. Dependency chain (strictly linear in v1)

**Context:** Eight modules could, in principle, have a complex dependency graph (parallel stages, conditional branches). A decision was needed about how simple or complex this should be for v1.

**Decision:** The pipeline is a strict linear chain — Module 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08, each depending only on the one immediately before it, with no module skipping ahead or branching (`Release/DEPENDENCY_DIAGRAM.md`).

**Why it was chosen:** A linear chain is the simplest structure that satisfies the actual v1 requirement (each stage genuinely does depend on the output of the one before it — you can't classify a file you haven't discovered, can't extract metadata from a file you haven't classified, and so on) and keeps every module's contract review scoped to exactly one upstream dependency, not an arbitrary subset of seven others.

**Trade-offs:** No parallelism between stages even where it might theoretically be possible (e.g. metadata extraction for deterministic categories doesn't truly need classification's *judgment* fields, only its category label) — accepted as unnecessary complexity for v1's actual volume and execution mode (Manual, on-demand).

**Consequences:** Any future version that introduces branching or parallel stages must update `Release/DEPENDENCY_DIAGRAM.md` explicitly — it's deliberately drawn as a single chain specifically because that's still true today, not because branching was never considered.

---

## 18. Error handling philosophy

**Context:** Every module processes a batch of files where any individual file could fail for reasons ranging from "genuinely corrupted" to "an implementation bug nobody anticipated."

**Decision:** Two layers of defense, consistently applied: (1) each module's Engine catches every *anticipated* failure mode explicitly (provider unavailable, provider exception, malformed content) and converts it into a normal, named fallback result; (2) the batch-orchestration layer wraps the Engine call in one more try/except as a last-resort safety net for anything genuinely unanticipated, logging an `error` action and continuing to the next file rather than aborting the whole batch.

**Why it was chosen:** Anticipated failures deserve specific, informative handling (a real `fallback_reason`, not a generic catch-all) because they're common enough and understood well enough to handle precisely. But no anticipated-failure list is ever complete, so a final, generic safety net is required regardless — the alternative (an unhandled exception aborting an entire batch because of one bad file) is unacceptable for a tool meant to run unattended over dozens or hundreds of real files.

**Trade-offs:** Two layers of error handling is more code than one, and it's possible for the specific/generic layers to overlap in what they catch if not written carefully — mitigated by each layer's tests explicitly verifying which layer catches which class of failure (e.g. a regression test that forces a failure *inside* the Engine's own internal routing, specifically to prove the outer safety net still works even when the Engine's own handling doesn't apply).

**Consequences:** Every future module should implement both layers from the start, not add the outer safety net reactively after a real crash. `_sanitize_error()` (a sanitized, length-bounded diagnostic helper) exists in both Module 02 and Module 03 specifically because this was learned as a gap once (Module 02's release audit F3) and deliberately built in from day one for Module 03 rather than being rediscovered.

---

## 19. Fallback philosophy (never guess, never crash, always disclose)

**Context:** Closely related to decisions 7 and 18, but specifically about what a fallback *result* looks like once a failure has been caught.

**Decision:** A fallback never fabricates a plausible-looking value. It sets the affected field(s) to their honest "not found" state (`Unknown`/`null`), preserves any *other* value already legitimately found for that same record (a provider failure on one field never discards a sibling deterministic field already resolved), sets an explicit `fallback_used`/`fallback_reason` pair, and — since the implementation-audit lesson that prompted decision 18's `_sanitize_error()` — captures a sanitized diagnostic string explaining *why*, not just *that*, a fallback occurred.

**Why it was chosen:** This is the concrete mechanism that makes decisions 7 and 18 actually true in practice rather than just stated as principles — every fallback is independently auditable from the action log alone, without needing to reproduce the original failure.

**Trade-offs:** More log detail per fallback than a bare "failed" flag would need — accepted because the whole point of a fallback strategy is that a human (or a future module) can trust and act on the disclosure without re-investigating from scratch.

**Consequences:** Every future module's own fallback strategy should follow this exact shape: honest not-found value, preserved sibling data, named reason, sanitized diagnostic — not a bespoke shape invented per module.
