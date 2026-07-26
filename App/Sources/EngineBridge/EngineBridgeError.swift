import Foundation

/// Every error this package can throw. Deliberately exhaustive and specific —
/// no case here means "something went wrong" without saying what; that
/// distinction is what lets `Desktop Implementation Blueprint.md` §8's
/// screen-level-vs-inline error classification actually be implemented later
/// on top of this type, rather than re-deriving it from a string message.
public enum EngineBridgeError: Error, Equatable, Sendable {
    /// Refused before a subprocess was even spawned, per
    /// `EngineCommand.requiresInteractiveInput`'s documentation: this
    /// command reads from stdin in the real CLI, and no caller passed
    /// `allowInteractive: true` to `ProcessRunner.run(_:allowInteractive:)`.
    case commandRequiresInteractiveInput(EngineCommand)

    /// `EngineMutationGuard` refused this call because another mutating
    /// command is already in flight (`GUI Architecture Specification.md`
    /// §9, `Desktop Implementation Blueprint.md` §7's single-mutation-slot
    /// rule).
    case anotherMutatingOperationInProgress

    /// `Process.run()` itself failed — the executable couldn't be spawned at
    /// all (e.g. `/usr/bin/env` missing, or a permissions problem). This is
    /// distinct from the *engine* reporting a failure (a real invocation
    /// that ran and exited non-zero) — this is the invocation never having
    /// happened at all. The associated string is `Process.run()`'s own
    /// thrown error, described, and is intentionally opaque here — this
    /// package never invents a friendlier reason it cannot actually verify
    /// (`GUI Architecture Specification.md` §12's "never invent or infer
    /// beyond what the engine's own output actually states," applied here
    /// one layer below where the engine even gets a chance to say anything).
    case failedToLaunchProcess(String)

    /// The configured project-root directory (the checkout containing
    /// `src/`) doesn't exist on disk. Distinguished from a Python-missing or
    /// engine-unavailable condition (`Desktop Implementation Blueprint.md`
    /// §8): this means the Engine Bridge itself was configured with a path
    /// that isn't there, before any process was even attempted.
    case projectRootNotFound(String)

    /// An artifact reader (`ConfigurationReader`, `ActionLogReader`,
    /// `MetadataStoreReader`, `ReportsReader`, `VersionReader`) found a file
    /// that exists but could not be parsed into the expected shape. Carries
    /// the file path and a human-readable reason — never a raw, unparsed
    /// exception object, so this stays `Equatable`/`Sendable` and testable.
    case artifactUnreadable(path: String, reason: String)

    /// An artifact reader found no file at all where one was expected to
    /// have been created by prior engine activity. Distinguished from
    /// `artifactUnreadable`: a missing file is frequently a normal, empty-
    /// state condition (e.g. no action log yet on a fresh install) — callers
    /// decide whether that's an error or an expected empty state for their
    /// context; this case exists so they can tell the two apart.
    case artifactNotFound(path: String)

    /// `VersionCompatibilityChecker` rejected the engine's reported version
    /// because it is older than the GUI's configured minimum supported
    /// version (`Desktop Implementation Blueprint.md` §14).
    case engineVersionTooOld(engineVersion: SemanticVersion, minimumSupportedVersion: SemanticVersion)

    /// `VersionCompatibilityChecker` rejected the engine's reported version
    /// because it is newer than the GUI's configured maximum supported
    /// version (`Desktop Implementation Blueprint.md` §14) — the GUI does
    /// not assume forward compatibility with an engine version it was never
    /// tested against.
    case engineVersionTooNew(engineVersion: SemanticVersion, maximumSupportedVersion: SemanticVersion)
}

extension EngineBridgeError: CustomStringConvertible {
    public var description: String {
        switch self {
        case .commandRequiresInteractiveInput(let command):
            return "The command \(command) requires an attached interactive " +
                "terminal (stdin) and was refused. Pass allowInteractive: true " +
                "only if a real terminal is attached."
        case .anotherMutatingOperationInProgress:
            return "Another engine-mutating operation is already in progress."
        case .failedToLaunchProcess(let reason):
            return "Could not launch the engine process: \(reason)"
        case .projectRootNotFound(let path):
            return "The configured project root does not exist: \(path)"
        case .artifactUnreadable(let path, let reason):
            return "Could not read \(path): \(reason)"
        case .artifactNotFound(let path):
            return "No file found at \(path)"
        case .engineVersionTooOld(let engineVersion, let minimumSupportedVersion):
            return "The installed engine (version \(engineVersion)) is older than this application " +
                "supports (minimum \(minimumSupportedVersion)). Please update the engine."
        case .engineVersionTooNew(let engineVersion, let maximumSupportedVersion):
            return "The installed engine (version \(engineVersion)) is newer than this application " +
                "has been tested with (maximum \(maximumSupportedVersion)). Please update this application."
        }
    }
}
