# Engineering Standard — Downloads Intelligence Pipeline

The engineering constitution for this project. Every future module (04 through 08, and any version-2/3 work beyond them) follows this process. It is written *from* the discipline Modules 01, 02, and 03 were actually built under — not invented after the fact — so it describes real, already-proven practice, formalized so it survives beyond any one person's memory of "how we did it last time."

This document is generic by design: nothing in it names a specific module, field, or business rule. Module-specific decisions live in `Governance/ARCHITECTURE_DECISIONS.md` (permanent architecture record) and `Rules/*.md` (business rules). This document is process, not content.

## 0. Scope and authority

This standard governs how a module moves from idea to permanently frozen, production-adjacent code. It applies to every pipeline module. It does not apply to one-off scripts, exploratory research, or content produced in a separate research chat per `CLAUDE.md`'s "Separate chats" working rule — those are explicitly out of scope until their conclusions are brought back and formalized through this process.

Nothing in this document overrides the project's non-negotiables (`CLAUDE.md`): never permanently delete anything, every action must be reversible, superseded versions/duplicates get archived not deleted. Any process step below that would conflict with a non-negotiable defers to the non-negotiable.

## 1. Development lifecycle

Every module passes through the same nine stages, in order, without skipping ahead:

1. **Design** (§2)
2. **Architecture review** (§3)
3. **Freeze** (§4)
4. **Implementation** (§5)
5. **Independent implementation audit** (§7)
6. **Integration testing** (§6.2)
7. **User Acceptance Testing** (§6.3)
8. **Independent release audit, including the mandatory Pipeline Contract Verification gate** (§7, §7A)
9. **Release** (§8)

A stage does not begin until the prior stage has been explicitly approved by the project owner. No stage's findings are fixed automatically — every audit, review, or test run that surfaces a finding stops and waits for explicit direction on which findings to apply before the next stage begins. This is the single most load-bearing rule in this document: it is what makes every subsequent guarantee ("frozen," "production ready," "approved") mean something concrete rather than an unverified claim.

## 2. Design phase requirements

A module's design document (`Build-out/<NN> <Module Name>/Module <NN> Design.md`) must, before it is considered complete enough for review:

- State the module's **Purpose** and **Module Contract** (see §12) in terms of what it receives, produces, and guarantees — the same three questions every existing `MODULE_CONTRACT.md` answers.
- Enumerate every **field, action-log entry type, or data shape** the module introduces or depends on, cross-checked against every upstream module's already-frozen contract for collisions.
- State explicitly which decisions are **architectural** (the design author's to make) versus **business-rule judgment calls** (the project owner's to confirm) — per the precedent set by Module 03's required/optional metadata taxonomy, which was correctly flagged as "a proposal requiring explicit confirmation" rather than silently settled by the design document alone.
- Include a **Test Strategy** section naming, concretely, which regression tests the design *commits to* — not a vague intention, but specific enough that a later audit can check whether the commitment was kept (Module 03's own implementation audit F2 exists because a design-committed test was silently dropped; this requirement exists to make that class of gap independently checkable).
- Include an explicit list of **responsibilities reserved for later modules** — what this module deliberately does *not* do, so a future module's scope can be verified against it rather than assumed.
- Not modify any earlier, already-frozen module's design document or contract. A new module only ever adds a new consumer of already-frozen contracts.

## 3. Architecture review process

Before any implementation begins, the design is reviewed independently — meaning the reviewer explicitly adopts the posture of a senior engineer who did not write the design and has no attachment to its drafting decisions. At minimum, one review round; a second, verification-focused round is required whenever the first round found any Medium-or-higher-severity finding, to confirm each was resolved with the rigor requested rather than merely marked done.

Each review must:
- Classify every finding by severity (Critical / High / Medium / Low / Cosmetic — see §14 for the shared severity scale).
- For every finding, state: what it is, why it matters, its impact, its trade-offs, and the smallest fix that would resolve it.
- Explicitly separate findings that are architectural (the reviewer's to recommend) from findings that are business-rule judgment calls requiring the project owner's own confirmation (the reviewer does not resolve these unilaterally, even if a "smallest fix" is technically available).
- Not modify the design document as a side effect of reviewing it — findings only, until the project owner directs which to apply.
- Independently re-scan the *entire* document for anything new, not just verify the specific findings from a prior round — a second review's job is broader than "did you fix the four things I said," per the standard Module 03's second design review actually held itself to.

A review round concludes with an explicit disposition: either a list of unresolved Critical/High/Medium findings (blocking), or the exact statement that the architecture is frozen and ready for implementation.

## 4. Freeze requirements

A design, an implementation, or a module is "frozen" only when all of the following hold simultaneously (see §15 for the full definition):

- The most recent independent review/audit of it found zero unresolved Critical, High, or Medium findings.
- Every Low/Cosmetic finding from that review is either resolved or explicitly, visibly disposed of (deferred to a named future module, or accepted as a documented trade-off) — never silently dropped.
- The project owner has given explicit approval to treat it as frozen, distinct from merely reviewing the findings.
- No implementation code was changed as a side effect of producing the freeze record itself (a freeze record is documentation of a state, not a vehicle for new changes).

Once frozen, a design document, a module's contract, or a module's implementation is not modified except: (a) a genuine defect is discovered during a later stage (integration testing, UAT, or a future module's own release audit) and the project owner explicitly authorizes a fix, scoped to the smallest possible change; or (b) a new module version is deliberately released per §9's versioning policy. "I thought of a nicer way to do this" is never sufficient justification to reopen a frozen module.

## 4A. Frozen Module Change Policy

See `Governance/FROZEN_MODULE_CHANGE_POLICY.md` for the full policy governing what happens when a defect is discovered in a module after it has already been frozen — severity handling, documentation requirements, version-bump policy, audit/regression requirements, and the specific conditions under which a module may remain frozen versus must be re-released. Referenced here because it is a direct extension of this section's freeze requirements, not a separate framework.

## 5. Implementation standards

- Implement exactly what the frozen design specifies — no redesign, no scope expansion, no feature creep into a later module's reserved responsibilities (§2's "reserved for later modules" list is what an implementation audit checks this against).
- A module's provider-boundary/judgment-dependent components (anything requiring Claude's live understanding of file content) follow the established pattern: a request/response dataclass contract, an abstract provider class, a documented placeholder concrete implementation that raises rather than silently faking judgment, and a fake/test-double implementation for automated testing. This keeps deterministic code testable in isolation from judgment code, per the project's foundational "Claude fits into code" principle (`src/README.md`).
- A module's own Engine/Provider (or equivalently-layered) architecture is not code-shared with a sibling module's identically-shaped architecture unless a specific, disclosed reason exists to couple them — convention-following, not coupling, is the default (this is why Module 03's `MetadataExtractionEngine`/`Provider` are not imported from Module 02's `ClassificationEngine`/`Provider`, despite being structurally near-identical).
- Every fallback path is explicit, named, and auditable (§13). No silent failure, no silent guess, no crash that takes down an entire batch for one file's problem.
- Sanitized, length-bounded diagnostic capture (an `error_detail`-style helper) is built in from the start for every module with a fallback strategy, not retrofitted after an audit catches its absence a second time.

## 6. Testing standards

### 6.1 Unit tests
Every deterministic function and every Engine decision branch is covered by an isolated pytest test using `tmp_path`/`monkeypatch` fixtures — never the project's real `Database/`/`Runtime/` paths. A module's own test file (`test_<module>.py`, colocated with the module per `src/README.md`'s "deliberately not named tests/" convention) is the primary evidence; supporting `core/`/`models/`/`storage/` test files cover shared dependencies. The full suite (all modules combined) is run and must pass at 100% before any stage is reported complete.

### 6.2 Integration tests
A dedicated Integration Test Plan document (`Tests/Module <NN> Integration Test Plan.md`) validates the complete interaction between the new module and every upstream module it depends on, using real files run through the real pipeline functions end-to-end (not just asserted in unit-test isolation). It must cover, at minimum: functional scenarios, cross-module contract validation, data/metadata correctness, required-vs-optional validation (if applicable), privacy/security-relevant behavior, failure/corrupted/locked-file scenarios, mixed-batch scenarios, performance, database and logging validation, and full regression validation. Reuse existing `Samples/`/`Tests/` datasets wherever they already cover a scenario; build new fixtures only where genuinely required. Every case is executed against real code, not merely planned. A failure is a genuine defect only if it reproduces directly against the module's own code, independent of the test harness itself — a bug in the test's own fixture routing or assertion is a test-authoring error, corrected in the harness and explicitly distinguished from a product defect in the plan's own execution-results section.

### 6.3 User Acceptance Testing
A dedicated UAT Plan document (`Tests/Module <NN> UAT Plan.md`) validates the complete real user experience, run exactly as an actual end user would: a realistic external test folder outside the project, the real CLI entry point and production code paths, and — for any judgment-dependent step — live Claude judgment as the actual provider (never a canned/routing fake; that pattern is reserved for integration testing only). Results are archived under `Runtime/UAT/Module<NN>_UAT_<timestamp>/` with, at minimum, the resulting metadata store, action log, terminal output, and a summary document covering every dimension the plan required. Any UAT that validates judgment quality must explicitly caveat the sample size and note if the same person who implemented the module also defined the "correct" expected answers — this is a disclosed limitation of every UAT run so far, not a solved problem, and should not be presented as statistically meaningful judgment-quality validation.

### 6.4 Regression testing policy
See §19.

## 7. Independent audit process

Two distinct audits are required per module, at two distinct points, and neither may be skipped:

- **Implementation audit** (after implementation, before integration testing): reviews the actual code — not the design's description of what the code should do — against the frozen design, all design-review findings, upstream contracts, and the full test suite, re-run fresh. Posture: "assume I did not write this."
- **Release audit** (after UAT, before freeze): a broader, final review of the complete release candidate against every design document, every prior review/audit, every upstream contract, business rules, the data model, and runtime logs. Posture: "assume I did not build this; do not trust any implementation, documentation, or previous review." The release audit has two parts, run together but distinct in kind:
  - **The Pipeline Contract Verification gate (§7A)** — a fixed, mechanical, checklist-driven pass covering contract/compatibility/consistency concerns (FileRecord, module contracts, database, serialization, action log, documentation, dependency graph, versions, rule references, ownership boundaries, breaking changes, performance assumptions, security assumptions). This is **not** a second audit — it is the formalized, non-negotiable subset of the release audit that must be run identically, in the same way, for every module, so its rigor never depends on who's performing it or how much they remember to check.
  - **The qualitative release review** — everything the gate doesn't mechanically check: overall release readiness, architecture drift, UAT evidence quality (sample size, self-grading caveats), completeness of `KNOWN_LIMITATIONS.md`, and forward-compatibility narrative with every module not yet built (does this module's design/data choices make a specific future module's job harder). This part requires judgment, not a checklist, and is where genuinely new findings (like a real, previously-unnoticed data-quality issue) are most likely to be found.

Both audits:
- Classify every finding by severity (§14).
- For every finding, state explanation, impact, trade-offs, and the smallest possible fix — never a recommendation to redesign or expand scope.
- Do not fix anything automatically. Present findings, wait for explicit direction on which to apply.
- After fixes are applied (per direction), re-run the full test suite, re-run the module's own regression tests, verify every upstream module is unaffected, and perform one final, brief re-audit before concluding the stage is complete.
- Investigate, rather than assume, when something looks wrong that isn't part of the module's own code — e.g. unexpected state in the project's real Database/Runtime files is a real finding worth root-causing (as Module 03's release audit did), not something to note and move past.

## 7A. Pipeline Contract Verification gate (mandatory)

`Governance/PIPELINE_CONTRACT_VERIFICATION.md` defines 13 specific checks (FileRecord compatibility, module contract compatibility, database compatibility, serialization compatibility, action log compatibility, documentation consistency, dependency graph consistency, version consistency, rule references, ownership boundaries, breaking changes, performance assumptions, security assumptions) that **every module must pass, or have an explicitly approved exception for, as a mandatory gate within the release audit stage above — not as a separate or additional audit.**

This gate exists so the mechanical, compatibility-focused portion of a release audit is performed identically every time, rather than being reconstructed from memory (and therefore varying in rigor) module by module. A module does not proceed to Release (§8) until this gate passes, or every failing check has a documented, project-owner-approved exception recorded in that module's `RELEASE_AUDIT.md`.

The gate does not replace the qualitative release review described in §7 above — a module's release audit is complete only when *both* the gate has passed (or has approved exceptions) *and* the qualitative review has found no unresolved Critical/High/Medium findings.

## 8. Release process

A module's release package lives at `Release/Module<NN>/` and consists, at minimum, of: `RELEASE_NOTES.md` (features, bugs fixed, breaking changes, improvements), `MODULE_STATUS.md` (version/approval/dependency snapshot), `MODULE_CONTRACT.md` (INPUT/OUTPUT/guarantees/DOES NOT MODIFY — see §12), `TEST_RESULTS.md` (unit/integration/UAT/security/performance summary with verified, re-run counts — never carried forward from memory), `PRODUCTION_CHECKLIST.md` (an explicit PASS/FAIL checklist), `KNOWN_LIMITATIONS.md` (every disclosed gap, with a "deployment model" section up front if an autonomous-vs-interactive distinction applies), and the module's implementation-audit and release-audit records. A release is not begun until the release audit (§7) has concluded with zero unresolved Critical/High/Medium/Low findings, or every remaining Low finding has been explicitly, visibly disposed of with the project owner's direction.

After a release package is generated: `Release/VERSIONS.md` and `Release/DEPENDENCY_DIAGRAM.md` are updated (§9), `CHANGELOG.md` gains dated entries for every stage the module passed through (not a single retroactive summary — the historical granularity matters for future readers), and `src/README.md`'s status section is updated to reflect the new module's completion. A final documentation-consistency pass (no stale version numbers, no stale "not started" claims, no broken cross-references, test counts matching everywhere they're cited) is required before the release is reported complete — this is the same check `Governance/PIPELINE_CONTRACT_VERIFICATION.md` formalizes as a repeatable, checklist-driven process rather than an ad-hoc grep sweep performed differently each time.

## 9. Versioning policy

- **Module Version** — independent semver (`MAJOR.MINOR.PATCH`) per module: `PATCH` for a bug fix within the module's current frozen contract; `MINOR` for an additive change that doesn't break `MODULE_CONTRACT.md`; `MAJOR` for a change to the contract itself (INPUT/OUTPUT/guarantees) that could require downstream modules to adapt.
- **Pipeline Version** — one number for the whole project's overall maturity, bumped deliberately at meaningful milestones, never automatically derived from module versions.
- `Release/VERSIONS.md` is the single cross-module ledger; each module's own `MODULE_STATUS.md` records that module's current version. Both must always agree — verified at every freeze by `PIPELINE_CONTRACT_VERIFICATION.md` check 8 ("Version consistency").
- A module's version is bumped only as part of an explicit release, never silently alongside an unrelated change.

## 10. Documentation standards

- Every module's canonical architecture lives in exactly one place (`Build-out/<NN> <Name>/Module <NN> Design.md` once frozen); a pre-design pointer note, if one predates the real design, is explicitly marked superseded, not deleted, and nothing continues to cite it as current.
- Business rules (classification, naming, folder routing, confidence scoring, ignore patterns, and any future rule category) live in `Rules/*.md` — never duplicated into a `Build-out/` design doc or this governance folder. A design doc may formalize a taxonomy a rules doc will eventually own, but the design review process (§2) must flag this as a pending relocation, not a silent permanent home.
- The canonical data/log schema (`Build-out/08 Logging & Reporting/Metadata & Log Schema.md`) is updated in the same release cycle that introduces a new field or action-log type — never left for a later audit to catch as a gap. (This has already happened twice — Module 02's `classify` action type, Module 03's `extract_metadata` action type — and should not happen a third time; `PIPELINE_CONTRACT_VERIFICATION.md`'s documentation-consistency check exists specifically to catch this before release, not after.)
- `CHANGELOG.md` receives a dated entry for every notable stage of every module's lifecycle, not only a final summary — historical accuracy means a future reader can reconstruct *when* a decision was made and *why*, not just *what* the final state is.
- Every document produced during a review or audit states its own posture explicitly (e.g. "assume I did not build this") and is never silently overwritten by a later pass — a second-round review adds a new section or a new document; it does not rewrite history.

## 11. Module ownership rules

Every module's contract states, explicitly and exhaustively: what it receives, what it produces, which fields it owns and fully populates, and — the section that matters most for preventing silent regressions — every field it must **never** touch, grouped by which later module owns each one. A module's implementation audit and release audit both independently re-verify this "DOES NOT MODIFY" list against the actual code (not just re-cite the contract document), and a permanent regression test (an immutability test asserting every non-owned field is byte-identical before and after the module runs) is required, not optional, for every module from Module 02 onward.

No module reads a field before the module that owns it has actually populated it in the given execution path (e.g. a module must not assume `category` is set on a record Module 01 marked `unreadable`). No module writes into a field owned by a module that hasn't run yet, and no module retroactively "fixes" a value an earlier, already-frozen module produced — a genuine defect in an earlier module is fixed in that module, under its own versioning policy (§9), not worked around downstream.

## 12. Module contract requirements

Every `MODULE_CONTRACT.md` states, at minimum:
- **INPUT** — what it receives from the caller, and what it receives internally (e.g. an injected provider) that isn't part of the caller-facing contract.
- **OUTPUT** — what it produces, including action-log detail that is log-only and never persisted on the core data record.
- **Guarantees** — fields it owns and fully populates, with the exact conditions under which each is populated vs. left at a default.
- **DOES NOT MODIFY** — an exhaustive list of every field it must never touch, attributed to the module that actually owns each one.
- **Provider boundary** (if applicable) — an explicit statement of what is and isn't part of the external contract, and a disclosed deployment-model caveat if no autonomous provider exists yet.
- **Verified by** — the specific test(s) that prove each guarantee, not merely an assertion that testing occurred.

## 13. Fallback and error-handling philosophy

Every failure mode a module can encounter — provider unavailable, provider exception, malformed/corrupted input, an unanticipated internal error — must degrade to a named, auditable state (never a silent guess, never a crash that aborts an entire batch for one file's problem). A sanitized, length-bounded diagnostic (`error_detail` or equivalent) is captured on every fallback path from the module's first implementation, not retrofitted after an audit finds the gap a second time. A single unanticipated failure is caught by an explicit outer safety net at the batch-orchestration layer, distinct from the per-file fallback handling inside the module's own Engine — two layers of defense, not one.

## 14. Severity scale (shared across every review/audit)

- **Critical** — blocks freeze/release unconditionally; typically a correctness, security, or data-loss risk.
- **High** — blocks freeze/release; must be resolved before the next stage begins.
- **Medium** — blocks freeze/release; must be resolved or explicitly, visibly disposed of (not silently dropped) before the next stage begins.
- **Low** — does not block freeze/release by itself, but must be resolved or explicitly recorded (in `KNOWN_LIMITATIONS.md` or the audit document itself) with a stated reason it wasn't fixed and, if applicable, which future module will address it.
- **Cosmetic** — wording/clarity issues with zero behavioral impact; may be fixed on the spot during the same review pass that found it, without a separate approval cycle, given their triviality — the same standard Module 02's and Module 03's own second-round reviews applied.

## 15. Definition of "Frozen"

A module (or a design document, before implementation) is **Frozen** when: the most recent independent review/audit found zero unresolved Critical/High/Medium findings; every Low/Cosmetic finding is resolved or explicitly disposed of; the project owner has given explicit approval to treat it as such; and no further change will be made to it except a genuine, project-owner-authorized defect fix or a deliberate new version release. "Frozen" is a statement about process completeness, not a claim about the code being bug-free forever — it means the module has been through every required stage of this standard and passed.

## 16. Definition of "Production Ready"

"Production Ready" is never used as an unqualified claim (this project's own history contains a real instance of this going wrong — Module 02's release audit F1 — and the correction is now permanent practice). It is always stated as one of two explicit, separately-true claims:

- **Production Ready for interactive, Claude-assisted operation** — every judgment-dependent step is validated end-to-end (unit tests, integration tests, and a real UAT run) for use during a live, agent-driven Claude session, where Claude itself fulfills the module's provider role.
- **Production Ready for autonomous/unattended operation** — a claim that requires an actual autonomous provider implementation to exist. As of this document, no module in this pipeline has one; every module's judgment-dependent behavior requires a live Claude session. Running any module unattended is *safe* (every judgment-dependent field falls back gracefully) but *not functional* for real judgment output. This is disclosed explicitly in every module's `KNOWN_LIMITATIONS.md`, not left implicit.

A module is never described as "production ready" without specifying which of these two claims is being made.

## 17. Breaking change policy

A breaking change is any change to a frozen module's `MODULE_CONTRACT.md` — its declared INPUT, OUTPUT, or guarantees — that could require a downstream module to adapt. Every release's `RELEASE_NOTES.md` states explicitly whether it introduces one, even when the answer is "none." A breaking change, if ever required, triggers a `MAJOR` version bump (§9) for the affected module and requires the project owner's explicit approval before implementation begins, distinct from ordinary feature or bug-fix approval — the same weight given to any other irreversible-feeling decision under this project's non-negotiables.

## 18. Dependency management

New third-party dependencies are named and justified in the module's design document before implementation, not discovered mid-implementation. A dependency introduced ahead of what an upstream module currently supports (e.g. a classification category the ingest layer doesn't yet discover) is an accepted, disclosed forward-compatibility choice, not dead code — but it must be named as such in `KNOWN_LIMITATIONS.md`, and a regression test should guard against the upstream and downstream lists silently diverging further, per the precedent Module 02's own extension-mapping drift test set.

## 19. Regression testing policy

The full unit test suite (every module combined) is re-run after every single change made during any stage of this lifecycle — a review's fix, an audit's fix, a UAT-driven fix — with a 100% pass rate required each time, not merely "mostly passing." Whenever a change is made to one module, the isolated test suites of every other already-frozen module are re-run and confirmed unchanged, as direct, current evidence that the frozen module was not affected — never inferred from "I didn't touch that file." A permanent regression test is added, not merely a manual check performed once, for any drift class an audit discovers (taxonomy drift, extension-mapping drift, contract-immutability violations) — the goal is that the same class of gap cannot recur silently a second time.

## 20. Security review requirements

Every module's release audit explicitly considers: whether any file-content-derived operation could execute code (parsing/reading only, never `eval`, never shelling out, never extracting/decompressing untrusted archive entry contents without a specific, justified reason); whether the module's trust boundary (its Engine or equivalent validation layer) enforces its guarantees unconditionally, independent of whether the upstream provider or input behaves well (verified adversarially — deliberately feeding a malformed or over-permissive value, not only well-behaved test fixtures); and whether any sensitive value (e.g. an account number, a redacted field) can reach a log file, a diagnostic string, or a persisted record in any form the module's own privacy rules prohibit. A structural, provider-independent safeguard for confirmed-sensitive data is preferred over a prompt-instruction-only safeguard whenever a module's design identifies specifically which field(s) carry that risk.

## 21. Performance review requirements

Every module's test results record at least one measured (not estimated) throughput observation against a realistic batch size (`Tests/Large Batch/` or equivalent), explicitly framed as informational at v1 volumes unless a real bottleneck is found. Any known algorithmic cost inherited from an earlier module (e.g. a full read-modify-write per file rather than per batch) is disclosed in `KNOWN_LIMITATIONS.md` as it becomes newly relevant to each additional module that shares it, not only documented once by whichever module first introduced it.

## 22. Relationship to other governance documents

This document defines the overall release lifecycle (§1) and is process only. `Governance/PIPELINE_CONTRACT_VERIFICATION.md` is not a parallel or additional framework — it is the mandatory, checklist-driven gate this document's §7A names as one required part of the release audit stage (stage 8 of §1). Nothing in `PIPELINE_CONTRACT_VERIFICATION.md`'s 13 checks duplicates this document's content; this document says *when* the gate runs and *why* it exists, `PIPELINE_CONTRACT_VERIFICATION.md` says exactly *how* each check is performed.

See `Governance/ARCHITECTURE_DECISIONS.md` for the permanent record of *what* has already been decided architecturally and why; `Governance/PROJECT_ROADMAP.md` for where the pipeline currently stands; `Governance/FROZEN_MODULE_CHANGE_POLICY.md` for what happens if a defect is found in an already-frozen module (§4A); and `Governance/GOVERNANCE_REVIEW.md` for the review history of this governance framework itself.

## 22A. Governance Document Growth Policy

See `Governance/DOCUMENT_GROWTH_POLICY.md` for the full policy governing when a governance document should be split, how cross-references are maintained as documents grow, how superseded content is archived, and how historical decisions remain discoverable. Summary: numbering within any governance document only ever grows (new entries appended, never renumbered or removed); a document is split only once it demonstrably impairs finding a section within a few seconds of scanning, not preemptively; and nothing in `Governance/` is ever silently rewritten — corrections are made in place only for genuine errors (like this framework's own F2 cross-reference fix), while substantive changes in understanding get a new, dated entry instead.
