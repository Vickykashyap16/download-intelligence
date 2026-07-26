import Foundation

/// A type-erased, `Codable`, `Equatable`, `Sendable` representation of an
/// arbitrary JSON value. Exists because several real, frozen artifact
/// shapes are deliberately open-ended and are not something this package
/// should force into a fixed Swift type:
///
/// * `FileRecord.extracted_metadata` (`src/models/file_record.py`) — a
///   free-form `dict` whose keys vary per file category (an invoice's
///   extracted fields look nothing like a resume's).
/// * `FileRecord.confidence_breakdown` (same file) — a free-form `dict`
///   recording whatever `Rules/Confidence Rules.md` scoring inputs applied.
/// * The action log's `details` field
///   (`src/storage/runtime_io.py`'s `append_action_log()`) — explicitly
///   documented as an arbitrary-shaped dict that differs per `action`
///   value.
///
/// Modeling any of these as a fixed Swift struct would be exactly the kind
/// of "assumption about future formats" WP-GUI-00 rules out — a new field
/// added to a future classification provider's output, or a new action
/// type's details shape, must decode successfully today, not require a
/// Swift-side schema change to avoid a crash. `JSONValue` decodes anything
/// valid JSON can express and lets a caller inspect it by shape by
/// switching on it or reaching into `.object`/`.array` by key/index.
public indirect enum JSONValue: Equatable, Sendable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])
}

extension JSONValue: Decodable {
    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unrecognized JSON value shape"
            )
        }
    }
}

extension JSONValue: Encodable {
    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null:
            try container.encodeNil()
        case .bool(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .string(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        }
    }
}

extension JSONValue {
    /// Convenience accessor for the common case of treating this value as a
    /// JSON object and reaching in by key. Returns `nil` for any other
    /// shape or a missing key, rather than throwing — callers inspecting an
    /// intentionally free-form value are expected to handle absence, not
    /// treat it as exceptional.
    public subscript(key: String) -> JSONValue? {
        guard case .object(let dictionary) = self else { return nil }
        return dictionary[key]
    }

    public var stringValue: String? {
        guard case .string(let value) = self else { return nil }
        return value
    }

    public var doubleValue: Double? {
        guard case .number(let value) = self else { return nil }
        return value
    }

    public var boolValue: Bool? {
        guard case .bool(let value) = self else { return nil }
        return value
    }
}
