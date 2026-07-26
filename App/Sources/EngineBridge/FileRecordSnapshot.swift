import Foundation

/// A read-only Swift mirror of one real `FileRecord` (`src/models/file_record.py`),
/// as it exists today in `Database/Metadata/metadata_store.json`. Field
/// names, optionality, and defaults all mirror the real Python dataclass
/// exactly — this type is never constructed by the GUI to be written back;
/// per `GUI Architecture Specification.md` §1 and §7, the engine is the
/// sole owner and writer of this state, and the GUI only ever reads a
/// projection of it.
///
/// Two independent value categories exist among these fields:
///
/// 1. **Identity fields**, present on every real record regardless of how
///    far through the pipeline it has progressed (`fileID`, `sourceID`,
///    `originalName`, `originalPath`, `currentPath`, `fileExtension`,
///    `mimeType`, `sizeBytes`, `createdAt`, `modifiedAt`, `contentHash`,
///    `discoveredAt`). A record missing one of these is not a record this
///    package can meaningfully represent at all — `MetadataStoreReader`
///    treats a decode failure at this level as one unparseable record to
///    skip and report, not a reason to fail the entire read.
/// 2. **Pipeline-stage fields**, populated only once the corresponding
///    module has actually processed the file (`category`,
///    `classificationSignals`, `suggestedName`, `namingSignals`,
///    `duplicateOf`, `confidenceScore`, `tier`, `batchID`, `approvedBy`,
///    etc.) — all modeled as `Optional`, exactly mirroring the real
///    dataclass's `Optional[...] = None` fields, because a freshly
///    discovered file legitimately has none of these yet.
public struct FileRecordSnapshot: Equatable, Sendable {
    // MARK: Identity fields (always present on a well-formed record)

    public let fileID: String
    public let sourceID: String
    public let originalName: String
    public let originalPath: String
    public let currentPath: String
    public let fileExtension: String
    public let mimeType: String
    public let sizeBytes: Int64
    public let createdAt: String
    public let modifiedAt: String
    public let contentHash: String
    public let discoveredAt: String

    // MARK: Lifecycle

    /// Open-ended, grown module by module in the real pipeline (e.g.
    /// `"discovered"`, `"classified"`, `"extracted"`, `"error"`) — modeled
    /// as a plain `String` rather than a closed enum for the same
    /// forward-compatibility reason as `Category.other` and `Tier.other`,
    /// since this package has no authoritative list of every value the
    /// engine may ever assign here.
    public let status: String
    public let error: String?

    // MARK: Classification (Module 02)

    public let category: Category?
    public let classificationSignals: ClassificationSignals?

    // MARK: Metadata extraction (Module 03)

    public let extractedMetadata: [String: JSONValue]

    // MARK: Naming & destination (Module 05)

    public let suggestedName: String?
    public let suggestedDestination: String?
    public let namingSignals: NamingSignals?

    // MARK: Duplicate & version detection (Module 04)

    public let duplicateOf: String?
    public let versionGroupID: String?
    public let versionRank: VersionRank?
    public let duplicateSignals: DuplicateSignals?

    // MARK: Confidence scoring (Module 06)

    public let confidenceScore: Int?
    public let confidenceBreakdown: [String: JSONValue]
    public let tier: Tier?

    // MARK: Execution (Module 07)

    public let batchID: String?
    public let processedAt: String?
    public let approvedBy: ApprovedBy?
    public let approvedAt: String?
    public let reversible: Bool

    public enum VersionRank: Equatable, Sendable {
        case latest
        case superseded
        case other(String)

        public var rawValue: String {
            switch self {
            case .latest: return "latest"
            case .superseded: return "superseded"
            case .other(let value): return value
            }
        }

        public init(rawValue: String) {
            switch rawValue {
            case "latest": self = .latest
            case "superseded": self = .superseded
            default: self = .other(rawValue)
            }
        }
    }

    public enum ApprovedBy: Equatable, Sendable {
        case auto
        case user
        case other(String)

        public var rawValue: String {
            switch self {
            case .auto: return "auto"
            case .user: return "user"
            case .other(let value): return value
            }
        }

        public init(rawValue: String) {
            switch rawValue {
            case "auto": self = .auto
            case "user": self = .user
            default: self = .other(rawValue)
            }
        }
    }

    public init(
        fileID: String,
        sourceID: String,
        originalName: String,
        originalPath: String,
        currentPath: String,
        fileExtension: String,
        mimeType: String,
        sizeBytes: Int64,
        createdAt: String,
        modifiedAt: String,
        contentHash: String,
        discoveredAt: String,
        status: String = "discovered",
        error: String? = nil,
        category: Category? = nil,
        classificationSignals: ClassificationSignals? = nil,
        extractedMetadata: [String: JSONValue] = [:],
        suggestedName: String? = nil,
        suggestedDestination: String? = nil,
        namingSignals: NamingSignals? = nil,
        duplicateOf: String? = nil,
        versionGroupID: String? = nil,
        versionRank: VersionRank? = nil,
        duplicateSignals: DuplicateSignals? = nil,
        confidenceScore: Int? = nil,
        confidenceBreakdown: [String: JSONValue] = [:],
        tier: Tier? = nil,
        batchID: String? = nil,
        processedAt: String? = nil,
        approvedBy: ApprovedBy? = nil,
        approvedAt: String? = nil,
        reversible: Bool = true
    ) {
        self.fileID = fileID
        self.sourceID = sourceID
        self.originalName = originalName
        self.originalPath = originalPath
        self.currentPath = currentPath
        self.fileExtension = fileExtension
        self.mimeType = mimeType
        self.sizeBytes = sizeBytes
        self.createdAt = createdAt
        self.modifiedAt = modifiedAt
        self.contentHash = contentHash
        self.discoveredAt = discoveredAt
        self.status = status
        self.error = error
        self.category = category
        self.classificationSignals = classificationSignals
        self.extractedMetadata = extractedMetadata
        self.suggestedName = suggestedName
        self.suggestedDestination = suggestedDestination
        self.namingSignals = namingSignals
        self.duplicateOf = duplicateOf
        self.versionGroupID = versionGroupID
        self.versionRank = versionRank
        self.duplicateSignals = duplicateSignals
        self.confidenceScore = confidenceScore
        self.confidenceBreakdown = confidenceBreakdown
        self.tier = tier
        self.batchID = batchID
        self.processedAt = processedAt
        self.approvedBy = approvedBy
        self.approvedAt = approvedAt
        self.reversible = reversible
    }
}

extension FileRecordSnapshot.VersionRank: Codable {
    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        self.init(rawValue: try container.decode(String.self))
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}

extension FileRecordSnapshot.ApprovedBy: Codable {
    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        self.init(rawValue: try container.decode(String.self))
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}

extension FileRecordSnapshot: Codable {
    private enum CodingKeys: String, CodingKey {
        case fileID = "file_id"
        case sourceID = "source_id"
        case originalName = "original_name"
        case originalPath = "original_path"
        case currentPath = "current_path"
        case fileExtension = "extension"
        case mimeType = "mime_type"
        case sizeBytes = "size_bytes"
        case createdAt = "created_at"
        case modifiedAt = "modified_at"
        case contentHash = "content_hash"
        case discoveredAt = "discovered_at"
        case status
        case error
        case category
        case classificationSignals = "classification_signals"
        case extractedMetadata = "extracted_metadata"
        case suggestedName = "suggested_name"
        case suggestedDestination = "suggested_destination"
        case namingSignals = "naming_signals"
        case duplicateOf = "duplicate_of"
        case versionGroupID = "version_group_id"
        case versionRank = "version_rank"
        case duplicateSignals = "duplicate_signals"
        case confidenceScore = "confidence_score"
        case confidenceBreakdown = "confidence_breakdown"
        case tier
        case batchID = "batch_id"
        case processedAt = "processed_at"
        case approvedBy = "approved_by"
        case approvedAt = "approved_at"
        case reversible
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            // Identity fields: decoded with `decode`, not `decodeIfPresent`
            // — a record missing one of these is malformed at a level
            // MetadataStoreReader treats as an unparseable individual
            // record, not a field to silently default.
            fileID: try container.decode(String.self, forKey: .fileID),
            sourceID: try container.decode(String.self, forKey: .sourceID),
            originalName: try container.decode(String.self, forKey: .originalName),
            originalPath: try container.decode(String.self, forKey: .originalPath),
            currentPath: try container.decode(String.self, forKey: .currentPath),
            fileExtension: try container.decode(String.self, forKey: .fileExtension),
            mimeType: try container.decode(String.self, forKey: .mimeType),
            sizeBytes: try container.decode(Int64.self, forKey: .sizeBytes),
            createdAt: try container.decode(String.self, forKey: .createdAt),
            modifiedAt: try container.decode(String.self, forKey: .modifiedAt),
            contentHash: try container.decode(String.self, forKey: .contentHash),
            discoveredAt: try container.decode(String.self, forKey: .discoveredAt),
            // Pipeline-stage fields: decoded defensively — absence, or a
            // future additive field this type doesn't know about yet,
            // must never fail the whole record.
            status: try container.decodeIfPresent(String.self, forKey: .status) ?? "discovered",
            error: try container.decodeIfPresent(String.self, forKey: .error),
            category: try container.decodeIfPresent(Category.self, forKey: .category),
            classificationSignals: try container.decodeIfPresent(ClassificationSignals.self, forKey: .classificationSignals),
            extractedMetadata: try container.decodeIfPresent([String: JSONValue].self, forKey: .extractedMetadata) ?? [:],
            suggestedName: try container.decodeIfPresent(String.self, forKey: .suggestedName),
            suggestedDestination: try container.decodeIfPresent(String.self, forKey: .suggestedDestination),
            namingSignals: try container.decodeIfPresent(NamingSignals.self, forKey: .namingSignals),
            duplicateOf: try container.decodeIfPresent(String.self, forKey: .duplicateOf),
            versionGroupID: try container.decodeIfPresent(String.self, forKey: .versionGroupID),
            versionRank: try container.decodeIfPresent(FileRecordSnapshot.VersionRank.self, forKey: .versionRank),
            duplicateSignals: try container.decodeIfPresent(DuplicateSignals.self, forKey: .duplicateSignals),
            confidenceScore: try container.decodeIfPresent(Int.self, forKey: .confidenceScore),
            confidenceBreakdown: try container.decodeIfPresent([String: JSONValue].self, forKey: .confidenceBreakdown) ?? [:],
            tier: try container.decodeIfPresent(Tier.self, forKey: .tier),
            batchID: try container.decodeIfPresent(String.self, forKey: .batchID),
            processedAt: try container.decodeIfPresent(String.self, forKey: .processedAt),
            approvedBy: try container.decodeIfPresent(FileRecordSnapshot.ApprovedBy.self, forKey: .approvedBy),
            approvedAt: try container.decodeIfPresent(String.self, forKey: .approvedAt),
            reversible: try container.decodeIfPresent(Bool.self, forKey: .reversible) ?? true
        )
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(fileID, forKey: .fileID)
        try container.encode(sourceID, forKey: .sourceID)
        try container.encode(originalName, forKey: .originalName)
        try container.encode(originalPath, forKey: .originalPath)
        try container.encode(currentPath, forKey: .currentPath)
        try container.encode(fileExtension, forKey: .fileExtension)
        try container.encode(mimeType, forKey: .mimeType)
        try container.encode(sizeBytes, forKey: .sizeBytes)
        try container.encode(createdAt, forKey: .createdAt)
        try container.encode(modifiedAt, forKey: .modifiedAt)
        try container.encode(contentHash, forKey: .contentHash)
        try container.encode(discoveredAt, forKey: .discoveredAt)
        try container.encode(status, forKey: .status)
        try container.encodeIfPresent(error, forKey: .error)
        try container.encodeIfPresent(category, forKey: .category)
        try container.encodeIfPresent(classificationSignals, forKey: .classificationSignals)
        try container.encode(extractedMetadata, forKey: .extractedMetadata)
        try container.encodeIfPresent(suggestedName, forKey: .suggestedName)
        try container.encodeIfPresent(suggestedDestination, forKey: .suggestedDestination)
        try container.encodeIfPresent(namingSignals, forKey: .namingSignals)
        try container.encodeIfPresent(duplicateOf, forKey: .duplicateOf)
        try container.encodeIfPresent(versionGroupID, forKey: .versionGroupID)
        try container.encodeIfPresent(versionRank, forKey: .versionRank)
        try container.encodeIfPresent(duplicateSignals, forKey: .duplicateSignals)
        try container.encodeIfPresent(confidenceScore, forKey: .confidenceScore)
        try container.encode(confidenceBreakdown, forKey: .confidenceBreakdown)
        try container.encodeIfPresent(tier, forKey: .tier)
        try container.encodeIfPresent(batchID, forKey: .batchID)
        try container.encodeIfPresent(processedAt, forKey: .processedAt)
        try container.encodeIfPresent(approvedBy, forKey: .approvedBy)
        try container.encodeIfPresent(approvedAt, forKey: .approvedAt)
        try container.encode(reversible, forKey: .reversible)
    }
}
