import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Verifies `ErrorPresentation.forEngineBridgeFailure(_:)` — the one place
/// in the GUI layer that translates a real `EngineBridgeError` into the
/// plain-language explanation + resolution action + technical detail the
/// shared Error State template requires (`High-Fidelity UI Specification.md`
/// §14). One test per `EngineBridgeError` case, so every case this package
/// can throw is proven to produce a sane, plain-language presentation —
/// not just the two cases exercised end-to-end in
/// `AppLifecycleControllerTests`.
final class ErrorPresentationTests: XCTestCase {

    /// Shared assertions every case must satisfy: the user never sees a
    /// raw technical error as the *explanation* (`High-Fidelity UI
    /// Specification.md` §14 — "the user never sees a raw technical error
    /// by default"), and the technical detail is always preserved
    /// somewhere for a genuine bug report ("never deleted or hidden
    /// permanently").
    private func assertPlainLanguage(_ presentation: ErrorPresentation, rawDescription: String, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertFalse(presentation.heading.isEmpty, file: file, line: line)
        XCTAssertFalse(presentation.explanation.isEmpty, file: file, line: line)
        XCTAssertNotEqual(presentation.explanation, rawDescription, "the explanation must be plain-language, not the raw technical description", file: file, line: line)
        XCTAssertEqual(presentation.technicalDetail, rawDescription, "the raw technical detail must still be available, never deleted", file: file, line: line)
        XCTAssertEqual(presentation.layout, .fullScreen, "WP-GUI-01's only call site is a screen-level startup failure", file: file, line: line)
    }

    func test_commandRequiresInteractiveInput() {
        let error = EngineBridgeError.commandRequiresInteractiveInput(.status)
        let presentation = ErrorPresentation.forEngineBridgeFailure(error)
        assertPlainLanguage(presentation, rawDescription: String(describing: error))
        XCTAssertNotNil(presentation.resolutionActionTitle)
    }

    func test_anotherMutatingOperationInProgress() {
        let error = EngineBridgeError.anotherMutatingOperationInProgress
        let presentation = ErrorPresentation.forEngineBridgeFailure(error)
        assertPlainLanguage(presentation, rawDescription: String(describing: error))
        // Nothing to resolve — the user just needs to wait, per `Desktop
        // Implementation Blueprint.md` §7's single-mutation-slot rule.
        XCTAssertNil(presentation.resolutionActionTitle)
    }

    func test_failedToLaunchProcess() {
        let error = EngineBridgeError.failedToLaunchProcess("posix_spawn failed")
        let presentation = ErrorPresentation.forEngineBridgeFailure(error)
        assertPlainLanguage(presentation, rawDescription: String(describing: error))
        XCTAssertNotNil(presentation.resolutionActionTitle)
    }

    func test_projectRootNotFound() {
        let error = EngineBridgeError.projectRootNotFound("/nonexistent/path")
        let presentation = ErrorPresentation.forEngineBridgeFailure(error)
        assertPlainLanguage(presentation, rawDescription: String(describing: error))
        XCTAssertNotNil(presentation.resolutionActionTitle)
    }

    func test_artifactUnreadable_mentionsTheFileByName() {
        let error = EngineBridgeError.artifactUnreadable(path: "/fixture/project/src/config/sources.yaml", reason: "malformed YAML")
        let presentation = ErrorPresentation.forEngineBridgeFailure(error)
        assertPlainLanguage(presentation, rawDescription: String(describing: error))
        XCTAssertTrue(presentation.explanation.contains("sources.yaml"), "should name the specific file, not just say 'a file'")
        XCTAssertNotNil(presentation.resolutionActionTitle)
    }

    func test_artifactNotFound_mentionsTheFileByName() {
        let error = EngineBridgeError.artifactNotFound(path: "/fixture/project/Release/VERSIONS.md")
        let presentation = ErrorPresentation.forEngineBridgeFailure(error)
        assertPlainLanguage(presentation, rawDescription: String(describing: error))
        XCTAssertTrue(presentation.explanation.contains("VERSIONS.md"))
    }

    func test_engineVersionTooOld_namesBothVersions() {
        let engineVersion = SemanticVersion(major: 0, minor: 5, patch: 0)
        let minimum = SemanticVersion(major: 0, minor: 8, patch: 0)
        let error = EngineBridgeError.engineVersionTooOld(engineVersion: engineVersion, minimumSupportedVersion: minimum)
        let presentation = ErrorPresentation.forEngineBridgeFailure(error)
        assertPlainLanguage(presentation, rawDescription: String(describing: error))
        XCTAssertTrue(presentation.explanation.contains("0.5.0"))
        XCTAssertTrue(presentation.explanation.contains("0.8.0"))
        XCTAssertNotNil(presentation.resolutionActionTitle)
    }

    func test_engineVersionTooNew_namesBothVersions() {
        let engineVersion = SemanticVersion(major: 9, minor: 9, patch: 9)
        let maximum = SemanticVersion(major: 0, minor: 99, patch: 0)
        let error = EngineBridgeError.engineVersionTooNew(engineVersion: engineVersion, maximumSupportedVersion: maximum)
        let presentation = ErrorPresentation.forEngineBridgeFailure(error)
        assertPlainLanguage(presentation, rawDescription: String(describing: error))
        XCTAssertTrue(presentation.explanation.contains("9.9.9"))
        XCTAssertTrue(presentation.explanation.contains("0.99.0"))
        XCTAssertNotNil(presentation.resolutionActionTitle)
    }

    func test_inlineLayoutIsPreservedWhenRequested() {
        let error = EngineBridgeError.anotherMutatingOperationInProgress
        let presentation = ErrorPresentation.forEngineBridgeFailure(error, layout: .inline)
        XCTAssertEqual(presentation.layout, .inline)
    }

    /// Distinguishes the Error State's tone from an Empty State's
    /// (`06 Visual Design System.md` §12: "None of the following ever...
    /// [uses] Warning/Error color or iconography" for empty states, and
    /// the converse for error states) by confirming `.artifactNotFound`'s
    /// mapping — the one case genuinely ambiguous with "empty" — still
    /// reads as something needing attention, not as a calm, nothing's-
    /// wrong empty condition.
    func test_artifactNotFound_readsAsNeedingAttentionNotAsAnEmptyState() {
        let error = EngineBridgeError.artifactNotFound(path: "/fixture/project/Release/VERSIONS.md")
        let presentation = ErrorPresentation.forEngineBridgeFailure(error)
        let emptyStateLanguage = ["nothing here", "all caught up", "fully caught up"]
        for phrase in emptyStateLanguage {
            XCTAssertFalse(
                presentation.heading.lowercased().contains(phrase),
                "heading should not borrow Empty State framing"
            )
        }
    }
}
