# Module 03 (Metadata Extraction) — Senior Architect Review

Independent review of `Module 03 Design.md`, performed before implementation begins. Reviewed as if by a Principal Engineer with no attachment to prior drafting decisions — no finding below is skipped because "that's just how Module 02 did it." Scope: unnecessary complexity, duplicated responsibilities, separation of concerns, scalability, maintainability, future extensibility, contract consistency, naming consistency, documentation completeness.

No changes have been made to the design as a result of this review — findings only, per instruction.

## Findings

### F1 — Required/optional field split (§7) is a new judgment call with real downstream consequences, not yet confirmed by the project owner
**Severity: Medium-High**

`Rules/Confidence Rules.md`'s deduction table (`−8` per missing required field, `−30` cap; `−2` per missing optional, `−10` cap) has always presupposed a required/optional split existed somewhere — but no document actually defined one until this design's §7 table invented it, category by category, based on inference from `Rules/Naming Rules.md`'s templates ("if a naming template needs it, it's required").

**Why it matters:** this is a real business-rule decision, not an architectural one — whether `invoice_number` is "optional" (as this design proposes) or should actually be required is a judgment about what matters to you, not something derivable purely from the naming template. Getting it wrong doesn't crash anything, but it silently miscalibrates every confidence score computed from it once Module 06 exists, in a way that's hard to notice later (a score of 82 instead of 74 doesn't look wrong on its face).

**Recommended fix:** treat §7's table as a proposal requiring your explicit confirmation, category by category, before it's treated as settled — the same way `Rules/Naming Rules.md` itself is explicitly marked "a draft to react to, not a locked spec."

**Blocks freeze:** Recommend yes, specifically for this table — everything else in the design can freeze around it.

---

### F2 — Bank Statement redaction pattern is specified qualitatively, not precisely enough to implement or test deterministically
**Severity: Medium**

§6 step 7, §12, and §18 describe the safeguard as checking for "a run of 8+ digits" and "common account/routing-number-like patterns" — evocative, but not a specification. An implementer would have to invent the actual regex/logic themselves, which risks a different (looser or stricter) behavior than whatever was actually intended here.

**Why it matters:** this is v1's one concrete, structural privacy control (as opposed to a prompt instruction) — for a control that exists specifically because prompt instructions aren't trusted alone, its own definition should be precise enough to unit-test exactly, not descriptive enough to vary by implementer.

**Recommended fix:** define the exact pattern(s) explicitly in the design (e.g., "any digit sequence of length ≥ 8, ignoring separators, after stripping the `account_last4` field's own value from consideration") before implementation, and add the unit test §20 already calls for as a concrete assertion, not a described intention.

**Blocks freeze:** No — doesn't require re-architecting anything, just tightening one paragraph before it's implemented.

---

### F3 — The redaction safeguard is scoped only to Bank Statement; other categories could plausibly surface the same risk
**Severity: Medium**

Contract and Document (generic) extraction could, in principle, have a provider echo back an account number, SSN-shaped sequence, or similar sensitive digit string embedded in the source text — nothing in the taxonomy (§7) rules this out for those categories, only Bank Statement gets the structural check.

**Why it matters:** the design's own stated reasoning for the redaction control ("a prompt instruction can be wrong, ignored, or bypassed... a structural check at the trust boundary cannot be") applies with equal force to any category whose extracted fields are free text derived from arbitrary document content — the argument doesn't actually depend on the category being Bank Statement specifically.

**Recommended fix:** either (a) generalize the digit-pattern check to run over every extracted string field regardless of category, or (b) keep it Bank-Statement-only but state explicitly, as an accepted and disclosed limitation, that other categories rely on prompt-level instruction alone for this specific risk. Either is defensible — leaving it unstated is not.

**Blocks freeze:** No.

---

### F4 — Video's naming `{Date}` defaults to filesystem `modified_at`, which may not reflect actual content creation date
**Severity: Medium**

§7's Video row and §16's dependency discussion both note that video-tag/duration extraction is deferred (no library dependency approved), so the naming template's date slot is proposed to fall back to `FileRecord.modified_at` — a download/filesystem timestamp, not the video's actual recording date. For a phone-recorded video downloaded or transferred well after it was shot, these can differ by days, months, or more.

**Why it matters:** this is presented almost as an aside inside a table cell rather than as a named, disclosed limitation — a future reader (or user) filing videos by date could be misled about what that date actually represents, with no flag anywhere telling them so.

**Recommended fix:** no design change needed — just promote this from an implicit table note to an explicit, named limitation (in `KNOWN_LIMITATIONS.md` once Module 03 ships, and ideally cross-referenced from §7/§19 now) so it's discoverable the way Module 02's own known limitations are.

**Blocks freeze:** No.

---

### F5 — `extract_batch()` doesn't mirror the `extract_metadata` action-log name as tightly as `classify_batch()` mirrors `classify`
**Severity: Low / Cosmetic**

`classify_batch()` ↔ `"classify"` is an exact verb match. `extract_batch()` ↔ `"extract_metadata"` is not — a minor asymmetry in an otherwise carefully-mirrored naming convention.

**Recommended fix:** rename to `extract_metadata_batch()` for exact parity, or explicitly note the shorter name is a deliberate brevity choice if that's preferred. Either is fine; leaving it unexamined is the only wrong answer.

**Blocks freeze:** No.

---

### F6 — §25's state-transition diagram implies an all-`null` result "never actually persisted this bare," which contradicts §12's own fallback behavior
**Severity: Low / Cosmetic**

The middle state in the diagram (`{key: null, key: null, ...}`) is labeled "a transient in-Engine state, never actually persisted this bare" — but §12 explicitly allows a total-fallback record (provider unavailable/exception on every field) to persist in exactly that shape. The diagram's caption overstates how distinct the transient and final states are.

**Recommended fix:** reword the caption to something like "usually further populated before persistence, but a full-fallback record can legitimately persist in this exact shape — see §12."

**Blocks freeze:** No.

---

### F7 — Test strategy doesn't explicitly name a test for Video's deferred `duration` field
**Severity: Low / Cosmetic**

§20 is otherwise thorough (taxonomy-drift test, redaction test, contract test all explicitly named) but doesn't call out a test confirming Video's `duration` stays `null` without raising, now that §16 has deferred the library that would populate it.

**Recommended fix:** add one line to §20 naming this test explicitly, so "Video duration is null" is asserted by design rather than merely true by omission.

**Blocks freeze:** No.

---

### F8 — The full three-layer Engine/Provider/ABC split is only exercised by roughly seven of twelve categories
**Severity: Low (complexity observation, not a defect)**

Archive and Application are fully deterministic in v1 (§9); Video is mostly deterministic. For these categories, `MetadataExtractionProvider` is scaffolding that's never actually called. This mirrors a risk Module 02's own design (§22, risk 1) already named for itself ("adds structure for exactly one working provider") — here the ratio is arguably less favorable (a smaller fraction of categories actually need the provider at all).

**Why it matters:** not a correctness issue — but worth naming explicitly rather than silently inheriting Module 02's structure because it's the established pattern. The design does partially address this already (§9's table, §27's note on not building a shared cross-module provider base) but doesn't explicitly weigh "is a full ABC justified here" the way Module 02's own Alternative Architectures section (§23-D) weighed it for classification.

**Recommended fix:** none required — recommend explicitly accepting this trade-off (consistency and future extensibility for AI-driven categories outweigh the cost of an unused interface for deterministic ones) as a stated decision rather than an inherited assumption, e.g. a short addition to §27 or §22 of the design.

**Blocks freeze:** No.

## Verification of documentation completeness

All 27 requested sections are present and populated (Purpose through Future Extensibility), plus an explicit Ownership & Boundaries summary (§28) covering what Module 03 owns, must never do, what becomes immutable after it runs, and what later modules are expected to consume — nothing from the original request is missing structurally.

Cross-checked against frozen artifacts: no field, action type, or exception name proposed here collides with anything in `Release/Module01/` or `Release/Module02/`; `FileRecord.extracted_metadata` is confirmed to already exist and require no schema change (§14/§15); the one recommended documentation move (`Rules/Metadata Rules.md`, §10) and the one new dependency (`mutagen`, §16) are both explicitly marked pending approval, not applied — consistent with "do not begin implementation."

## Disposition

Zero Critical, zero High findings. One Medium-High finding (F1) that should be resolved — by your explicit input, not a design change — before this is treated as frozen, since it's a business-rule judgment call the design author (me) shouldn't be finalizing unilaterally. Three further Medium findings (F2–F4) are cheap, contained clarifications. Four Low/Cosmetic findings (F5–F8) are optional polish.

Recommend: confirm or correct §7's required/optional assignments (F1), then apply F2–F8 as small, non-architectural edits to the same document. No architecture change is implied by any finding above — the three-layer shape, the Module Contract, and the taxonomy structure all hold.

Awaiting your direction on which findings to apply before any changes are made to `Module 03 Design.md`.
