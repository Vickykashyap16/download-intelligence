import Foundation

/// The logging seam `ProcessRunner` (and, later, the artifact readers and
/// `EngineBridge` facade) write through. Declared as a protocol here, in the
/// same file group as the type that first needs it, so `ProcessRunner`
/// compiles and is testable in isolation (a test can inject a no-op or
/// recording logger) without depending on wherever the real, concrete GUI
/// log file writer ends up being implemented.
///
/// `GUI Architecture Specification.md` §15 is explicit that the GUI's own
/// log is a separate stream from the engine's `Runtime/Logs/action_log.jsonl`
/// and the two are never merged: this protocol exists to give the GUI side
/// of that boundary a concrete seam. The concrete file-backed implementation
/// (what gets written, where, and in what format) is this same work
/// package's remaining "Logging" deliverable and is completed alongside the
/// version-compatibility check, not here — `ProcessRunner` only needs to
/// know that *something* conforming to this protocol can be handed a
/// finished `CommandResult`.
public protocol GUILogger: Sendable {
    /// Called once per completed `ProcessRunner.run(_:)` invocation, after
    /// the process has exited and its output has been fully captured.
    /// Implementations decide what, if anything, to persist — this
    /// protocol makes no assumption about log format, destination, or
    /// retention.
    func log(result: CommandResult) async
}
