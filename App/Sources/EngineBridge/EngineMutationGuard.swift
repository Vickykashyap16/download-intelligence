import Foundation

/// Enforces the single-engine-mutation-slot rule: at most one
/// engine-mutating command runs at a time; any number of read-only
/// commands may run concurrently, including while a mutation is in
/// flight.
///
/// This is the concurrency guard called for in `GUI Architecture
/// Specification.md` §9 ("Background Scan Engine" — single scan at a time)
/// and `Desktop Implementation Blueprint.md` §7 ("Background Operations")
/// and is exactly, and only, the deliverable named in
/// `GUI Engineering Work Packages.md`'s WP-GUI-00 Scope: "the
/// single-engine-mutation-slot concurrency guard." It answers one question
/// — "is it safe to start this mutating command right now?" — and answers
/// it by refusing outright, never by making the caller wait. WP-GUI-00's
/// Acceptance Criteria are explicit that the guard "correctly refuses a
/// second mutating invocation while one is in flight," not that it queues
/// or defers it; a rejected caller (a screen, later) is expected to show
/// the user that the engine is busy, not to silently block.
///
/// ## Why this is safe under concurrency
///
/// `EngineMutationGuard` is a Swift `actor`. Every call into it — from
/// however many concurrent `Task`s — is processed one at a time by the
/// actor's own serial executor; no two calls can ever execute their bodies
/// simultaneously. The one property that matters for correctness is that
/// the read-then-write of `mutationInFlight` inside `run(_:via:allowInteractive:)`
/// contains no `await` between the check and the set: an actor only yields
/// its exclusive access at a suspension point, so as long as that
/// check-and-set is straight-line, synchronous code, it is impossible for a
/// second call to observe `mutationInFlight` as `false` while a first call
/// is between checking it and setting it to `true`. This is what actually
/// rules out the race the WP-GUI-00 Risks section warns about ("the
/// concurrency guard having a race condition if two invocations are
/// attempted in rapid succession") — not a lock or a semaphore, which would
/// introduce exactly the kind of ad hoc, hand-verified synchronization the
/// same Risks section recommends avoiding in favor of "a single, serialized
/// invocation queue." An actor's mailbox *is* that serialized queue.
///
/// The long-running `await runner.run(...)` call — the actual subprocess
/// invocation — happens only *after* the flag has already been set to
/// `true` and only while holding it, and the flag is guaranteed to be
/// cleared via `defer` on every exit path, including every thrown error,
/// so a failed or refused invocation can never leave the slot permanently
/// occupied.
public actor EngineMutationGuard {
    private var mutationInFlight = false

    public init() {}

    /// Whether a mutating command is currently occupying the single
    /// mutation slot. Exposed for diagnostics and tests; ordinary callers
    /// should not need to check this before calling `run` — `run` already
    /// performs the check atomically and reports the outcome via its
    /// thrown error.
    public var isMutationInFlight: Bool {
        mutationInFlight
    }

    /// Runs `command` through `runner`, enforcing the single-mutation-slot
    /// rule for commands where `command.isMutating` is `true`.
    ///
    /// Read-only commands (`command.isMutating == false`) are passed
    /// straight through to `runner` without ever consulting or touching
    /// the mutation slot — they are never rejected, delayed, or serialized
    /// against each other or against an in-flight mutation, satisfying
    /// WP-GUI-00's Acceptance Criteria that the guard "correctly allows
    /// unlimited concurrent read-only invocations."
    ///
    /// - Parameters:
    ///   - command: The engine operation to run.
    ///   - runner: The `ProcessRunner` that actually performs the
    ///     invocation. Injected rather than owned by the guard, so the
    ///     guard's sequencing logic and `ProcessRunner`'s subprocess
    ///     mechanics remain two independently testable responsibilities,
    ///     per this work package's "no duplicated logic" / single-
    ///     responsibility engineering standard.
    ///   - allowInteractive: Forwarded unchanged to `runner.run(_:allowInteractive:)`.
    /// - Throws: `EngineBridgeError.anotherMutatingOperationInProgress` if
    ///   `command.isMutating` is `true` and a different mutating command is
    ///   already occupying the slot. Otherwise, propagates whatever
    ///   `runner.run(_:allowInteractive:)` itself throws.
    public func run(
        _ command: EngineCommand,
        via runner: ProcessRunner,
        allowInteractive: Bool = false
    ) async throws -> CommandResult {
        guard command.isMutating else {
            return try await runner.run(command, allowInteractive: allowInteractive)
        }

        guard !mutationInFlight else {
            throw EngineBridgeError.anotherMutatingOperationInProgress
        }
        mutationInFlight = true
        defer { mutationInFlight = false }

        return try await runner.run(command, allowInteractive: allowInteractive)
    }
}
