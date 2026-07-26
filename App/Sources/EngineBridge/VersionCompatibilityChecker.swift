import Foundation

/// The three possible outcomes of comparing a candidate engine version
/// against a supported range. Kept as a plain, exhaustively-testable value
/// type separate from the throwing `check(_:)` convenience below it, so
/// every branch of the comparison logic can be exercised directly in a
/// unit test without needing to unwrap a thrown error each time.
public enum VersionCompatibilityResult: Equatable, Sendable {
    case compatible
    case tooOld
    case tooNew
}

/// Implements the version-compatibility check named in WP-GUI-00's Scope
/// and specified in `Desktop Implementation Blueprint.md` §14: before
/// reading artifacts or executing any engine command, the GUI checks the
/// engine's reported version "against a known-compatible range the GUI
/// itself was built and tested against," and if it falls outside that
/// range, routes to an incompatibility error rather than proceeding as if
/// everything will work.
///
/// **On the specific range values:** neither §14 nor WP-GUI-00 itself
/// names concrete minimum/maximum version numbers — §14's own wording
/// ("a known-compatible range the GUI itself was built and tested
/// against") explicitly describes this as a fact established by whichever
/// concrete GUI build exists, not a number this design phase fixed in
/// advance. Baking a specific, guessed range into this type would be
/// exactly the kind of unverified assumption this project's engineering
/// standard rules out. `VersionCompatibilityChecker` is therefore built as
/// a general, fully-configurable mechanism — the range is supplied by
/// whoever constructs it — and the concrete values used by the running
/// application are a release-configuration decision for the `EngineBridge`
/// facade (WP-GUI-00's remaining deliverable, tracked separately) to make,
/// not something invented here.
public struct VersionCompatibilityChecker: Sendable {
    public let minimumSupportedVersion: SemanticVersion
    public let maximumSupportedVersion: SemanticVersion

    /// - Precondition: `minimumSupportedVersion <= maximumSupportedVersion`.
    ///   A range where the minimum exceeds the maximum could never accept
    ///   any version at all, which is certainly a configuration mistake,
    ///   not a legitimate policy — caught here, at construction, rather
    ///   than surfacing later as every single version being rejected for
    ///   no discoverable reason.
    public init(minimumSupportedVersion: SemanticVersion, maximumSupportedVersion: SemanticVersion) {
        precondition(
            minimumSupportedVersion <= maximumSupportedVersion,
            "minimumSupportedVersion (\(minimumSupportedVersion)) must not exceed " +
                "maximumSupportedVersion (\(maximumSupportedVersion))"
        )
        self.minimumSupportedVersion = minimumSupportedVersion
        self.maximumSupportedVersion = maximumSupportedVersion
    }

    /// Pure comparison against the configured range — no throwing, so
    /// every outcome can be asserted directly.
    public func evaluate(_ engineVersion: SemanticVersion) -> VersionCompatibilityResult {
        if engineVersion < minimumSupportedVersion {
            return .tooOld
        }
        if engineVersion > maximumSupportedVersion {
            return .tooNew
        }
        return .compatible
    }

    /// The call-site convenience a startup gate actually wants: succeeds
    /// silently for a compatible version, throws a specific, typed error
    /// otherwise. Built directly on `evaluate(_:)` rather than
    /// re-implementing the comparison, so there is exactly one place the
    /// range logic itself lives.
    ///
    /// - Throws: `EngineBridgeError.engineVersionTooOld` or
    ///   `EngineBridgeError.engineVersionTooNew`, each carrying the
    ///   offending version and the configured range, so a caller can
    ///   render `Desktop Implementation Blueprint.md` §14's plain-language
    ///   incompatibility explanation without re-deriving which direction
    ///   the mismatch went.
    public func check(_ engineVersion: SemanticVersion) throws {
        switch evaluate(engineVersion) {
        case .compatible:
            return
        case .tooOld:
            throw EngineBridgeError.engineVersionTooOld(
                engineVersion: engineVersion,
                minimumSupportedVersion: minimumSupportedVersion
            )
        case .tooNew:
            throw EngineBridgeError.engineVersionTooNew(
                engineVersion: engineVersion,
                maximumSupportedVersion: maximumSupportedVersion
            )
        }
    }
}
