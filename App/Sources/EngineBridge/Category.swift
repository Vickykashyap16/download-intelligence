import Foundation

/// Mirrors `src/models/classification.py`'s `Category(str, Enum)` exactly —
/// the twelve real category values the engine assigns today, by their
/// exact, real string values (not Swift-cased identifiers): `"Invoice"`,
/// `"Resume"`, `"Bank Statement"`, `"Contract"`, `"Document"`, `"Image"`,
/// `"Screenshot"`, `"Application"`, `"Archive"`, `"Video"`, `"Audio"`,
/// `"Unknown"`.
///
/// `.other(String)` exists for exactly one reason: WP-GUI-00 requires
/// reading artifacts "exactly as they exist today" with "no assumptions
/// about future formats." If a future engine module ever adds a
/// thirteenth category, a metadata store record carrying it must still
/// decode successfully — falling back to `.other(rawValue)` rather than
/// failing the entire record (or the entire batch read) over one
/// unrecognized string. This is the same "fail gracefully, never invent,
/// never lose the real evidence" principle `GUI Architecture
/// Specification.md` §12 and §15 apply to error propagation and logging,
/// applied here to schema evolution instead.
public enum Category: Equatable, Hashable, Sendable {
    case invoice
    case resume
    case bankStatement
    case contract
    case document
    case image
    case screenshot
    case application
    case archive
    case video
    case audio
    case unknown
    case other(String)

    /// The exact real string value this case round-trips to/from, matching
    /// `src/models/classification.py`'s `Category(str, Enum)` member
    /// values verbatim.
    public var rawValue: String {
        switch self {
        case .invoice: return "Invoice"
        case .resume: return "Resume"
        case .bankStatement: return "Bank Statement"
        case .contract: return "Contract"
        case .document: return "Document"
        case .image: return "Image"
        case .screenshot: return "Screenshot"
        case .application: return "Application"
        case .archive: return "Archive"
        case .video: return "Video"
        case .audio: return "Audio"
        case .unknown: return "Unknown"
        case .other(let value): return value
        }
    }

    public init(rawValue: String) {
        switch rawValue {
        case "Invoice": self = .invoice
        case "Resume": self = .resume
        case "Bank Statement": self = .bankStatement
        case "Contract": self = .contract
        case "Document": self = .document
        case "Image": self = .image
        case "Screenshot": self = .screenshot
        case "Application": self = .application
        case "Archive": self = .archive
        case "Video": self = .video
        case "Audio": self = .audio
        case "Unknown": self = .unknown
        default: self = .other(rawValue)
        }
    }
}

extension Category: Codable {
    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        self.init(rawValue: try container.decode(String.self))
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}
