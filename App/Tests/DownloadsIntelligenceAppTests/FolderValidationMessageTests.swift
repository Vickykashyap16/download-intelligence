import XCTest
import EngineBridge
@testable import DownloadsIntelligenceApp

/// Pure, synchronous tests for `FolderValidationMessage` — proves every
/// `FolderValidationOutcome` case maps to a message (or, for `.valid`, to
/// `nil`), and that no message is empty/alarmist-looking by construction.
final class FolderValidationMessageTests: XCTestCase {
    func test_valid_hasNoMessage() {
        XCTAssertNil(FolderValidationMessage.inline(for: .valid))
    }

    func test_everyNonValidOutcome_hasANonEmptyMessage() {
        let nonValidOutcomes: [FolderValidationOutcome] = [
            .doesNotExist, .notADirectory, .notReadable, .notWritable
        ]
        for outcome in nonValidOutcomes {
            let message = FolderValidationMessage.inline(for: outcome)
            XCTAssertNotNil(message, "\(outcome) should produce a message")
            XCTAssertFalse(message?.isEmpty ?? true, "\(outcome)'s message should not be empty")
        }
    }

    func test_messagesAreDistinctPerOutcome() {
        let outcomes: [FolderValidationOutcome] = [.doesNotExist, .notADirectory, .notReadable, .notWritable]
        let messages = Set(outcomes.compactMap(FolderValidationMessage.inline(for:)))
        XCTAssertEqual(messages.count, outcomes.count, "each outcome should have its own distinct message")
    }
}
