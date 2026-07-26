import Foundation

/// Reads the engine's own reported version from `Release/VERSIONS.md`,
/// exactly as `src/cli.py`'s `_cmd_version()` reads it today: a line of the
/// exact form `**Pipeline Version: X.Y.Z**`, found via a
/// `startswith("**Pipeline Version:")` style check, not a full-file parse.
///
/// Per `Desktop Implementation Blueprint.md` §14, the GUI is required to
/// read "the engine's reported version (via the same information the CLI's
/// `version` command already exposes)" — this reader satisfies that by
/// reading the identical source file the CLI command itself reads from,
/// rather than invoking `EngineCommand.version` as a subprocess and parsing
/// its printed stdout. That choice follows WP-GUI-00's own Technical Notes
/// directly: "prefer re-reading the on-disk artifacts... over parsing
/// free-text stdout" wherever structured detail is needed — and a version
/// number that gates every other engine invocation is exactly that kind of
/// structured detail, not a case where free-text parsing is the only
/// option.
///
/// Not an actor, for the same reason as the other four artifact readers:
/// no mutable state, one synchronous file read per call.
public struct EngineVersionReader: Sendable {
    private let locations: EngineArtifactLocations

    /// The exact real prefix `src/cli.py`'s `_cmd_version()` itself checks
    /// for. Declared once, here, rather than repeated as a string literal
    /// anywhere else in this type.
    private static let versionLinePrefix = "**Pipeline Version:"

    public init(locations: EngineArtifactLocations) {
        self.locations = locations
    }

    /// - Throws: `EngineBridgeError.artifactNotFound` if `VERSIONS.md`
    ///   does not exist — this is "missing version information": the GUI
    ///   cannot verify compatibility at all and must not proceed as if it
    ///   had, per `Desktop Implementation Blueprint.md` §14's "does not
    ///   attempt to proceed as if everything will work."
    ///   `EngineBridgeError.artifactUnreadable` if the file exists but
    ///   contains no line matching the expected `**Pipeline Version:`
    ///   prefix, or the version segment on that line is not a valid
    ///   `MAJOR.MINOR.PATCH` triple — this is "malformed version
    ///   information," kept distinct from a missing file because the two
    ///   call for different explanations in the eventual Error State
    ///   (`Desktop Implementation Blueprint.md` §8's screen-level-error
    ///   distinction applied here to what caused the failure).
    public func read() throws -> SemanticVersion {
        let url = locations.versionsFileURL

        guard FileManager.default.fileExists(atPath: url.path) else {
            throw EngineBridgeError.artifactNotFound(path: url.path)
        }

        let contents: String
        do {
            contents = try String(contentsOf: url, encoding: .utf8)
        } catch {
            throw EngineBridgeError.artifactUnreadable(path: url.path, reason: String(describing: error))
        }

        guard let versionLine = contents
            .split(separator: "\n", omittingEmptySubsequences: false)
            .first(where: { $0.hasPrefix(Self.versionLinePrefix) })
        else {
            throw EngineBridgeError.artifactUnreadable(
                path: url.path,
                reason: "no line beginning with \"\(Self.versionLinePrefix)\" was found"
            )
        }

        // "**Pipeline Version: 0.8.0**" -> "0.8.0": drop the matched
        // prefix, then trim whitespace and any trailing Markdown bold
        // markers, exactly the substring `_cmd_version()` itself would
        // display to a terminal user. Converted to a plain `String`
        // immediately (rather than continuing to operate on the
        // `Substring` from `split`) so every subsequent String API used
        // here is unambiguously available.
        var remainder = String(versionLine.dropFirst(Self.versionLinePrefix.count))
        remainder = remainder.trimmingCharacters(in: .whitespaces)
        let versionString = remainder.hasSuffix("**") ? String(remainder.dropLast(2)) : remainder

        do {
            return try SemanticVersion(parsing: versionString)
        } catch {
            throw EngineBridgeError.artifactUnreadable(
                path: url.path,
                reason: "the version value \"\(versionString)\" is not a valid MAJOR.MINOR.PATCH triple (\(error))"
            )
        }
    }
}
