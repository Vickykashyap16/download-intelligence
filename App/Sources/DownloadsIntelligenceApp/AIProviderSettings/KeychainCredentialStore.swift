import Foundation
import Security

/// A narrow wrapper around macOS's `Security` framework generic-password
/// APIs, scoped to exactly one credential: the user's Anthropic API key
/// for AI Provider Settings (WP-GUI-12). Lives in `DownloadsIntelligenceApp`,
/// not `EngineBridge` — local OS credential storage is a GUI-only concern,
/// deliberately kept separate from the engine-subprocess boundary
/// `EngineBridge` owns, mirroring this project's existing "GUI log vs.
/// action log" separation discipline (`GUILogger` vs. the engine's own
/// action log).
///
/// **Why the Keychain, not `sources.yaml`/`UserDefaults`/a plaintext
/// file.** `GUI Architecture Specification.md` §16 (Security Architecture):
/// credential handling must use native secure storage, never plaintext.
/// The credential is written here and nowhere else in this app; it
/// reaches the engine subprocess only via
/// `EngineBridge.run(_:additionalEnvironment:)` (INFRA-01 / OD-GUI-6),
/// which never logs, persists, echoes, or exposes it (see that type's own
/// documentation for the structural leak-safety proof this store relies
/// on downstream).
///
/// **No third-party dependency.** `Security` is a system framework
/// available on every macOS target this package already requires (macOS
/// 13+, per `Package.swift`); adding a dependency for exactly one stored
/// value would be unjustified.
public struct KeychainCredentialStore: CredentialStore {
    public enum StoreError: Error, Equatable {
        /// A `Security` framework call returned an unexpected `OSStatus`
        /// — anything other than the specific, already-handled
        /// success/not-found outcomes each method below documents.
        case unexpectedStatus(OSStatus)
        /// The Keychain returned a value for this identifier that isn't
        /// valid UTF-8 text — not expected in practice (this store is the
        /// only writer for its identifiers, and always writes UTF-8), but
        /// surfaced as a distinct case rather than silently treated as "no
        /// credential" should it ever occur.
        case storedValueNotDecodable
    }

    /// Identifies exactly one Keychain item; both fields participate in
    /// every `Security` query below (`kSecAttrService`/`kSecAttrAccount`),
    /// so two `KeychainCredentialStore` instances constructed with
    /// different identifiers never see or affect each other's items — the
    /// mechanism `KeychainCredentialStoreTests` relies on to use a
    /// distinct, never-real identifier per test and never collide with
    /// anything a real run might store.
    public struct Identifier: Equatable, Sendable {
        public let service: String
        public let account: String

        public init(service: String, account: String) {
            self.service = service
            self.account = account
        }

        /// The one real identifier this app uses in production —
        /// `AIProviderSettingsViewModel`'s own default. Test code always
        /// constructs its own distinct `Identifier` instead of using this
        /// one.
        public static let anthropicAPIKey = Identifier(
            service: "com.downloadsintelligence.app.aiProvider",
            account: "anthropic-api-key"
        )
    }

    public let identifier: Identifier

    public init(identifier: Identifier = .anthropicAPIKey) {
        self.identifier = identifier
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: identifier.service,
            kSecAttrAccount as String: identifier.account
        ]
    }

    /// Stores `credential`, replacing any existing value for this
    /// identifier (add, then update-on-collision), so callers never have
    /// to know whether a previous value already exists.
    public func store(_ credential: String) throws {
        let data = Data(credential.utf8)

        var addQuery = baseQuery()
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock

        let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
        if addStatus == errSecSuccess {
            return
        }
        guard addStatus == errSecDuplicateItem else {
            throw StoreError.unexpectedStatus(addStatus)
        }

        let updateStatus = SecItemUpdate(baseQuery() as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        guard updateStatus == errSecSuccess else {
            throw StoreError.unexpectedStatus(updateStatus)
        }
    }

    /// Returns the stored credential, or `nil` if none exists yet — a
    /// missing credential is an expected, non-error state (e.g. the very
    /// first time this screen is ever shown), never thrown.
    public func read() throws -> String? {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess else {
            throw StoreError.unexpectedStatus(status)
        }
        guard let data = result as? Data, let credential = String(data: data, encoding: .utf8) else {
            throw StoreError.storedValueNotDecodable
        }
        return credential
    }

    /// Removes the stored credential. Deleting a nonexistent item is not
    /// an error — the end state ("no credential stored") is what every
    /// caller actually cares about, and is already reached.
    public func delete() throws {
        let status = SecItemDelete(baseQuery() as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw StoreError.unexpectedStatus(status)
        }
    }
}
