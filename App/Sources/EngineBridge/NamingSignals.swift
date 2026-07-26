import Foundation

/// Mirrors `src/models/naming.py`'s `NamingSignals` dataclass exactly.
public struct NamingSignals: Equatable, Sendable {
    public let fieldsFellBack: [String]

    public init(fieldsFellBack: [String] = []) {
        self.fieldsFellBack = fieldsFellBack
    }
}

extension NamingSignals: Codable {
    private enum CodingKeys: String, CodingKey {
        case fieldsFellBack = "fields_fell_back"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            fieldsFellBack: try container.decodeIfPresent([String].self, forKey: .fieldsFellBack) ?? []
        )
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(fieldsFellBack, forKey: .fieldsFellBack)
    }
}
