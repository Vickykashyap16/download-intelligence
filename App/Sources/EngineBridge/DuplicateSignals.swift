import Foundation

/// Mirrors `src/models/duplicate.py`'s `DuplicateSignals` dataclass
/// exactly, field for field, including its real Python defaults.
public struct DuplicateSignals: Equatable, Sendable {
    public let exactDuplicate: Bool
    public let fuzzyDuplicate: Bool
    public let phashDistance: Int?
    public let versionConflict: Bool

    public init(
        exactDuplicate: Bool = false,
        fuzzyDuplicate: Bool = false,
        phashDistance: Int? = nil,
        versionConflict: Bool = false
    ) {
        self.exactDuplicate = exactDuplicate
        self.fuzzyDuplicate = fuzzyDuplicate
        self.phashDistance = phashDistance
        self.versionConflict = versionConflict
    }
}

extension DuplicateSignals: Codable {
    private enum CodingKeys: String, CodingKey {
        case exactDuplicate = "exact_duplicate"
        case fuzzyDuplicate = "fuzzy_duplicate"
        case phashDistance = "phash_distance"
        case versionConflict = "version_conflict"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            exactDuplicate: try container.decodeIfPresent(Bool.self, forKey: .exactDuplicate) ?? false,
            fuzzyDuplicate: try container.decodeIfPresent(Bool.self, forKey: .fuzzyDuplicate) ?? false,
            phashDistance: try container.decodeIfPresent(Int.self, forKey: .phashDistance),
            versionConflict: try container.decodeIfPresent(Bool.self, forKey: .versionConflict) ?? false
        )
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(exactDuplicate, forKey: .exactDuplicate)
        try container.encode(fuzzyDuplicate, forKey: .fuzzyDuplicate)
        try container.encodeIfPresent(phashDistance, forKey: .phashDistance)
        try container.encode(versionConflict, forKey: .versionConflict)
    }
}
