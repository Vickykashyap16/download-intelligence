import Foundation

/// The narrow credential-storage contract `AIProviderSettingsViewModel`
/// depends on, rather than depending on `KeychainCredentialStore`
/// concretely — mirrors `EngineBridge`'s own `GUILogger` protocol
/// (dependency injected for testability, one real implementation in
/// production, one fake in tests). `AIProviderSettingsViewModelTests` uses
/// an in-memory fake conforming to this protocol so those tests never
/// touch the real OS Keychain; `KeychainCredentialStoreTests` is the one
/// place that exercises the real `Security`-framework-backed
/// implementation directly.
public protocol CredentialStore: Sendable {
    /// Stores `credential`, replacing any existing value for this
    /// instance's identifier.
    func store(_ credential: String) throws

    /// Returns the stored credential, or `nil` if none exists yet — a
    /// missing credential is an expected, non-error state, never thrown.
    func read() throws -> String?

    /// Removes the stored credential. Deleting a nonexistent value is not
    /// an error.
    func delete() throws
}
