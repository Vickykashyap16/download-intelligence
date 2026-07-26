import XCTest
@testable import EngineBridge

final class MetadataStoreReaderTests: XCTestCase {

    private func fixtureLocations(project: String) throws -> EngineArtifactLocations {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        return EngineArtifactLocations(projectRootURL: fixturesRoot.appendingPathComponent(project))
    }

    // MARK: - Mixed well-formed / malformed records

    func test_readsValidRecordsAndCapturesMalformedRecordAsIssue() throws {
        let reader = MetadataStoreReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let result = try reader.read()

        // Fixture file: record 0 (rich, valid), record 1 (minimal, valid),
        // record 2 (missing required "file_id").
        XCTAssertEqual(result.records.count, 2)
        XCTAssertEqual(result.issues.count, 1)
        XCTAssertEqual(result.issues.first?.index, 2)
    }

    func test_richRecord_decodesEveryFieldCorrectly() throws {
        let reader = MetadataStoreReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let result = try reader.read()

        let record = try XCTUnwrap(result.records.first(where: { $0.fileID == "file-001" }))
        XCTAssertEqual(record.sourceID, "downloads")
        XCTAssertEqual(record.originalName, "invoice.pdf")
        XCTAssertEqual(record.fileExtension, ".pdf")
        XCTAssertEqual(record.mimeType, "application/pdf")
        XCTAssertEqual(record.sizeBytes, 204_800)
        XCTAssertEqual(record.status, "executed")
        XCTAssertEqual(record.category, .invoice)
        XCTAssertEqual(record.classificationSignals?.detectedLanguage, "en")
        XCTAssertEqual(record.extractedMetadata["vendor"]?.stringValue, "Acme Corp")
        XCTAssertEqual(record.suggestedName, "2026-07-25_Acme_Invoice.pdf")
        XCTAssertEqual(record.namingSignals?.fieldsFellBack, [])
        XCTAssertEqual(record.versionRank, .latest)
        XCTAssertEqual(record.duplicateSignals, DuplicateSignals())
        XCTAssertEqual(record.confidenceScore, 97)
        XCTAssertEqual(record.tier, .auto)
        XCTAssertEqual(record.batchID, "batch-001")
        XCTAssertEqual(record.approvedBy, .auto)
        XCTAssertTrue(record.reversible)
    }

    func test_minimalRecord_appliesRealPythonDefaultsForAbsentFields() throws {
        let reader = MetadataStoreReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let result = try reader.read()

        let record = try XCTUnwrap(result.records.first(where: { $0.fileID == "file-002" }))
        // None of the pipeline-stage fields were present in the fixture for
        // this record — every one of them must fall back to the real
        // dataclass default rather than fail the decode.
        XCTAssertEqual(record.status, "discovered")
        XCTAssertNil(record.category)
        XCTAssertNil(record.classificationSignals)
        XCTAssertEqual(record.extractedMetadata, [:])
        XCTAssertNil(record.tier)
        XCTAssertNil(record.confidenceScore)
        XCTAssertTrue(record.reversible)
    }

    func test_unrecognizedCategoryValue_decodesToOtherRatherThanFailing() throws {
        XCTAssertEqual(Category(rawValue: "Spreadsheet"), .other("Spreadsheet"))
        XCTAssertEqual(Category(rawValue: "Spreadsheet").rawValue, "Spreadsheet")
    }

    func test_unrecognizedTierValue_decodesToOtherRatherThanFailing() throws {
        XCTAssertEqual(Tier(rawValue: "needs_manual_review"), .other("needs_manual_review"))
    }

    // MARK: - Summary derivation

    func test_summary_reflectsOnlySuccessfullyParsedRecords() throws {
        let reader = MetadataStoreReader(locations: try fixtureLocations(project: "FakeEngineProject"))
        let result = try reader.read()
        let summary = result.summary

        XCTAssertEqual(summary.totalRecordCount, 2)
        XCTAssertEqual(summary.countsByTier[.auto], 1)
        XCTAssertEqual(summary.countsByCategory[.invoice], 1)
        XCTAssertEqual(summary.countsByStatus["executed"], 1)
        XCTAssertEqual(summary.countsByStatus["discovered"], 1)
    }

    // MARK: - Missing file: normal empty state (fresh install, never scanned)

    func test_missingMetadataStore_returnsEmptyResultRatherThanThrowing() throws {
        let reader = MetadataStoreReader(locations: try fixtureLocations(project: "EmptyEngineProject"))
        let result = try reader.read()

        XCTAssertTrue(result.records.isEmpty)
        XCTAssertTrue(result.issues.isEmpty)
        XCTAssertEqual(result.summary.totalRecordCount, 0)
    }

    // MARK: - Whole-file corruption: no partial result is possible

    func test_topLevelNotAnArray_throwsArtifactUnreadable() throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("MetadataStoreReaderTests-\(UUID().uuidString)")
        let metadataDirectory = tempDirectory.appendingPathComponent("Database/Metadata")
        try FileManager.default.createDirectory(at: metadataDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDirectory) }

        let storeURL = metadataDirectory.appendingPathComponent("metadata_store.json")
        try #"{"not": "an array"}"#.write(to: storeURL, atomically: true, encoding: .utf8)

        let reader = MetadataStoreReader(locations: EngineArtifactLocations(projectRootURL: tempDirectory))

        do {
            _ = try reader.read()
            XCTFail("expected artifactUnreadable to be thrown")
        } catch EngineBridgeError.artifactUnreadable {
            // expected
        }
    }

    func test_invalidJSONSyntax_throwsArtifactUnreadable() throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("MetadataStoreReaderTests-\(UUID().uuidString)")
        let metadataDirectory = tempDirectory.appendingPathComponent("Database/Metadata")
        try FileManager.default.createDirectory(at: metadataDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDirectory) }

        let storeURL = metadataDirectory.appendingPathComponent("metadata_store.json")
        try "not json at all {{{".write(to: storeURL, atomically: true, encoding: .utf8)

        let reader = MetadataStoreReader(locations: EngineArtifactLocations(projectRootURL: tempDirectory))

        do {
            _ = try reader.read()
            XCTFail("expected artifactUnreadable to be thrown")
        } catch EngineBridgeError.artifactUnreadable {
            // expected
        }
    }
}
