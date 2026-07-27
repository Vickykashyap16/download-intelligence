import Foundation
import EngineBridge

/// Translates a real `FolderValidationOutcome` (WP-GUI-00A) into the
/// plain-language, non-alarmist inline message First Run Experience's Error
/// state requires: "an unreadable/unwritable folder selection surfaces
/// inline per step... the checkmark becomes a plain-language inline
/// message" (`High-Fidelity UI Specification.md` §16, States). Permission
/// denial gets "the same inline, non-alarmist treatment as the general
/// folder-error case... the most likely real-world trigger for that error
/// state" (ibid.) — so `.notReadable`/`.notWritable` are worded as ordinary,
/// expected outcomes, not alarms.
///
/// This is the one place in this work package that switches on
/// `FolderValidationOutcome` directly, mirroring `ErrorPresentation`'s own
/// "the one place... that interprets `EngineBridgeError` cases into
/// user-facing language" precedent (WP-GUI-01) — every other type here only
/// ever sees the resulting message string.
public enum FolderValidationMessage {
    /// `nil` when the folder is valid (nothing to show — the checkmark
    /// itself is sufficient, per §16's content spec). Non-`nil` for every
    /// other outcome.
    public static func inline(for outcome: FolderValidationOutcome) -> String? {
        switch outcome {
        case .valid:
            return nil
        case .doesNotExist:
            return "This folder couldn't be found."
        case .notADirectory:
            return "That's not a folder."
        case .notReadable:
            return "This app doesn't have permission to read this folder."
        case .notWritable:
            return "This app doesn't have permission to save files to this folder."
        }
    }
}
