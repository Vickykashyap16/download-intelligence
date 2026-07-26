import Foundation

/// A strict `MAJOR.MINOR.PATCH` version triple, matching the exact format
/// `Release/VERSIONS.md` records today (`**Pipeline Version: 0.8.0**`) and
/// the format `src/cli.py`'s own `version` command reports.
///
/// This type is deliberately independent of any specific file or artifact
/// — it knows nothing about `VERSIONS.md`, paths, or the Engine Bridge. It
/// exists purely to parse and compare three-part version strings correctly
/// once, so `EngineVersionReader` (which does know about the file) and
/// `VersionCompatibilityChecker` (which does the range comparison) both
/// build on the same, single parsing and ordering implementation rather
/// than each re-deriving their own.
public struct SemanticVersion: Equatable, Comparable, Sendable, CustomStringConvertible {
    public let major: Int
    public let minor: Int
    public let patch: Int

    public init(major: Int, minor: Int, patch: Int) {
        self.major = major
        self.minor = minor
        self.patch = patch
    }

    public var description: String {
        "\(major).\(minor).\(patch)"
    }

    public static func < (lhs: SemanticVersion, rhs: SemanticVersion) -> Bool {
        (lhs.major, lhs.minor, lhs.patch) < (rhs.major, rhs.minor, rhs.patch)
    }

    /// Every way a candidate string can fail to be a valid
    /// `MAJOR.MINOR.PATCH` triple. Kept local to this type — not tied to
    /// `EngineBridgeError` — so `SemanticVersion` stays a small, reusable
    /// value type with no dependency on the artifact/file-reading concern;
    /// `EngineVersionReader` is what translates a `ParseError` into an
    /// `EngineBridgeError.artifactUnreadable` with real file-path context.
    public enum ParseError: Error, Equatable, Sendable {
        /// The string did not have exactly three dot-separated components.
        case wrongComponentCount(rawValue: String)
        /// One or more components was not a non-negative integer.
        case nonNumericComponent(rawValue: String)
    }

    /// Parses a strict `"MAJOR.MINOR.PATCH"` string — exactly three
    /// dot-separated, non-negative integer components, nothing more and
    /// nothing less. Deliberately strict rather than lenient (e.g. it does
    /// not accept a two-component `"0.8"` or a pre-release/build-metadata
    /// suffix like `"0.8.0-beta"`): the real, current `VERSIONS.md` format
    /// is exactly three plain integer components, and silently tolerating
    /// a shape it doesn't use today would be exactly the kind of
    /// unverified assumption about a hypothetical future format this
    /// package avoids elsewhere.
    public init(parsing rawValue: String) throws {
        let components = rawValue.split(separator: ".", omittingEmptySubsequences: false)
        guard components.count == 3 else {
            throw ParseError.wrongComponentCount(rawValue: rawValue)
        }
        var parsedNumbers: [Int] = []
        for component in components {
            guard let number = Int(component), number >= 0 else {
                throw ParseError.nonNumericComponent(rawValue: rawValue)
            }
            parsedNumbers.append(number)
        }
        self.init(major: parsedNumbers[0], minor: parsedNumbers[1], patch: parsedNumbers[2])
    }
}
