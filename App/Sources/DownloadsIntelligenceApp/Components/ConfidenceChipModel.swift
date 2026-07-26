import EngineBridge

/// The pure content logic behind `ConfidenceChip` — separated from the
/// SwiftUI view itself so its label/icon/accessibility-text mapping is
/// unit-testable without instantiating any view or live window. Confidence
/// is data the *engine* owns (`Desktop Implementation Blueprint.md` §6),
/// so this model takes the engine's own `Tier` type directly
/// (`EngineBridge.Tier`) rather than re-deriving a parallel GUI-only tier
/// vocabulary, per WP-GUI-00's "no duplicated business logic" rule
/// extended here to the presentation layer.
public struct ConfidenceChipModel: Equatable, Sendable {
    public let tier: Tier
    public let score: Int?

    /// - Parameters:
    ///   - tier: the engine-reported tier. `.other` (an engine tier value
    ///     this GUI version doesn't recognize) renders with the same
    ///     honest, unremarkable "not recognized" treatment used for the
    ///     Unknown *category* color (`06 Visual Design System.md` §3) —
    ///     never a fabricated guess at which of the three known tiers it
    ///     might mean.
    ///   - score: the numeric confidence score, shown only in the
    ///     "With Score" variant. `nil` renders the "Without Score"
    ///     (compact) variant used in Preview/File Row contexts (Figma
    ///     Production Guide §2).
    public init(tier: Tier, score: Int? = nil) {
        self.tier = tier
        self.score = score
    }

    public var label: String {
        switch tier {
        case .auto: return "Auto"
        case .approvalRequired: return "Approval Required"
        case .reviewRequired: return "Review Required"
        case .other: return "Unrecognized"
        }
    }

    /// A settled/complete shape for Auto, a partial/pending shape for
    /// Approval Required, a flag-like shape (deliberately not a warning
    /// triangle) for Review Required — mirroring `05 Design System —
    /// Philosophy Specification.md` §5's tier-icon descriptions, restated
    /// in `06 Visual Design System.md` §5, as concrete SF Symbol names.
    public var iconSystemName: String {
        switch tier {
        case .auto: return "checkmark.circle"
        case .approvalRequired: return "hourglass"
        case .reviewRequired: return "flag"
        case .other: return "questionmark.circle"
        }
    }

    /// No tier is ever communicated by color alone (`06 Visual Design
    /// System.md` §11) — the spoken/accessible form always states the
    /// full tier label and, when present, the numeric score, using the
    /// exact same vocabulary the visible chip uses.
    public var accessibilityLabel: String {
        if let score {
            return "\(label), confidence score \(score)"
        }
        return label
    }
}
