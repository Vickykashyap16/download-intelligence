import XCTest
import EngineBridge
import enum EngineBridge.Category
@testable import DownloadsIntelligenceApp

final class FlagReasonResolverTests: XCTestCase {

    private func makeRecord(
        fileID: String = "1",
        category: Category? = nil,
        classificationSignals: ClassificationSignals? = nil,
        duplicateSignals: DuplicateSignals? = nil,
        confidenceBreakdown: [String: JSONValue] = [:]
    ) -> FileRecordSnapshot {
        FileRecordSnapshot(
            fileID: fileID,
            sourceID: "downloads",
            originalName: "\(fileID).pdf",
            originalPath: "/Users/fixture/Downloads/\(fileID).pdf",
            currentPath: "/Users/fixture/Downloads/\(fileID).pdf",
            fileExtension: ".pdf",
            mimeType: "application/pdf",
            sizeBytes: 1024,
            createdAt: "2026-07-27T10:00:00Z",
            modifiedAt: "2026-07-27T10:00:00Z",
            contentHash: "hash-\(fileID)",
            discoveredAt: "2026-07-27T10:00:00Z",
            category: category,
            classificationSignals: classificationSignals,
            duplicateSignals: duplicateSignals,
            confidenceBreakdown: confidenceBreakdown,
            tier: .reviewRequired
        )
    }

    // MARK: - The four hard-floor conditions, in fixed order

    func test_resolve_unknownCategory() {
        let record = makeRecord(category: .unknown)
        XCTAssertEqual(FlagReasonResolver.resolve(for: record), "This file's category couldn't be determined")
    }

    func test_resolve_fuzzyDuplicate() {
        let record = makeRecord(duplicateSignals: DuplicateSignals(fuzzyDuplicate: true))
        XCTAssertEqual(FlagReasonResolver.resolve(for: record), "Near-duplicate or fuzzy image match found")
    }

    func test_resolve_multiDocumentDetected() {
        let record = makeRecord(classificationSignals: ClassificationSignals(multiDocumentDetected: true))
        XCTAssertEqual(FlagReasonResolver.resolve(for: record), "This file appears to contain more than one document")
    }

    func test_resolve_lockedFile() {
        let record = makeRecord(classificationSignals: ClassificationSignals(locked: true))
        XCTAssertEqual(FlagReasonResolver.resolve(for: record), "Locked or password-protected file")
    }

    // MARK: - Fixed priority order when multiple hard floors would apply

    func test_resolve_unknownCategoryTakesPriorityOverOtherHardFloors() {
        let record = makeRecord(
            category: .unknown,
            classificationSignals: ClassificationSignals(locked: true),
            duplicateSignals: DuplicateSignals(fuzzyDuplicate: true)
        )
        XCTAssertEqual(FlagReasonResolver.resolve(for: record), "This file's category couldn't be determined")
    }

    // MARK: - No hard floor: falls back to the single largest-magnitude deduction

    func test_resolve_noHardFloor_fallsBackToLargestDeduction() {
        let record = makeRecord(
            category: .invoice,
            confidenceBreakdown: [
                "missing_optional_field:currency": .number(-2),
                "non_english_content": .number(-10),
            ]
        )
        XCTAssertEqual(FlagReasonResolver.resolve(for: record), "Non-English content detected")
    }

    // MARK: - Defensive fallback: no hard floor and an empty breakdown

    func test_resolve_noHardFloorAndEmptyBreakdown_usesGenericFallback() {
        let record = makeRecord(category: .invoice, confidenceBreakdown: [:])
        XCTAssertEqual(FlagReasonResolver.resolve(for: record), "This file needs your review")
    }
}
