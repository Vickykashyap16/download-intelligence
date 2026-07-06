# Frozen Module Change Policy

Referenced by `Governance/ENGINEERING_STANDARD.md` §4A. This policy governs what happens when a defect, gap, or inconsistency is discovered in a module *after* it has already been declared Frozen (`ENGINEERING_STANDARD.md` §15) — a realistic, expected occurrence as later modules begin depending on earlier ones under real conditions, not a failure of the freeze process itself. Generic by design: applies to every current and future module (01 through 08), not named to any one of them.

## 1. What happens when a post-freeze defect is discovered

1. **Do not fix anything automatically.** The same standing rule as every other stage of `ENGINEERING_STANDARD.md` applies here without exception: a suspected defect in a frozen module is reported — severity, root cause, impact, smallest possible fix — and the project owner is asked to approve before any change is made, exactly as if it were a fresh finding from an implementation or release audit.
2. **Investigate before concluding it's a defect.** Confirm the issue reproduces directly against the frozen module's own code and frozen contract, independent of whatever later module or test surfaced it — a defect in the *new* module's own assumptions about the frozen one is not a reason to reopen the frozen module (see `ENGINEERING_STANDARD.md` §2's "Module contract compatibility" discipline: the new module's assumptions must trace to an explicit contract guarantee; if they don't, the new module's assumption is the problem, not the frozen module).
3. **Classify severity** using the shared scale (`ENGINEERING_STANDARD.md` §14) before deciding anything about scope or process — severity is what determines the rest of this policy's requirements.

## 2. Severity levels and what each requires

- **Critical/High** — the frozen module produces an actively wrong, unsafe, or data-damaging result under real conditions (e.g. silent data loss, a privacy control that doesn't actually hold). Blocks any later module that depends on the affected behavior from being released until fixed. Requires the full re-release path (§5 below).
- **Medium** — a real defect with contained, non-catastrophic impact (e.g. an edge case producing an incorrect but recoverable value, a documented guarantee that doesn't quite hold in a specific circumstance). Requires the full re-release path (§5 below), but the fix and its verification may be scoped narrowly to the affected behavior rather than repeating the module's entire original test/audit surface.
- **Low** — a real but minor gap (e.g. a slightly-too-narrow validation, a rarely-hit fallback path with a less-than-ideal but not incorrect result). May remain frozen without a fix (§4 below) if explicitly disclosed and deferred, or may be fixed via the lightweight patch path (§5) at the project owner's discretion.
- **Cosmetic** — documentation/wording issues discovered in the frozen module's own release record (not its code). Fixed directly in the affected document, in place, without triggering any version bump or re-audit — the same standard `ENGINEERING_STANDARD.md` §14 already applies to Cosmetic findings during an original audit.

## 3. Documentation requirements

- A post-freeze fix is never a silent edit to the module's existing release record. It is a **dated addendum**: a new, clearly-timestamped section appended to that module's `RELEASE_NOTES.md` (and `TEST_RESULTS.md`/`KNOWN_LIMITATIONS.md` if affected), following the same "never rewrite history" principle `CHANGELOG.md` already applies — the original release record stays intact as a historical account of what was true at first freeze; the addendum records what changed, when, and why.
- `CHANGELOG.md` gains a new dated entry for the fix, exactly as it would for original release work — post-freeze fixes are not exempt from the project's documentation standards (`ENGINEERING_STANDARD.md` §10) just because the module was already released once.
- The discovering module's own release audit (whichever later module's work surfaced the issue) references the fix and the frozen module's new patch version, so the dependency is traceable from either direction.

## 4. When a module can remain frozen (no fix applied)

A module may remain frozen, unmodified, with the defect left in place, only when **all** of the following hold:
- The finding is Low or Cosmetic severity.
- The gap is explicitly recorded in that module's `KNOWN_LIMITATIONS.md` (not silently left undiscovered/undocumented) with the same rigor as an original release's disclosed limitations.
- The project owner explicitly confirms, at the time the finding is presented, that no fix is needed right now.
- No currently-planned future module's own design depends on the specific behavior the gap affects in a way that would silently produce a wrong result (if it does, the finding's severity should be reconsidered upward, not left at Low).

## 5. When a module must be re-released (fix applied)

Any Critical, High, or Medium finding — and any Low finding the project owner elects to fix rather than defer — triggers a re-release of the affected module:

1. **Version bump** (`ENGINEERING_STANDARD.md` §9): `PATCH` if the fix stays entirely within the module's existing, frozen `MODULE_CONTRACT.md`; `MINOR` if it adds new optional behavior without breaking the existing contract; `MAJOR` if the fix genuinely cannot be made without changing the contract's declared INPUT/OUTPUT/guarantees — which is itself a breaking change requiring the full breaking-change approval process (`ENGINEERING_STANDARD.md` §17), not just this policy's lighter patch path.
2. **Audit requirement:** a targeted re-audit, scoped to the fix itself and anything it touches — not a full repeat of the module's original implementation and release audits. At minimum: confirm the fix resolves the specific finding, confirm it doesn't introduce a new contract violation (re-run the module's own immutability/ownership-boundary test), and confirm every module downstream of the fixed one is unaffected (their isolated test suites still pass at their pre-existing counts).
3. **Regression requirement:** the full project-wide unit test suite is re-run and must pass at 100%; a new, permanent regression test is added for the specific defect (so the same class of gap cannot recur silently), following the same discipline as `ENGINEERING_STANDARD.md` §19.
4. **Version ledger update:** `Release/VERSIONS.md` reflects the module's new version number and a new History entry describing the patch/minor/major release and why it happened.
5. **Pipeline Contract Verification gate re-run** (`ENGINEERING_STANDARD.md` §7A): re-run the 13-check gate for the fixed module, since a change to a frozen module is exactly the kind of event the gate exists to catch drift from.

A module that has been re-released under this policy is Frozen again once these five requirements are satisfied and the project owner gives explicit approval — the same freeze definition (`ENGINEERING_STANDARD.md` §15) applies to a patched module as to an original release.
