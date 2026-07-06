# Pipeline Contract Verification — Process Design

**This document designs a process. It is not implemented, and no code exists for it yet.** It formalizes checks that were, until now, performed ad hoc (and slightly differently each time) during Modules 01–03's implementation and release audits — into one repeatable, checklist-driven gate that runs whenever a module is frozen. Building the actual tooling (scripts, automated checks) is future work, to be scoped and approved separately; this document defines *what* must be verified and *how*, so that future work has a concrete spec to implement against rather than reinventing the checklist per module.

## Relationship to `ENGINEERING_STANDARD.md`

This document is **not** a second or parallel audit. `ENGINEERING_STANDARD.md` §7A names this checklist as the mandatory, mechanical gate that forms one required part of the release audit stage (stage 8 of §1) — the release audit is complete only once this gate has passed (or has approved exceptions) *and* the separate qualitative release review (§7's UAT-evidence-quality/known-limitations/forward-compatibility review) has also found no unresolved findings. Nothing below duplicates `ENGINEERING_STANDARD.md`'s content: that document says *when* this gate runs and *why* it exists; this document says exactly *how* each check is performed.

## When this runs

Once per module, as the mandatory gate within the release-audit stage (`ENGINEERING_STANDARD.md` §7A), after UAT and before the module is declared Frozen. This is the final mechanical gate — a module does not freeze until every check below either passes or has an explicitly documented, approved exception.

## How to read each check

Every check states: **Purpose** (why this check exists), **Method** (how it's actually performed — today, manually; in the future, potentially scripted), **Pass criteria** (the specific, checkable condition for a pass), **Failure criteria** (what a failure looks like, concretely), and **Required evidence** (what must be captured/shown to prove the check was actually performed, not just asserted).

---

## 1. FileRecord compatibility

**Purpose:** Confirm the module being frozen has not changed the shape, meaning, or serialization of any `FileRecord` field it doesn't own — the shared data record every module depends on.

**Method:** Diff `src/models/file_record.py` against its state immediately before this module's implementation began (via source control if available, or a preserved pre-implementation copy). For every field the module does not own (per its `MODULE_CONTRACT.md`'s "DOES NOT MODIFY" list), confirm its type annotation, default value, and position in the dataclass are byte-identical to before.

**Pass criteria:** Zero changes to any field outside the module's own ownership. Any change to a field the module *does* own is itself checked against that module's own `MODULE_CONTRACT.md` (its stated guarantees) for consistency, not against this check.

**Failure criteria:** Any type, default, or field-name change to a field owned by a different module — even one that "looks harmless" (e.g. widening `Optional[str]` to `Optional[object]`) — is a failure requiring either a revert or an explicit, approved breaking-change process (`ENGINEERING_STANDARD.md` §17) for the *owning* module, not a silent side effect of an unrelated module's release.

**Required evidence:** The diff itself (or the specific confirmation that no diff exists), attached to or referenced from the module's `RELEASE_AUDIT.md`.

---

## 2. Module contract compatibility

**Purpose:** Confirm every upstream module's `MODULE_CONTRACT.md` still accurately describes that module's actual behavior — i.e., the module being frozen hasn't silently invalidated a guarantee an earlier module made.

**Method:** Re-read every upstream module's `MODULE_CONTRACT.md` fresh (not from memory) and re-run that module's own regression test suite in isolation (`ENGINEERING_STANDARD.md` §19's isolated re-run requirement). Cross-check the new module's own contract's "INPUT: Receives" section against exactly what the upstream contract's "OUTPUT: Produces"/"Guarantees" sections promise — every field the new module assumes is present must trace to an explicit upstream guarantee, not an observed-but-undocumented behavior.

**Pass criteria:** Every upstream module's isolated test suite passes at its pre-existing count, with no new failures. Every field the new module's contract assumes from upstream is traceable to an explicit guarantee in that upstream module's own contract document.

**Failure criteria:** Any upstream test regression, or any assumption the new module makes about upstream data that isn't backed by an explicit contract guarantee (an implicit, unstated dependency — e.g. assuming a field is always populated when the upstream contract only guarantees it "usually" is).

**Required evidence:** The isolated re-run's pass count for every upstream module (e.g. "Module 01/02 isolated: 118/118, unchanged"), and an explicit statement in the new module's `MODULE_CONTRACT.md` of which upstream guarantees it depends on.

---

## 3. Database compatibility

**Purpose:** Confirm the module being frozen has not altered how `Database/Metadata/metadata_store.json` (or any other `Database/` file) is structured, read, or written in a way that would break an earlier module's ability to load records it previously wrote, or vice versa.

**Method:** Load a metadata store snapshot written entirely by the pre-existing (upstream-only) modules, then run it through the new module's own batch function. Confirm every field the new module doesn't own round-trips unchanged, and every field it does own is added/populated without disturbing the record's overall JSON shape (key order/formatting differences are acceptable; data-shape differences are not).

**Pass criteria:** A pre-existing record, run through the new module, gains only the new module's owned field(s) and is otherwise identical on reload.

**Failure criteria:** Any pre-existing field's value, type, or presence changes as a side effect of the new module processing that record; any change to `_write_metadata_store()`'s or `_reconstruct_typed_fields()`'s core read/write behavior that isn't explicitly scoped to the new module's own typed-field needs.

**Required evidence:** A before/after diff of a representative multi-module test record, and confirmation that `storage/database.py`'s shared functions (`load_metadata_store()`, `save_file_record()`, `_write_metadata_store()`) were not modified — or, if they were, an explicit statement of what changed and why, reviewed under the breaking-change policy.

---

## 4. Serialization compatibility

**Purpose:** Confirm any new field the module introduces serializes to and deserializes from JSON correctly, and that `_reconstruct_typed_fields()` (or its future equivalent) correctly handles or deliberately ignores it.

**Method:** For any new field requiring typed reconstruction (an enum, a nested dataclass — as `Category`/`ClassificationSignals` required), verify a full save → reload round-trip preserves the real Python type, not a plain string/dict. For any new field that's intentionally left as a plain dict/primitive (as `extracted_metadata` deliberately is), verify the design's own stated reason for not needing typed reconstruction still holds.

**Pass criteria:** A round-trip test (write, reload, compare) passes for every new field, using the real on-disk JSON path, not an in-memory-only shortcut.

**Failure criteria:** A field that silently reloads as the wrong type (e.g. an enum reloading as a plain string) with no immediate test failure — this is the exact class of gap Module 02's typed-field (de)serialization work was built specifically to prevent, and any future field with structure beyond a JSON primitive needs the same explicit treatment.

**Required evidence:** The specific round-trip test name(s) and their pass result, cited in `TEST_RESULTS.md`.

---

## 5. Action Log compatibility

**Purpose:** Confirm the module's new action-log entry type(s) are fully documented in the canonical schema, don't collide with an existing action value, and that every consumer of the log (present or planned) can distinguish them correctly.

**Method:** Grep the actual codebase for every string passed as `action=` to `append_action_log()`, across every module. Cross-check this list against `Build-out/08 Logging & Reporting/Metadata & Log Schema.md`'s documented action-value list. Confirm the new module's entry adds a genuinely new, non-colliding value (or correctly reuses `error`/`skip` for its own equivalent cases) and that its `details` shape is documented with the same rigor as existing entries.

**Pass criteria:** Every action value the codebase actually writes appears in the schema doc, with a documented `details` shape, and no two modules use the same action string to mean different things.

**Failure criteria:** Any action value present in code but absent from the schema doc (this has happened twice already — `classify`, then `extract_metadata` — and is exactly what this check exists to catch before release, not after).

**Required evidence:** The grep output (or its equivalent) showing every action value in code, side-by-side with the schema doc's documented list, with zero discrepancies — attached to the release audit.

---

## 6. Documentation consistency

**Purpose:** Confirm no document across the repository makes a claim about the module's status, behavior, or citations that is stale, incomplete, or contradicted by another document.

**Method:** A full-repository grep sweep (not module-folder-scoped) for: the module's own name/number combined with status words ("not started," "next," "scaffold"); any citation to a superseded pointer document; any reference to the module from a sibling module's design/release docs that might now be stale. Cross-check `src/README.md`'s status section, `Release/VERSIONS.md`, `Release/DEPENDENCY_DIAGRAM.md`, and `CHANGELOG.md`'s most recent entries all agree with each other and with the actual code state.

**Pass criteria:** Every live (non-historical) document's claim about the module's status matches its actual, current state. Historical documents (audit records, changelog entries) correctly describe past states and are not required to be "corrected" to reflect the present — only live/current-state documents are checked here.

**Failure criteria:** Any current-state document (status file, README, version ledger) making a claim contradicted by the module's actual, verified state.

**Required evidence:** The grep sweep's output, explicitly distinguishing "historical, correctly describing the past" hits from "live and stale" hits, with the latter count at zero before this check passes.

---

## 7. Dependency graph consistency

**Purpose:** Confirm `Release/DEPENDENCY_DIAGRAM.md` still accurately describes the pipeline's actual module dependency structure after this module's release.

**Method:** Re-read the diagram fresh and confirm the new module's real dependencies (which upstream modules it actually reads from, per its own `MODULE_CONTRACT.md`'s "INPUT" section) match its position in the diagram. Confirm no module skips ahead or reads from a module not immediately before it in the chain (or, if the pipeline is ever no longer strictly linear, that the diagram has been explicitly updated to show the new shape — see `ARCHITECTURE_DECISIONS.md` §17).

**Pass criteria:** The diagram's depicted chain matches the real, verified read-dependencies of every module, including the newly-frozen one.

**Failure criteria:** A module reading from a non-adjacent upstream module without the diagram reflecting this, or a diagram left unchanged when the actual dependency structure has genuinely changed.

**Required evidence:** An explicit statement in the release audit that the diagram was re-checked against the new module's actual `MODULE_CONTRACT.md` INPUT section, not merely assumed unchanged.

---

## 8. Version consistency

**Purpose:** Confirm every document that states a version number (module version or pipeline version) agrees with every other one.

**Method:** Grep every `Release/*.md` and `Release/Module<NN>/*.md` file for "Pipeline Version" and "Module Version" strings. For every *current-state* document (not a historical changelog/version-history entry, which correctly preserves its own point-in-time value), confirm the value matches `Release/VERSIONS.md`'s current table exactly.

**Pass criteria:** Every current-state document's stated Pipeline Version and Module Version match `Release/VERSIONS.md` exactly, with zero discrepancies.

**Failure criteria:** Any current-state document showing a version number that disagrees with the ledger (e.g. a release-notes doc still showing the pipeline's *previous* version).

**Required evidence:** The grep output showing every version-number mention across the new module's release package, confirmed identical.

---

## 9. Rule references

**Purpose:** Confirm every citation from code, design docs, or the module's own contract to a `Rules/*.md` document points at a real, current section — not a superseded document, a since-renamed section, or a business rule that's since been revised without the citation being updated.

**Method:** For every citation to `Rules/*.md` introduced or relied upon by the module being frozen, confirm the cited file and section actually exist and still say what the citation implies they say. Where a regression test already exists for this (e.g. `Rules/Confidence Rules.md`'s citation-and-taxonomy-cross-check test, added after Module 03's implementation audit F2), re-run it and confirm it still passes; where no such test exists for a given citation, perform the check manually and note the gap in `KNOWN_LIMITATIONS.md` as a candidate for a future regression test.

**Pass criteria:** Every `Rules/*.md` citation the module depends on resolves to real, current, accurate content.

**Failure criteria:** A citation pointing at a superseded document (the exact class of drift caught twice already — Module 02's own release audit, and Module 03's implementation audit F3/release audit F3) or at a section whose content has since changed incompatibly with what the citation implied.

**Required evidence:** The specific test name(s) run (if automated) or the specific citations manually checked and confirmed, listed in the release audit.

---

## 10. Ownership boundaries

**Purpose:** Confirm the module being frozen genuinely respects the "DOES NOT MODIFY" list in its own `MODULE_CONTRACT.md` — i.e., that the contract's claim and the code's actual behavior agree.

**Method:** Run (or, if not yet automated, manually perform the equivalent of) an immutability test: construct a record with every field outside the module's ownership set to a distinctive, easily-checked value, run the module's batch function on it, and assert every one of those fields is byte-identical afterward. Cross-check against every *other* module's own contract to confirm none of them claims ownership of a field this module also claims.

**Pass criteria:** The immutability test passes, and no two modules' contracts claim ownership of the same field.

**Failure criteria:** Any non-owned field changed by the module's own processing, or an ownership collision between two modules' stated contracts.

**Required evidence:** The specific immutability test name and its pass result (e.g. `test_extract_metadata_batch_leaves_every_non_owned_field_byte_identical`), plus an explicit cross-check statement that no ownership collision exists across all frozen modules' contracts.

---

## 11. Breaking changes

**Purpose:** Confirm whether this module's release constitutes a breaking change to any earlier, already-frozen module's contract — and if so, that it went through the explicit breaking-change approval process (`ENGINEERING_STANDARD.md` §17), not silently.

**Method:** Diff every earlier module's `MODULE_CONTRACT.md` against its state before this module's work began. Any difference at all is a candidate breaking change requiring explicit justification and project-owner approval before this check can pass.

**Pass criteria:** Either zero changes to any earlier module's contract (the common case), or every change that did occur is explicitly documented in this module's `RELEASE_NOTES.md`'s "Breaking changes" section with the project owner's approval already obtained and cited.

**Failure criteria:** Any undocumented change to an earlier module's contract, or a documented change that lacks explicit approval.

**Required evidence:** The diff (or explicit "no diff" confirmation) for every earlier module's contract document, and — if applicable — a citation to the approval.

---

## 12. Performance assumptions

**Purpose:** Confirm the module's release doesn't silently invalidate a performance assumption an earlier module's `KNOWN_LIMITATIONS.md` or design documented (e.g. "fine at v1 volume, revisit if X grows"), and that the new module's own performance characteristics are measured, not assumed.

**Method:** Re-run the existing large-batch performance observation (`Tests/Large Batch/` or equivalent) through the full pipeline including the new module, and compare the measured time against the previous module's own measured baseline. Confirm any O(N×M)-style cost the new module inherits (e.g. `save_file_record()`'s per-file full-store read-modify-write) is explicitly re-disclosed in the new module's own `KNOWN_LIMITATIONS.md`, not left as only the originating module's problem.

**Pass criteria:** A fresh, measured performance number exists for the full chain including the new module, with no unexplained order-of-magnitude regression versus the prior module's baseline.

**Failure criteria:** No measured number (only an estimate or an assumption that "it's probably fine"), or a measured regression with no investigation/explanation.

**Required evidence:** The specific measured time and file count, cited in `TEST_RESULTS.md`, with an explicit note if any inherited cost is now also disclosed as this module's own concern.

---

## 13. Security assumptions

**Purpose:** Confirm the module's release doesn't introduce a new code-execution, data-exposure, or trust-boundary risk, and that any structural privacy/security control it relies on from an earlier module (or introduces itself) still holds under adversarial input, not just well-behaved test fixtures.

**Method:** Re-confirm, for the new module specifically: no file-content-derived operation executes code or extracts/decompresses untrusted content without specific justification; the module's own trust boundary (its Engine's validation layer, if applicable) rejects out-of-contract data unconditionally, verified by feeding it a deliberately malformed or over-permissive input (not only a well-behaved fake); and any sensitive-value handling (redaction or equivalent) is verified against an adversarial provider response during that module's own UAT, not assumed safe by analogy to an earlier module's UAT.

**Pass criteria:** Every point above is independently, freshly verified for the new module — not inferred from "an earlier module already checked this."

**Failure criteria:** Any adversarial-input test that wasn't actually run for this specific module (relying instead on a similar-sounding check from an earlier module), or any sensitive value observed reaching a log/store/diagnostic in a form the module's own rules prohibit.

**Required evidence:** The specific adversarial test case(s) run for this module and their pass result, cited in `TEST_RESULTS.md`'s Security Review section.

---

## Overall gate result

A module passes Pipeline Contract Verification only when all 13 checks above pass, or every failing check has an explicit, project-owner-approved exception recorded in that module's `RELEASE_AUDIT.md` with a stated reason. This gate result is itself part of the evidence required before a module may be declared Frozen (`ENGINEERING_STANDARD.md` §4/§15) — the release audit references this document's checklist explicitly, rather than performing an unstructured "does everything look fine" pass that varies in rigor from module to module.

## Relationship to existing practice

Every check above already happened, in substance, during Module 03's release audit — this document's contribution is making the checklist explicit, complete, and repeatable, so a future module's release audit can be checked against a fixed standard rather than re-deriving "what should I look for" from scratch each time, and so a gap in coverage (like the two action-log documentation misses, check 5) is structurally less likely to recur a third time.
