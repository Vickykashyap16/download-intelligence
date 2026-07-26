import Foundation

/// Mirrors `src/models/classification.py`'s `ClassificationSignals`
/// dataclass exactly, field for field, including its real Python defaults
/// — used when a key is absent from a decoded record rather than treating
/// absence as a decode failure, since a defensively-tolerant reader should
/// survive a record written by a slightly older or newer version of the
/// same dataclass shape (an additive field, in particular) without losing
/// the rest of that record.
public struct ClassificationSignals: Equatable, Sendable {
    public let ambiguous: Bool
    public let multiDocumentDetected: Bool
    public let noExtractableText: Bool
    public let nonEnglishDetected: Bool
    public let detectedLanguage: String?
    public let locked: Bool

    public init(
        ambiguous: Bool = false,
        multiDocumentDetected: Bool = false,
        noExtractableText: Bool = false,
        nonEnglishDetected: Bool = false,
        detectedLanguage: String? = nil,
        locked: Bool = false
    ) {
        self.ambiguous = ambiguous
        self.multiDocumentDetected = multiDocumentDetected
        self.noExtractableText = noExtractableText
        self.nonEnglishDetected = nonEnglishDetected
        self.detectedLanguage = detectedLanguage
        self.locked = locked
    }
}

extension ClassificationSignals: Codable {
    private enum CodingKeys: String, CodingKey {
        case ambiguous
        case multiDocumentDetected = "multi_document_detected"
        case noExtractableText = "no_extractable_text"
        case nonEnglishDetected = "non_english_detected"
        case detectedLanguage = "detected_language"
        case locked
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            ambiguous: try container.decodeIfPresent(Bool.self, forKey: .ambiguous) ?? false,
            multiDocumentDetected: try container.decodeIfPresent(Bool.self, forKey: .multiDocumentDetected) ?? false,
            noExtractableText: try container.decodeIfPresent(Bool.self, forKey: .noExtractableText) ?? false,
            nonEnglishDetected: try container.decodeIfPresent(Bool.self, forKey: .nonEnglishDetected) ?? false,
            detectedLanguage: try container.decodeIfPresent(String.self, forKey: .detectedLanguage),
            locked: try container.decodeIfPresent(Bool.self, forKey: .locked) ?? false
        )
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(ambiguous, forKey: .ambiguous)
        try container.encode(multiDocumentDetected, forKey: .multiDocumentDetected)
        try container.encode(noExtractableText, forKey: .noExtractableText)
        try container.encode(nonEnglishDetected, forKey: .nonEnglishDetected)
        try container.encodeIfPresent(detectedLanguage, forKey: .detectedLanguage)
        try container.encode(locked, forKey: .locked)
    }
}
