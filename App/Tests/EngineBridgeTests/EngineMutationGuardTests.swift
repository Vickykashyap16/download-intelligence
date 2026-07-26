import XCTest
@testable import EngineBridge

/// Verifies `EngineMutationGuard` against WP-GUI-00's Acceptance Criteria:
/// "the concurrency guard correctly refuses a second mutating invocation
/// while one is in flight and correctly allows unlimited concurrent
/// read-only invocations."
///
/// The concurrency tests here are integration tests in the sense that they
/// spawn real subprocesses (via `ProcessRunner` against the same fixture
/// engine `ProcessRunnerTests` uses) and rely on real, observable timing —
/// not simulated actor behavior — to prove the guard's serialization is
/// correct under genuine concurrent access, not just correct on paper.
final class EngineMutationGuardTests: XCTestCase {

    private func makeRunner() throws -> ProcessRunner {
        guard let fixturesRoot = Bundle.module.url(forResource: "Fixtures", withExtension: nil) else {
            throw XCTSkip("Fixtures resource bundle not found — check Package.swift test resources.")
        }
        let projectRoot = fixturesRoot.appendingPathComponent("FakeEngineProject")
        return ProcessRunner(configuration: .init(projectRootURL: projectRoot))
    }

    /// Polls `guard.isMutationInFlight` until it becomes `true` or `timeout`
    /// elapses. Used instead of a fixed `Task.sleep` before firing a second,
    /// concurrent mutating call, so the test is not dependent on guessing
    /// how long process startup takes on the machine running it.
    private func waitUntilMutationInFlight(
        _ guardActor: EngineMutationGuard,
        timeout: TimeInterval = 5.0
    ) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if await guardActor.isMutationInFlight {
                return true
            }
            try? await Task.sleep(nanoseconds: 5_000_000) // 5ms
        }
        return false
    }

    // MARK: - Read-only pass-through

    func test_readOnlyCommand_neverTouchesTheSlot() async throws {
        let runner = try makeRunner()
        let guardActor = EngineMutationGuard()

        let before = await guardActor.isMutationInFlight
        let result = try await guardActor.run(.status, via: runner)
        let after = await guardActor.isMutationInFlight

        XCTAssertFalse(before)
        XCTAssertFalse(after)
        XCTAssertTrue(result.succeeded)
    }

    func test_manyConcurrentReadOnlyCommands_allSucceed() async throws {
        let runner = try makeRunner()
        let guardActor = EngineMutationGuard()

        try await withThrowingTaskGroup(of: Bool.self) { group in
            for _ in 0..<20 {
                group.addTask {
                    let result = try await guardActor.run(.status, via: runner)
                    return result.succeeded
                }
            }
            for try await succeeded in group {
                XCTAssertTrue(succeeded)
            }
        }
    }

    // MARK: - Mutating command: acquire and release

    func test_mutatingCommand_acquiresAndReleasesSlot() async throws {
        let runner = try makeRunner()
        let guardActor = EngineMutationGuard()

        let before = await guardActor.isMutationInFlight
        let result = try await guardActor.run(.provider(.disable), via: runner)
        let after = await guardActor.isMutationInFlight

        XCTAssertFalse(before)
        XCTAssertTrue(result.succeeded)
        XCTAssertFalse(after, "the slot must be released once the mutating command completes")
    }

    func test_sequentialMutatingCommands_bothSucceed() async throws {
        let runner = try makeRunner()
        let guardActor = EngineMutationGuard()

        let first = try await guardActor.run(.provider(.disable), via: runner)
        let second = try await guardActor.run(.provider(.disable), via: runner)

        XCTAssertTrue(first.succeeded)
        XCTAssertTrue(second.succeeded)
    }

    // MARK: - The core rule: a second concurrent mutation is refused, not queued

    func test_secondConcurrentMutatingCommand_isRefusedWhileFirstIsInFlight() async throws {
        let runner = try makeRunner()
        let guardActor = EngineMutationGuard()

        // `config` sleeps ~0.3s in the fixture before succeeding, giving a
        // real, observable window in which a second mutating call must be
        // rejected rather than silently waiting its turn.
        async let firstResult = guardActor.run(.config(setSource: "/tmp/fixture"), via: runner)

        let acquired = await waitUntilMutationInFlight(guardActor)
        XCTAssertTrue(acquired, "expected the first mutating call to occupy the slot")

        do {
            _ = try await guardActor.run(.provider(.disable), via: runner)
            XCTFail("expected the second, concurrent mutating call to be refused")
        } catch EngineBridgeError.anotherMutatingOperationInProgress {
            // expected — refused immediately, not queued
        }

        let first = try await firstResult
        XCTAssertTrue(first.succeeded, "the first, legitimately-in-flight call must still complete normally")
    }

    func test_afterFirstMutationReleases_aNewMutatingCommandSucceeds() async throws {
        let runner = try makeRunner()
        let guardActor = EngineMutationGuard()

        let first = try await guardActor.run(.config(setSource: "/tmp/fixture"), via: runner)
        XCTAssertTrue(first.succeeded)

        // The slot must be free again now that the first call has returned.
        let second = try await guardActor.run(.provider(.disable), via: runner)
        XCTAssertTrue(second.succeeded)
    }

    // MARK: - Read-only commands are never blocked by an in-flight mutation

    func test_readOnlyCommands_proceedUnblockedWhileMutationIsInFlight() async throws {
        let runner = try makeRunner()
        let guardActor = EngineMutationGuard()

        async let mutation = guardActor.run(.config(setSource: "/tmp/fixture"), via: runner)
        let acquired = await waitUntilMutationInFlight(guardActor)
        XCTAssertTrue(acquired)

        // These must all complete promptly and successfully even though a
        // mutating command currently holds the slot — read-only commands
        // are never serialized against a mutation in progress.
        try await withThrowingTaskGroup(of: Bool.self) { group in
            for _ in 0..<10 {
                group.addTask {
                    let result = try await guardActor.run(.status, via: runner)
                    return result.succeeded
                }
            }
            for try await succeeded in group {
                XCTAssertTrue(succeeded)
            }
        }

        _ = try await mutation
    }

    // MARK: - The slot is released even when the underlying call throws

    func test_slotIsReleasedEvenWhenTheUnderlyingCommandIsRefused() async throws {
        let runner = try makeRunner()
        let guardActor = EngineMutationGuard()

        // .initialSetup is classified as mutating, and is refused by
        // ProcessRunner itself (it requires interactive input and
        // allowInteractive defaults to false) before any subprocess is
        // spawned. This must not leave the mutation slot permanently held.
        do {
            _ = try await guardActor.run(.initialSetup, via: runner)
            XCTFail("expected commandRequiresInteractiveInput to be thrown")
        } catch EngineBridgeError.commandRequiresInteractiveInput {
            // expected
        }

        let stuck = await guardActor.isMutationInFlight
        XCTAssertFalse(stuck, "a refused mutating call must not leave the slot occupied")

        // Proven by demonstration: a subsequent, legitimate mutating call
        // must still be able to acquire the slot.
        let result = try await guardActor.run(.provider(.disable), via: runner)
        XCTAssertTrue(result.succeeded)
    }
}
