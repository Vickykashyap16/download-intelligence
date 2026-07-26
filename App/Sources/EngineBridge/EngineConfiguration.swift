import Foundation

/// Mirrors one entry of `src/config/sources.yaml`'s `sources:` list exactly,
/// as observed in the real, current file: `source_id`, `path`, `type`,
/// `enabled`, `recursive`.
public struct EngineSource: Equatable, Sendable {
    public let sourceID: String
    public let path: String

    /// The real, current value is `"local_folder"`. Modeled as a plain
    /// `String`, not a closed enum, since a future source type (e.g. a
    /// cloud-backed folder) is a plausible, unadjudicated future
    /// possibility this package has no authority to anticipate or
    /// foreclose — matching the same forward-compatibility reasoning as
    /// `Category.other`/`Tier.other` elsewhere in this package.
    public let type: String

    /// Defaults to `true` when absent: a source entry a user bothered to
    /// list is reasonably assumed active unless the file says otherwise.
    public let enabled: Bool

    /// Defaults to `false` when absent, matching this project's own
    /// established v1 scope decision that recursive scanning is not
    /// supported — not an arbitrary guess, but the real, already-recorded
    /// default for this exact field.
    public let recursive: Bool

    public init(sourceID: String, path: String, type: String, enabled: Bool = true, recursive: Bool = false) {
        self.sourceID = sourceID
        self.path = path
        self.type = type
        self.enabled = enabled
        self.recursive = recursive
    }
}

extension EngineSource: Codable {
    private enum CodingKeys: String, CodingKey {
        case sourceID = "source_id"
        case path
        case type
        case enabled
        case recursive
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            sourceID: try container.decode(String.self, forKey: .sourceID),
            path: try container.decode(String.self, forKey: .path),
            type: try container.decode(String.self, forKey: .type),
            enabled: try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? true,
            recursive: try container.decodeIfPresent(Bool.self, forKey: .recursive) ?? false
        )
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(sourceID, forKey: .sourceID)
        try container.encode(path, forKey: .path)
        try container.encode(type, forKey: .type)
        try container.encode(enabled, forKey: .enabled)
        try container.encode(recursive, forKey: .recursive)
    }
}

/// Mirrors `src/config/sources.yaml` exactly, as it exists today: a
/// `sources:` list, `execution_mode`, `destination_root`,
/// `classification_provider`, `extraction_provider`, and
/// `ai_provider_consent`.
public struct EngineConfiguration: Equatable, Sendable {
    public let sources: [EngineSource]

    /// The real, current value is `"manual"`. No default is invented here
    /// for an absent key — unlike `EngineSource.recursive`, this package
    /// has no independently-confirmed "this is the documented real
    /// default" fact to fall back on for execution mode, so absence is
    /// represented honestly as `nil` rather than guessed.
    public let executionMode: String?

    public let destinationRoot: String?
    public let classificationProvider: String?
    public let extractionProvider: String?

    /// Defaults to `false` when absent. This default is not a guess: it is
    /// the direct, load-bearing expression of `GUI Architecture
    /// Specification.md` §16's AI-disclosure principle that the absence of
    /// explicit, disclosed consent must never be treated as consent.
    public let aiProviderConsent: Bool

    public init(
        sources: [EngineSource] = [],
        executionMode: String? = nil,
        destinationRoot: String? = nil,
        classificationProvider: String? = nil,
        extractionProvider: String? = nil,
        aiProviderConsent: Bool = false
    ) {
        self.sources = sources
        self.executionMode = executionMode
        self.destinationRoot = destinationRoot
        self.classificationProvider = classificationProvider
        self.extractionProvider = extractionProvider
        self.aiProviderConsent = aiProviderConsent
    }
}

extension EngineConfiguration: Codable {
    private enum CodingKeys: String, CodingKey {
        case sources
        case executionMode = "execution_mode"
        case destinationRoot = "destination_root"
        case classificationProvider = "classification_provider"
        case extractionProvider = "extraction_provider"
        case aiProviderConsent = "ai_provider_consent"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            sources: try container.decodeIfPresent([EngineSource].self, forKey: .sources) ?? [],
            executionMode: try container.decodeIfPresent(String.self, forKey: .executionMode),
            destinationRoot: try container.decodeIfPresent(String.self, forKey: .destinationRoot),
            classificationProvider: try container.decodeIfPresent(String.self, forKey: .classificationProvider),
            extractionProvider: try container.decodeIfPresent(String.self, forKey: .extractionProvider),
            aiProviderConsent: try container.decodeIfPresent(Bool.self, forKey: .aiProviderConsent) ?? false
        )
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(sources, forKey: .sources)
        try container.encodeIfPresent(executionMode, forKey: .executionMode)
        try container.encodeIfPresent(destinationRoot, forKey: .destinationRoot)
        try container.encodeIfPresent(classificationProvider, forKey: .classificationProvider)
        try container.encodeIfPresent(extractionProvider, forKey: .extractionProvider)
        try container.encode(aiProviderConsent, forKey: .aiProviderConsent)
    }
}
