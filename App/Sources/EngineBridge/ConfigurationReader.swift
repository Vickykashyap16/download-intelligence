import Foundation
import Yams

/// Reads `src/config/sources.yaml` — the engine's real, hand-editable
/// configuration file — exactly as it exists on disk today.
///
/// Unlike `ActionLogReader` and `MetadataStoreReader`, a missing
/// configuration file is treated as a distinct, meaningful state rather
/// than "empty and fine": it means the engine has never been configured at
/// all (before its own `init` command has ever been run), which is exactly
/// the condition the product's First Run Experience screen exists to
/// detect and route around (`High-Fidelity UI Specification.md` §16). A
/// caller needs to be able to tell "not configured yet" apart from "an
/// empty history," so this reader throws `EngineBridgeError.artifactNotFound`
/// for a missing file rather than silently returning a default
/// configuration.
///
/// Similarly, because this is a single, small, holistically-meaningful
/// settings file rather than a large collection of independent records,
/// a parse failure here throws `EngineBridgeError.artifactUnreadable`
/// for the whole file rather than attempting the kind of per-element
/// partial recovery `MetadataStoreReader` performs — there is no
/// meaningful "the source list decoded but the destination root didn't"
/// partial state a caller could safely act on.
public struct ConfigurationReader: Sendable {
    private let locations: EngineArtifactLocations

    public init(locations: EngineArtifactLocations) {
        self.locations = locations
    }

    /// - Throws: `EngineBridgeError.artifactNotFound` if the configuration
    ///   file does not exist; `EngineBridgeError.artifactUnreadable` if it
    ///   exists but cannot be read from disk or is not valid YAML matching
    ///   the expected shape.
    public func read() throws -> EngineConfiguration {
        let url = locations.configurationFileURL

        guard FileManager.default.fileExists(atPath: url.path) else {
            throw EngineBridgeError.artifactNotFound(path: url.path)
        }

        let yamlText: String
        do {
            yamlText = try String(contentsOf: url, encoding: .utf8)
        } catch {
            throw EngineBridgeError.artifactUnreadable(path: url.path, reason: String(describing: error))
        }

        do {
            return try YAMLDecoder().decode(EngineConfiguration.self, from: yamlText)
        } catch {
            throw EngineBridgeError.artifactUnreadable(path: url.path, reason: String(describing: error))
        }
    }
}
