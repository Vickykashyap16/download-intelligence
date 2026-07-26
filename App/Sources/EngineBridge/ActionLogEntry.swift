import Foundation

/// Mirrors one line of `Runtime/Logs/action_log.jsonl` exactly, as written
/// by `src/storage/runtime_io.py`'s `append_action_log()`:
/// `{"batch_id", "file_id", "action", "from", "to", "timestamp",
/// "approved_by", "details"}`, with `details` optional and open-ended.
///
/// `action` and `approvedBy` are modeled as plain `String`s rather than
/// closed enums. The real `action` vocabulary is explicitly documented as
/// open-ended and "grown module by module" (`move_rename`,
/// `archive_duplicate`, `archive_superseded_version`, `skip`, `error`,
/// `undo`, `discover`, `classify`, `extract_metadata`,
/// `detect_duplicates_and_versions`, `suggest_naming_and_destination`,
/// `score_confidence`, `reject`, as of this writing, with more added as the
/// pipeline grows) — a closed Swift enum here would itself be exactly the
/// "assumption about a future format" WP-GUI-00 rules out: a new action
/// type introduced by a future engine module must decode today without a
/// corresponding Swift change.
public struct ActionLogEntry: Equatable, Sendable {
    public let batchID: String
    public let fileID: String
    public let action: String
    public let from: String?
    public let to: String?
    public let timestamp: String
    public let approvedBy: String
    public let details: JSONValue?

    public init(
        batchID: String,
        fileID: String,
        action: String,
        from: String?,
        to: String?,
        timestamp: String,
        approvedBy: String,
        details: JSONValue?
    ) {
        self.batchID = batchID
        self.fileID = fileID
        self.action = action
        self.from = from
        self.to = to
        self.timestamp = timestamp
        self.approvedBy = approvedBy
        self.details = details
    }

    /// `timestamp` parsed as a `Date`, using ISO 8601. Returns `nil` rather
    /// than throwing if the stored string doesn't parse — a display layer
    /// can fall back to showing the raw string rather than the whole entry
    /// becoming unusable over a timestamp formatting quirk.
    public var timestampDate: Date? {
        ISO8601DateFormatter().date(from: timestamp)
    }
}

extension ActionLogEntry: Codable {
    private enum CodingKeys: String, CodingKey {
        case batchID = "batch_id"
        case fileID = "file_id"
        case action
        case from
        case to
        case timestamp
        case approvedBy = "approved_by"
        case details
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            batchID: try container.decode(String.self, forKey: .batchID),
            fileID: try container.decode(String.self, forKey: .fileID),
            action: try container.decode(String.self, forKey: .action),
            from: try container.decodeIfPresent(String.self, forKey: .from),
            to: try container.decodeIfPresent(String.self, forKey: .to),
            timestamp: try container.decode(String.self, forKey: .timestamp),
            approvedBy: try container.decode(String.self, forKey: .approvedBy),
            details: try container.decodeIfPresent(JSONValue.self, forKey: .details)
        )
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(batchID, forKey: .batchID)
        try container.encode(fileID, forKey: .fileID)
        try container.encode(action, forKey: .action)
        try container.encodeIfPresent(from, forKey: .from)
        try container.encodeIfPresent(to, forKey: .to)
        try container.encode(timestamp, forKey: .timestamp)
        try container.encode(approvedBy, forKey: .approvedBy)
        try container.encodeIfPresent(details, forKey: .details)
    }
}
