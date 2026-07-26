import Foundation

/// Checks whether a candidate folder path is usable as a Source or
/// Destination folder — existence, being a directory, and read/write
/// permission — via real, syscall-backed `FileManager` checks rather than
/// an assumption. Exists as its own collaborator so `EngineBridge.swift`
/// stays delegation-only, exactly as every other artifact-facing method on
/// the facade does (see that file's own header comment: "This type
/// contains no parsing, comparison, subprocess, or file-I/O logic of its
/// own").
///
/// Added for WP-GUI-00A (EngineBridge Folder Validation) — a small,
/// isolated addition to WP-GUI-00's frozen `EngineBridge` scope, made only
/// because WP-GUI-02 (Onboarding)'s Technical Notes require disabling
/// progress until a folder is "verified readable/writable via a real
/// Engine Bridge check," and no such capability existed anywhere in this
/// package or the underlying engine CLI (see
/// `Downloads Intelligence — UX Design/Open Dependencies.md`, OD-GUI-1).
///
/// This check is deliberately independent of the running engine process:
/// it inspects a path on the local filesystem the same way the engine's
/// own Python subprocess will ultimately see it (same machine, same user,
/// same permission bits), so no subprocess invocation is needed to
/// perform it faithfully.
public struct FolderAccessValidator: Sendable {
    private let fileManager: FileManager

    /// - Parameter fileManager: injectable so tests can exercise every
    ///   outcome (including permission-denied cases, which are awkward and
    ///   environment-dependent to reproduce with real `chmod` calls inside
    ///   a test suite) against a fake, deterministic implementation rather
    ///   than the real filesystem. Defaults to `.default` for real use.
    public init(fileManager: FileManager = .default) {
        self.fileManager = fileManager
    }

    public func validate(_ url: URL, requireWritable: Bool) -> FolderValidationOutcome {
        var isDirectoryObjC: ObjCBool = false
        guard fileManager.fileExists(atPath: url.path, isDirectory: &isDirectoryObjC) else {
            return .doesNotExist
        }
        guard isDirectoryObjC.boolValue else {
            return .notADirectory
        }
        guard fileManager.isReadableFile(atPath: url.path) else {
            return .notReadable
        }
        if requireWritable, !fileManager.isWritableFile(atPath: url.path) {
            return .notWritable
        }
        return .valid
    }
}
