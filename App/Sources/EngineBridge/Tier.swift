import Foundation

/// Mirrors the three confidence tiers defined in `Rules/Confidence Rules.md`
/// and produced by `src/pipeline/confidence.py`: `"auto"` (95-100),
/// `"approval_required"` (80-94), `"review_required"` (below 80, left in
/// place and flagged, no dedicated folder). These exact raw strings are
/// what the real `FileRecord.tier` field and the real action log's
/// `details.tier` value contain today.
///
/// `.other(String)` exists for the same forward-compatibility reason as
/// `Category.other` — a tier scheme change is a `Rules/Confidence
/// Rules.md`-level decision this package has no authority over and no
/// visibility into ahead of time; a record carrying an unrecognized tier
/// value must still decode, not crash the whole read.
public enum Tier: Equatable, Hashable, Sendable {
    case auto
    case approvalRequired
    case reviewRequired
    case other(String)

    public var rawValue: String {
        switch self {
        case .auto: return "auto"
        case .approvalRequired: return "approval_required"
        case .reviewRequired: return "review_required"
        case .other(let value): return value
        }
    }

    public init(rawValue: String) {
        switch rawValue {
        case "auto": self = .auto
        case "approval_required": self = .approvalRequired
        case "review_required": self = .reviewRequired
        default: self = .other(rawValue)
        }
    }
}

extension Tier: Codable {
    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        self.init(rawValue: try container.decode(String.self))
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}
