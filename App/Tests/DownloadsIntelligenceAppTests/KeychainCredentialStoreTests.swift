import XCTest
@testable import DownloadsIntelligenceApp

/// Exercises `KeychainCredentialStore` against the *real* macOS Keychain —
/// deliberately, since a fake would only verify this type's own internal
/// bookkeeping, not that `Security`'s generic-password APIs are actually
/// being called correctly. Every test uses a distinct, never-real
/// `Identifier` (never `.anthropicAPIKey`, the one real production
/// identifier `AIProviderSettingsViewModel` actually uses) and deletes
/// whatever it stored in a teardown block, so these tests never leave real
/// state behind and never collide with anything a real run — or a second,
/// concurrently-running test — might store.
final class KeychainCredentialStoreTests: XCTestCase {

    private func makeStore(function: String = #function) -> KeychainCredentialStore {
        let identifier = KeychainCredentialStore.Identifier(
            service: "com.downloadsintelligence.app.tests",
            account: "test-\(function)-\(UUID().uuidString)"
        )
        let store = KeychainCredentialStore(identifier: identifier)
        addTeardownBlock {
            try? store.delete()
        }
        return store
    }

    func test_read_withNothingStored_returnsNil() throws {
        let store = makeStore()
        XCTAssertNil(try store.read())
    }

    func test_storeThenRead_roundTripsTheExactValue() throws {
        let store = makeStore()
        try store.store("sk-ant-test-credential-value")
        XCTAssertEqual(try store.read(), "sk-ant-test-credential-value")
    }

    func test_storeTwice_replacesRatherThanDuplicating() throws {
        let store = makeStore()
        try store.store("first-value")
        try store.store("second-value")
        XCTAssertEqual(try store.read(), "second-value")
    }

    func test_delete_removesTheStoredValue() throws {
        let store = makeStore()
        try store.store("to-be-deleted")
        try store.delete()
        XCTAssertNil(try store.read())
    }

    func test_delete_withNothingStored_doesNotThrow() throws {
        let store = makeStore()
        XCTAssertNoThrow(try store.delete())
    }

    func test_distinctIdentifiers_neverSeeEachOthersValue() throws {
        let storeA = makeStore(function: "A")
        let storeB = makeStore(function: "B")

        try storeA.store("value-for-a")

        XCTAssertEqual(try storeA.read(), "value-for-a")
        XCTAssertNil(try storeB.read())
    }

    // MARK: - CredentialStore protocol conformance (used by AIProviderSettingsViewModel)

    func test_conformsToCredentialStore() {
        let store = makeStore()
        let asProtocol: CredentialStore = store
        XCTAssertNoThrow(try asProtocol.read())
    }
}
