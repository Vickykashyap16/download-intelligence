import XCTest
@testable import EngineBridge

/// Tests for `FolderAccessValidator` (WP-GUI-00A) — the collaborator
/// `EngineBridge.validateFolder(at:requireWritable:)` delegates to.
///
/// "Does not exist" and "not a directory" are exercised against a real,
/// on-disk temp directory/file, since those conditions are simple and
/// portable to reproduce for real. "Not readable"/"not writable" are
/// exercised against an injected fake `FileManager` instead of real
/// `chmod` calls: permission enforcement is environment-dependent (a
/// process running as root, or a CI sandbox with unusual defaults, can
/// silently ignore `chmod 000`), so a deterministic fake is the only way
/// to reliably prove those two branches without a flaky test.
final class FolderAccessValidatorTests: XCTestCase {

    // MARK: - Real filesystem: existence / directory-ness

    func test_validate_pathDoesNotExist_returnsDoesNotExist() {
        let validator = FolderAccessValidator()
        let missingURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("FolderAccessValidatorTests-missing-\(UUID().uuidString)")

        let outcome = validator.validate(missingURL, requireWritable: false)

        XCTAssertEqual(outcome, .doesNotExist)
    }

    func test_validate_pathIsARegularFile_returnsNotADirectory() throws {
        let validator = FolderAccessValidator()
        let fileURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("FolderAccessValidatorTests-file-\(UUID().uuidString).txt")
        try "not a folder".write(to: fileURL, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: fileURL) }

        let outcome = validator.validate(fileURL, requireWritable: false)

        XCTAssertEqual(outcome, .notADirectory)
    }

    func test_validate_realReadableDirectory_requireWritableFalse_returnsValid() throws {
        let validator = FolderAccessValidator()
        let directoryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("FolderAccessValidatorTests-dir-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directoryURL) }

        let outcome = validator.validate(directoryURL, requireWritable: false)

        XCTAssertEqual(outcome, .valid)
    }

    func test_validate_realWritableDirectory_requireWritableTrue_returnsValid() throws {
        let validator = FolderAccessValidator()
        let directoryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("FolderAccessValidatorTests-dir-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directoryURL) }

        let outcome = validator.validate(directoryURL, requireWritable: true)

        XCTAssertEqual(outcome, .valid)
    }

    // MARK: - Fake FileManager: permission-denied branches

    func test_validate_notReadable_returnsNotReadable() {
        let fake = StubFileManager()
        fake.existsResult = true
        fake.isDirectoryResult = true
        fake.isReadableResult = false
        let validator = FolderAccessValidator(fileManager: fake)

        let outcome = validator.validate(URL(fileURLWithPath: "/irrelevant"), requireWritable: false)

        XCTAssertEqual(outcome, .notReadable)
    }

    func test_validate_readableButNotWritable_requireWritableTrue_returnsNotWritable() {
        let fake = StubFileManager()
        fake.existsResult = true
        fake.isDirectoryResult = true
        fake.isReadableResult = true
        fake.isWritableResult = false
        let validator = FolderAccessValidator(fileManager: fake)

        let outcome = validator.validate(URL(fileURLWithPath: "/irrelevant"), requireWritable: true)

        XCTAssertEqual(outcome, .notWritable)
    }

    func test_validate_readableButNotWritable_requireWritableFalse_returnsValid() {
        // The whole point of the `requireWritable` flag: an unwritable
        // folder must not block a caller (e.g. a Source-folder step) that
        // never asked for write access in the first place.
        let fake = StubFileManager()
        fake.existsResult = true
        fake.isDirectoryResult = true
        fake.isReadableResult = true
        fake.isWritableResult = false
        let validator = FolderAccessValidator(fileManager: fake)

        let outcome = validator.validate(URL(fileURLWithPath: "/irrelevant"), requireWritable: false)

        XCTAssertEqual(outcome, .valid)
    }

    func test_validate_checkOrdering_existenceBeforeDirectoryBeforeReadableBeforeWritable() {
        // A path that fails every check at once must report the *first*
        // reason in the documented precedence, not some other one — this
        // pins that precedence down explicitly rather than leaving it as
        // an implicit consequence of the guard-statement order.
        let fake = StubFileManager()
        fake.existsResult = false
        fake.isDirectoryResult = false
        fake.isReadableResult = false
        fake.isWritableResult = false
        let validator = FolderAccessValidator(fileManager: fake)

        XCTAssertEqual(validator.validate(URL(fileURLWithPath: "/irrelevant"), requireWritable: true), .doesNotExist)

        fake.existsResult = true
        XCTAssertEqual(validator.validate(URL(fileURLWithPath: "/irrelevant"), requireWritable: true), .notADirectory)

        fake.isDirectoryResult = true
        XCTAssertEqual(validator.validate(URL(fileURLWithPath: "/irrelevant"), requireWritable: true), .notReadable)

        fake.isReadableResult = true
        XCTAssertEqual(validator.validate(URL(fileURLWithPath: "/irrelevant"), requireWritable: true), .notWritable)

        fake.isWritableResult = true
        XCTAssertEqual(validator.validate(URL(fileURLWithPath: "/irrelevant"), requireWritable: true), .valid)
    }
}

/// A deterministic, fully-controllable stand-in for `FileManager`, used
/// only by this test file. `FileManager`'s relevant methods are all
/// declared `open`, so overriding them here never touches the real
/// filesystem for the cases under test.
private final class StubFileManager: FileManager {
    var existsResult = true
    var isDirectoryResult = true
    var isReadableResult = true
    var isWritableResult = true

    override func fileExists(atPath path: String, isDirectory: UnsafeMutablePointer<ObjCBool>?) -> Bool {
        isDirectory?.pointee = ObjCBool(isDirectoryResult)
        return existsResult
    }

    override func isReadableFile(atPath path: String) -> Bool {
        isReadableResult
    }

    override func isWritableFile(atPath path: String) -> Bool {
        isWritableResult
    }
}
