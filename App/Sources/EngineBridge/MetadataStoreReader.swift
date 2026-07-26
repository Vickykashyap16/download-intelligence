import Foundation

/// Reads `Database/Metadata/metadata_store.json` — the cumulative JSON
/// array of `FileRecord` objects the engine maintains
/// (`src/storage/database.py`'s `load_metadata_store()`) — exactly as it
/// exists on disk today, with no modification to the file and no
/// assumption the engine will ever write it differently than it does now.
///
/// Not an actor: this type holds no mutable state and performs a single,
/// self-contained, synchronous file read per call — there is nothing here
/// that needs actor isolation to be safe, unlike `ProcessRunner` (a running
/// subprocess) or `EngineMutationGuard` (shared mutable sequencing state).
public struct MetadataStoreReader: Sendable {
    private let locations: EngineArtifactLocations

    public init(locations: EngineArtifactLocations) {
        self.locations = locations
    }

    /// Reads and parses the metadata store.
    ///
    /// A missing file is treated as a normal, empty result — `records: []`,
    /// `issues: []` — not an error: a fresh installation that has never
    /// run `scan` legitimately has no metadata store file yet (the
    /// product's own First Run Experience / Empty State condition, not a
    /// broken artifact).
    ///
    /// A file that exists but cannot even be parsed as a JSON array at the
    /// top level (the whole file is corrupted, truncated, or not JSON at
    /// all) throws `EngineBridgeError.artifactUnreadable` — there is no
    /// partial result to salvage at that point.
    ///
    /// A well-formed JSON array containing one or more individually
    /// malformed elements (a record missing a required identity field, or
    /// carrying a field of the wrong type) does **not** throw: every
    /// element that decodes successfully is returned in `records`, and
    /// every element that doesn't is recorded in `issues` with its index
    /// and original content — one corrupted record must never hide every
    /// other, healthy record in a store that can hold thousands of them.
    public func read() throws -> MetadataStoreReadResult {
        let url = locations.metadataStoreURL

        guard FileManager.default.fileExists(atPath: url.path) else {
            return MetadataStoreReadResult(records: [], issues: [])
        }

        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            throw EngineBridgeError.artifactUnreadable(path: url.path, reason: String(describing: error))
        }

        let topLevelObject: Any
        do {
            topLevelObject = try JSONSerialization.jsonObject(with: data, options: [])
        } catch {
            throw EngineBridgeError.artifactUnreadable(path: url.path, reason: String(describing: error))
        }

        guard let elements = topLevelObject as? [Any] else {
            throw EngineBridgeError.artifactUnreadable(
                path: url.path,
                reason: "expected a JSON array at the top level, found a different JSON shape"
            )
        }

        var records: [FileRecordSnapshot] = []
        var issues: [ArtifactParseIssue] = []
        let decoder = JSONDecoder()

        for (index, element) in elements.enumerated() {
            do {
                // Re-serializing this single, already-isolated array element
                // back to Data via JSONSerialization — deliberately *not*
                // via this package's own JSONValue, which represents every
                // JSON number as a Double — is what lets one bad element be
                // isolated without corrupting every other, healthy element's
                // integer fields in the process. JSONSerialization's
                // NSNumber-backed values preserve whether a number was
                // originally written as a JSON integer or a JSON float, so
                // round-tripping `"size_bytes": 204800` back through it still
                // decodes as `Int64` afterward; round-tripping the same value
                // through a Double-typed representation could silently turn
                // it into `204800.0`, which strict `Int64` decoding would
                // then reject. JSONValue remains exactly the right tool for
                // this package's genuinely free-form fields
                // (`extracted_metadata`, `confidence_breakdown`, the action
                // log's `details`) because those are decoded forward, once,
                // directly from real bytes — never re-encoded and decoded a
                // second time the way this per-element isolation requires.
                let elementData = try JSONSerialization.data(withJSONObject: element, options: [])
                let record = try decoder.decode(FileRecordSnapshot.self, from: elementData)
                records.append(record)
            } catch {
                let rawContent = (try? JSONSerialization.data(withJSONObject: element, options: [.sortedKeys]))
                    .flatMap { String(data: $0, encoding: .utf8) } ?? String(describing: element)
                issues.append(
                    ArtifactParseIssue(index: index, rawContent: rawContent, reason: String(describing: error))
                )
            }
        }

        return MetadataStoreReadResult(records: records, issues: issues)
    }
}

/// The result of one `MetadataStoreReader.read()` call: every
/// successfully-parsed record, every individually-unparseable element
/// encountered along the way, and — derived from the same single parse,
/// never re-read separately — the aggregate `summary` WP-GUI-00's Scope
/// names as "the metadata store's summary state."
public struct MetadataStoreReadResult: Equatable, Sendable {
    public let records: [FileRecordSnapshot]
    public let issues: [ArtifactParseIssue]

    public init(records: [FileRecordSnapshot], issues: [ArtifactParseIssue]) {
        self.records = records
        self.issues = issues
    }

    public var summary: MetadataStoreSummary {
        MetadataStoreSummary(records: records)
    }
}

/// Aggregate counts over a set of `FileRecordSnapshot`s: total record
/// count, and counts broken down by tier, by category, and by pipeline
/// status. Computed directly from already-parsed records rather than by
/// re-reading or re-parsing the underlying file, so there is exactly one
/// parser for `metadata_store.json` and this summary can never disagree
/// with the full record list it was derived from.
public struct MetadataStoreSummary: Equatable, Sendable {
    public let totalRecordCount: Int
    public let countsByTier: [Tier: Int]
    public let countsByCategory: [Category: Int]
    public let countsByStatus: [String: Int]

    public init(records: [FileRecordSnapshot]) {
        self.totalRecordCount = records.count
        self.countsByTier = Dictionary(grouping: records.compactMap(\.tier), by: { $0 })
            .mapValues(\.count)
        self.countsByCategory = Dictionary(grouping: records.compactMap(\.category), by: { $0 })
            .mapValues(\.count)
        self.countsByStatus = Dictionary(grouping: records, by: \.status)
            .mapValues(\.count)
    }
}
