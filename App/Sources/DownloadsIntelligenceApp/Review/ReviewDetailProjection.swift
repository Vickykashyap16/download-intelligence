import EngineBridge

/// The read-through projection Review Detail and the flagged "why" view
/// both render (`High-Fidelity UI Specification.md` §6): full identity,
/// confidence chip, and the complete ordered breakdown
/// (`ConfidenceDeductionFormatter`) for one specific file, found by
/// `fileID` among the engine's current records.
///
/// A pure function over `[FileRecordSnapshot]`, mirroring
/// `ReviewQueueProjection.compute(records:)`'s own separation — unit-
/// testable without an `EngineBridge`, a live window, or async code.
public struct ReviewDetailProjection: Equatable, Sendable {
    /// Which of the two Review Queue groups this file currently belongs to
    /// — governs which action row the view shows (equal-weight Reject/
    /// Approve for `.needsInput`; Open/Reclassify only, for `.flagged`).
    /// `nil` means the record exists but no longer belongs to either group
    /// (e.g. it was executed, or re-scored to `auto`, between the list's
    /// own last read and this screen's independent fresh read) — a real,
    /// if rare, race the view must show honestly rather than silently
    /// pretend didn't happen.
    public enum Kind: Equatable, Sendable {
        case needsInput
        case flagged
    }

    public let fileID: String
    public let originalName: String
    public let suggestedName: String?
    public let suggestedDestination: String?
    public let category: Category?
    public let confidenceScore: Int?
    public let isDuplicate: Bool
    public let kind: Kind?
    public let breakdown: [ConfidenceDeductionFormatter.DeductionLine]
    /// Populated only for `.flagged` — `nil` for `.needsInput` and for
    /// `nil` kind, matching `ReviewQueueProjection.FlaggedItem`'s own
    /// "Flagged only" scoping for this field.
    public let flagReason: String?

    public init(
        fileID: String,
        originalName: String,
        suggestedName: String?,
        suggestedDestination: String?,
        category: Category?,
        confidenceScore: Int?,
        isDuplicate: Bool,
        kind: Kind?,
        breakdown: [ConfidenceDeductionFormatter.DeductionLine],
        flagReason: String?
    ) {
        self.fileID = fileID
        self.originalName = originalName
        self.suggestedName = suggestedName
        self.suggestedDestination = suggestedDestination
        self.category = category
        self.confidenceScore = confidenceScore
        self.isDuplicate = isDuplicate
        self.kind = kind
        self.breakdown = breakdown
        self.flagReason = flagReason
    }

    /// `nil` when no record with `fileID` exists at all among `records` —
    /// e.g. re-scanned away, or a stale/invalid link — distinct from a
    /// found record whose `kind` is `nil` (see `Kind`'s own documentation).
    public static func compute(records: [FileRecordSnapshot], fileID: String) -> ReviewDetailProjection? {
        guard let record = records.first(where: { $0.fileID == fileID }) else { return nil }

        let kind: Kind?
        if record.tier == .approvalRequired && record.status != "executed" {
            kind = .needsInput
        } else if record.tier == .reviewRequired {
            kind = .flagged
        } else {
            kind = nil
        }

        return ReviewDetailProjection(
            fileID: record.fileID,
            originalName: record.originalName,
            suggestedName: record.suggestedName,
            suggestedDestination: record.suggestedDestination,
            category: record.category,
            confidenceScore: record.confidenceScore,
            isDuplicate: record.duplicateOf != nil,
            kind: kind,
            breakdown: ConfidenceDeductionFormatter.lines(from: record.confidenceBreakdown),
            flagReason: kind == .flagged ? FlagReasonResolver.resolve(for: record) : nil
        )
    }
}
