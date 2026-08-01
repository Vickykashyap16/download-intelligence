import XCTest

/// A `review_required` item must never be approvable from anywhere in the
/// Flagged card or the flagged "why" view — a structural requirement, not
/// a stylistic one (Figma Production Guide, Frame 06: "no control anywhere
/// on a 'Flagged for you' card may approve it"). `FlaggedCardView` and
/// `FlaggedDetailView` are their own dedicated types specifically so this
/// can be verified mechanically, in isolation, rather than by trusting a
/// runtime conditional inside a type shared with the approvable
/// `NeedsInputCardView`/`ReviewDetailView`.
///
/// This reads each file's own real source at the exact path it was
/// compiled from (`#filePath`, resolved relative to this test file's own
/// location) and asserts it never contains the word "approve" — a literal,
/// mechanical implementation of the WP-GUI-06 Test Plan's own "a static-
/// analysis/code-review check confirming no approve affordance exists in
/// the flagged-card component."
final class FlaggedViewsStructuralTests: XCTestCase {

    private var sourcesReviewDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // .../Tests/DownloadsIntelligenceAppTests
            .deletingLastPathComponent() // .../Tests
            .deletingLastPathComponent() // .../App
            .appendingPathComponent("Sources/DownloadsIntelligenceApp/Review")
    }

    private func assertNoApproveAffordance(inFileNamed fileName: String) throws {
        let url = sourcesReviewDirectory.appendingPathComponent(fileName)
        let source = try String(contentsOf: url, encoding: .utf8)

        XCTAssertFalse(
            source.localizedCaseInsensitiveContains("approve"),
            "\(fileName) must never contain any Approve affordance, by design — review_required items can never be approved from anywhere in this file"
        )
    }

    func test_flaggedCardViewSource_containsNoApproveAffordance() throws {
        try assertNoApproveAffordance(inFileNamed: "FlaggedCardView.swift")
    }

    func test_flaggedDetailViewSource_containsNoApproveAffordance() throws {
        try assertNoApproveAffordance(inFileNamed: "FlaggedDetailView.swift")
    }
}
