import EngineBridge

/// Translates a real `FileRecordSnapshot.confidenceBreakdown` — a free-form
/// `[String: JSONValue]` mirroring the engine's own internal deduction keys
/// exactly (`src/pipeline/confidence.py`'s `compute_deductions()`) — into
/// the ordered, plain-language lines Review Detail's breakdown block and a
/// Flagged card's one-line reason both need.
///
/// This translation did not exist anywhere in the GUI before WP-GUI-06:
/// `confidence_breakdown` stores raw keys like `"ambiguous_classification"`
/// or `"missing_required_field:invoice_number"`, never prose — the
/// plain-language wording below is sourced directly from `Rules/Confidence
/// Rules.md`'s own Signal column (for the six fixed deductions) and its
/// worked example's own bracketed commentary style (for the three
/// parameterized ones: "missing required field: invoice_number," "naming
/// fallback used: vendor"), not from `Wireframes — MVP.md` screen 11's
/// illustrative breakdown text ("Vendor name found, but unusual
/// formatting") — that example does not correspond to any real deduction
/// the engine computes and was confirmed to be a mockup placeholder, not
/// literal required copy.
///
/// Ordering is fixed, matching `Rules/Confidence Rules.md`'s own Deductions
/// table row order, exactly the same "never re-shuffle on re-render"
/// determinism guarantee `ScanCompleteProjection.categoryBreakdown` and
/// `PreviewProjection`'s tier sections already establish — Swift
/// dictionaries have no inherent order, so this type imposes one rather
/// than leaving it to iteration order. Within the three parameterized
/// groups (missing required/optional field, naming fallback), entries are
/// sub-ordered alphabetically by field name, since the real engine's own
/// per-category field order is not preserved once collapsed into the
/// stored, unordered dict.
public enum ConfidenceDeductionFormatter {
    public struct DeductionLine: Equatable, Sendable {
        public let text: String
        public let points: Int

        public init(text: String, points: Int) {
            self.text = text
            self.points = points
        }
    }

    /// Builds the full, ordered breakdown from a record's raw
    /// `confidenceBreakdown`. Every key present is rendered — including a
    /// capped entry whose value is exactly `0` (`_apply_capped_field_deductions`'s
    /// own "exactly 0 — never omitted" contract) — since this is meant to
    /// be the complete, auditable "why," not a filtered summary; a
    /// contributed-nothing deduction is still evidence the field was
    /// checked and found missing, once the category's cap had already been
    /// reached by an earlier field.
    public static func lines(from breakdown: [String: JSONValue]) -> [DeductionLine] {
        var ambiguous: DeductionLine?
        var noExtractableText: DeductionLine?
        var missingRequired: [DeductionLine] = []
        var missingOptional: [DeductionLine] = []
        var namingFallback: [DeductionLine] = []
        var fuzzyDuplicate: DeductionLine?
        var versionConflict: DeductionLine?
        var nonEnglishContent: DeductionLine?
        var lockedFile: DeductionLine?
        // Defensive fallback for a future/unrecognized deduction key this
        // package doesn't know about yet — never silently dropped, but
        // rendered using the raw key itself rather than fabricating wording
        // this package has no authority over, mirroring `Tier.other`/
        // `Category.other`'s own forward-compatibility precedent.
        var other: [DeductionLine] = []

        for (key, value) in breakdown {
            let points = Self.points(from: value)
            switch key {
            case "ambiguous_classification":
                ambiguous = DeductionLine(text: "Classification was ambiguous between two plausible categories", points: points)
            case "no_extractable_text":
                noExtractableText = DeductionLine(text: "No extractable text or content — classified from filename only", points: points)
            case "fuzzy_duplicate":
                fuzzyDuplicate = DeductionLine(text: "Near-duplicate or fuzzy image match found", points: points)
            case "version_conflict":
                versionConflict = DeductionLine(text: "Version chain where filename version number and file date disagree", points: points)
            case "non_english_content":
                nonEnglishContent = DeductionLine(text: "Non-English content detected", points: points)
            case "locked_file":
                lockedFile = DeductionLine(text: "Locked or password-protected file", points: points)
            default:
                if let field = Self.field(in: key, prefix: "missing_required_field") {
                    missingRequired.append(DeductionLine(text: "Missing required field: \(field)", points: points))
                } else if let field = Self.field(in: key, prefix: "missing_optional_field") {
                    missingOptional.append(DeductionLine(text: "Missing optional field: \(field)", points: points))
                } else if let field = Self.field(in: key, prefix: "naming_fallback") {
                    namingFallback.append(DeductionLine(text: "Naming fallback used: \(field)", points: points))
                } else {
                    other.append(DeductionLine(text: key, points: points))
                }
            }
        }

        missingRequired.sort { $0.text < $1.text }
        missingOptional.sort { $0.text < $1.text }
        namingFallback.sort { $0.text < $1.text }
        other.sort { $0.text < $1.text }

        var result: [DeductionLine] = []
        if let ambiguous { result.append(ambiguous) }
        if let noExtractableText { result.append(noExtractableText) }
        result.append(contentsOf: missingRequired)
        result.append(contentsOf: missingOptional)
        result.append(contentsOf: namingFallback)
        if let fuzzyDuplicate { result.append(fuzzyDuplicate) }
        if let versionConflict { result.append(versionConflict) }
        if let nonEnglishContent { result.append(nonEnglishContent) }
        if let lockedFile { result.append(lockedFile) }
        result.append(contentsOf: other)
        return result
    }

    private static func points(from value: JSONValue) -> Int {
        Int((value.doubleValue ?? 0).rounded())
    }

    private static func field(in key: String, prefix: String) -> String? {
        let fullPrefix = prefix + ":"
        guard key.hasPrefix(fullPrefix) else { return nil }
        return String(key.dropFirst(fullPrefix.count))
    }
}
