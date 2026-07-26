import Foundation

/// The result of `EngineBridge.validateFolder(at:requireWritable:)` — a
/// structured outcome (never free-text, never a raw thrown error) so GUI
/// code can react to the specific reason a folder can't be used without
/// parsing a message, in the same "never invent or infer beyond what was
/// actually determined" spirit as `EngineBridgeError`.
///
/// This is deliberately its own type rather than an `EngineBridgeError`
/// case: folder validation is not a failure the way an unreadable
/// artifact or an incompatible engine version is — an invalid folder is
/// an entirely expected, common outcome while a user is still choosing
/// one (e.g. during WP-GUI-02's Onboarding flow), not an exceptional
/// condition. `EngineBridge.validateFolder(at:requireWritable:)` returns
/// this value rather than throwing.
public enum FolderValidationOutcome: Equatable, Sendable {
    /// The path exists, is a directory, is readable, and — if
    /// `requireWritable` was `true` when this outcome was produced — is
    /// also writable.
    case valid

    /// Nothing exists at this path.
    case doesNotExist

    /// Something exists at this path, but it is not a directory (e.g. a
    /// regular file was selected instead of a folder).
    case notADirectory

    /// The path is a directory that exists but cannot be read.
    case notReadable

    /// The path is a readable directory but cannot be written to. Only
    /// ever produced when `requireWritable` was `true` — never returned
    /// when the caller didn't ask for a writability check.
    case notWritable

    /// Convenience for call sites that only need a yes/no answer (e.g.
    /// disabling a "Continue" button) without branching on the specific
    /// reason.
    public var isValid: Bool {
        self == .valid
    }
}
