import Foundation

/// The single public entry point this package exposes. Every other type in
/// `EngineBridge` (`ProcessRunner`, `EngineMutationGuard`,
/// `ConfigurationReader`, `MetadataStoreReader`, `ActionLogReader`,
/// `ReportsReader`, `EngineVersionReader`, `VersionCompatibilityChecker`,
/// `FileGUILogger`, `FolderAccessValidator`) is an internal collaborator
/// this facade coordinates — per WP-GUI-00's own framing ("Build and
/// independently verify the subprocess-invocation and artifact-reading
/// layer the entire GUI depends on"), no future screen or view is meant to
/// reach past this type to use any of those collaborators directly. That
/// boundary is enforced by access control here: every collaborator is a
/// `private let`, reachable only through this type's own methods.
/// (`FolderAccessValidator` was added by WP-GUI-00A, a small isolated
/// extension of this same facade — see `validateFolder(at:requireWritable:)`
/// below for why.)
///
/// This type contains **no parsing, comparison, subprocess, or file-I/O
/// logic of its own.** Every one of its methods does exactly two things:
/// (1) run the version-compatibility gate, (2) delegate to the one
/// collaborator that actually does the work, optionally recording the
/// outcome to the GUI log. Search this file for anything resembling
/// business logic and it should not be found — that would mean logic had
/// been duplicated out of a component already built and tested in
/// WP-GUI-00's earlier tasks, which is exactly what this task's own
/// requirements rule out.
///
/// **The version gate.** `Desktop Implementation Blueprint.md` §14: "At
/// startup, during the Engine Bridge readiness phase, the GUI reads the
/// engine's reported version... and checks it against a known-compatible
/// range... If the engine's version falls outside that range, the GUI does
/// not attempt to proceed as if everything will work." Every method below
/// that runs a command or reads an artifact calls `verifyEngineIsCompatible()`
/// as its very first action, before touching `processRunner`,
/// `mutationGuard`, or any reader — an incompatible engine is detected
/// before any of those collaborators are given a chance to run against
/// data or a process they may not actually understand.
public actor EngineBridge {
    /// Everything needed to construct a fully-wired `EngineBridge`.
    ///
    /// `minimumSupportedEngineVersion`/`maximumSupportedEngineVersion` are
    /// deliberately **not** defaulted. Per `VersionCompatibilityChecker`'s
    /// own documentation (WP-GUI-00, Task #580), neither
    /// `Desktop Implementation Blueprint.md` §14 nor WP-GUI-00 itself fixes
    /// real supported-version numbers — that is a release-configuration
    /// decision for whoever assembles the running application, made once,
    /// deliberately, at that point. Defaulting these here would silently
    /// make that decision now, for every future caller, which is exactly
    /// the kind of unverified assumption this project's engineering
    /// standard prohibits.
    public struct Configuration: Sendable {
        public let projectRootURL: URL
        public let pythonInvocation: [String]
        public let minimumSupportedEngineVersion: SemanticVersion
        public let maximumSupportedEngineVersion: SemanticVersion
        public let guiLogDirectoryURL: URL
        public let guiLogFilename: String
        public let guiLogMaximumFileSizeBytes: Int
        public let guiLogMaximumRotatedFileCount: Int

        public init(
            projectRootURL: URL,
            pythonInvocation: [String] = ["python3"],
            minimumSupportedEngineVersion: SemanticVersion,
            maximumSupportedEngineVersion: SemanticVersion,
            guiLogDirectoryURL: URL,
            guiLogFilename: String = "gui.log",
            guiLogMaximumFileSizeBytes: Int = 5 * 1024 * 1024,
            guiLogMaximumRotatedFileCount: Int = 5
        ) {
            self.projectRootURL = projectRootURL
            self.pythonInvocation = pythonInvocation
            self.minimumSupportedEngineVersion = minimumSupportedEngineVersion
            self.maximumSupportedEngineVersion = maximumSupportedEngineVersion
            self.guiLogDirectoryURL = guiLogDirectoryURL
            self.guiLogFilename = guiLogFilename
            self.guiLogMaximumFileSizeBytes = guiLogMaximumFileSizeBytes
            self.guiLogMaximumRotatedFileCount = guiLogMaximumRotatedFileCount
        }
    }

    private let processRunner: ProcessRunner
    private let mutationGuard: EngineMutationGuard
    private let configurationReader: ConfigurationReader
    private let metadataStoreReader: MetadataStoreReader
    private let actionLogReader: ActionLogReader
    private let reportsReader: ReportsReader
    private let versionReader: EngineVersionReader
    private let versionChecker: VersionCompatibilityChecker
    private let logger: FileGUILogger
    private let folderAccessValidator: FolderAccessValidator

    public init(configuration: Configuration) {
        let locations = EngineArtifactLocations(projectRootURL: configuration.projectRootURL)
        let guiLogger = FileGUILogger(configuration: .init(
            logDirectoryURL: configuration.guiLogDirectoryURL,
            currentLogFilename: configuration.guiLogFilename,
            maximumLogFileSizeBytes: configuration.guiLogMaximumFileSizeBytes,
            maximumRotatedFileCount: configuration.guiLogMaximumRotatedFileCount
        ))

        self.logger = guiLogger
        // The GUI logger is handed to ProcessRunner here, once — every
        // CommandResult ProcessRunner ever produces is logged through this
        // same instance automatically (ProcessRunner.run's own
        // `await logger?.log(result:)` call). EngineBridge never logs a
        // CommandResult itself; doing so would duplicate logic ProcessRunner
        // already owns.
        self.processRunner = ProcessRunner(
            configuration: .init(
                projectRootURL: configuration.projectRootURL,
                pythonInvocation: configuration.pythonInvocation
            ),
            logger: guiLogger
        )
        self.mutationGuard = EngineMutationGuard()
        self.configurationReader = ConfigurationReader(locations: locations)
        self.metadataStoreReader = MetadataStoreReader(locations: locations)
        self.actionLogReader = ActionLogReader(locations: locations)
        self.reportsReader = ReportsReader(locations: locations)
        self.versionReader = EngineVersionReader(locations: locations)
        self.versionChecker = VersionCompatibilityChecker(
            minimumSupportedVersion: configuration.minimumSupportedEngineVersion,
            maximumSupportedVersion: configuration.maximumSupportedEngineVersion
        )
        self.folderAccessValidator = FolderAccessValidator()
    }

    // MARK: - Version readiness

    /// Performs the startup readiness check from `Desktop Implementation
    /// Blueprint.md` §14 as its own, explicit operation — reads the
    /// engine's real version and validates it against the configured
    /// range, returning the version if compatible. Every other method on
    /// this facade performs this exact same check internally before doing
    /// its own work (see each method's implementation), so a caller is
    /// never required to call this first — it exists so application
    /// startup can perform the check as its own explicit lifecycle step,
    /// per §14's "during the Engine Bridge readiness phase," without that
    /// step being an incidental side effect of some other call.
    ///
    /// - Throws: `EngineBridgeError.artifactNotFound` /
    ///   `.artifactUnreadable` if the version cannot be determined at all
    ///   (from `EngineVersionReader`), or `.engineVersionTooOld` /
    ///   `.engineVersionTooNew` if it is outside the configured range
    ///   (from `VersionCompatibilityChecker`).
    @discardableResult
    public func verifyEngineIsCompatible() async throws -> SemanticVersion {
        let version: SemanticVersion
        do {
            version = try versionReader.read()
        } catch {
            await logger.log("Engine version could not be determined: \(error)", level: .error)
            throw error
        }
        do {
            try versionChecker.check(version)
        } catch {
            await logger.log("Engine version \(version) is not compatible: \(error)", level: .error)
            throw error
        }
        return version
    }

    /// Reads the engine's reported version **without** validating it
    /// against the supported range. Exists so a caller that has just
    /// received an `.engineVersionTooOld`/`.engineVersionTooNew` error can
    /// still display *which* version is actually installed in the
    /// resulting Error State (`Desktop Implementation Blueprint.md` §14's
    /// "plain-language explanation... with a resolution action") — the
    /// gated methods below cannot serve that purpose themselves, since
    /// they refuse to proceed at all once the version is known to be
    /// incompatible.
    public func currentEngineVersion() throws -> SemanticVersion {
        try versionReader.read()
    }

    // MARK: - Folder validation

    /// Checks whether `url` is usable as a Source or Destination folder —
    /// exists, is a directory, and has read (and, if `requireWritable` is
    /// `true`, write) permission — via a real, syscall-backed check
    /// (`FolderAccessValidator`), never assumed. Added by WP-GUI-00A
    /// (EngineBridge Folder Validation) specifically because WP-GUI-02
    /// (Onboarding)'s Technical Notes require disabling its "Continue"/
    /// "Scan now" action until the folder the user selected is "verified
    /// readable/writable via a real Engine Bridge check" — a capability
    /// that did not exist anywhere in this package or the underlying
    /// engine CLI before this addition (see
    /// `Downloads Intelligence — UX Design/Open Dependencies.md`,
    /// OD-GUI-1).
    ///
    /// Deliberately **not** run behind `verifyEngineIsCompatible()`,
    /// unlike every other method on this facade: this check inspects a
    /// local filesystem path directly, never invoking the engine
    /// subprocess or reading one of its artifacts, so requiring engine
    /// compatibility first would couple two unrelated concerns for no
    /// benefit. The engine's own Python subprocess runs as the same local
    /// user on the same machine, so this direct check is a faithful proxy
    /// for what that subprocess would itself see when it later reads from
    /// or writes to this path — no subprocess invocation is needed to
    /// determine that.
    public func validateFolder(at url: URL, requireWritable: Bool) -> FolderValidationOutcome {
        folderAccessValidator.validate(url, requireWritable: requireWritable)
    }

    // MARK: - Command execution

    /// Runs `command` through the concurrency guard and process runner,
    /// after first verifying engine compatibility.
    ///
    /// This method's entire body is orchestration: verify compatibility,
    /// then delegate to `EngineMutationGuard.run(_:via:allowInteractive:)`
    /// — the single-mutation-slot rule (Task #578), the actual subprocess
    /// mechanics (Task #577), and per-invocation GUI logging (Task #580,
    /// via the `logger` already wired into `processRunner`) all remain
    /// exactly where they were built, not reimplemented here.
    public func run(_ command: EngineCommand, allowInteractive: Bool = false) async throws -> CommandResult {
        try await verifyEngineIsCompatible()
        do {
            return try await mutationGuard.run(command, via: processRunner, allowInteractive: allowInteractive)
        } catch {
            // ProcessRunner logs every CommandResult it actually produces,
            // success or failure, through the shared logger already — that
            // is not duplicated here. This catch exists only for the
            // failure modes that occur *before* any CommandResult exists at
            // all (refused by the concurrency guard, or a launch failure),
            // which ProcessRunner has no CommandResult to log on behalf of.
            await logger.log("run(\(command)) did not complete: \(error)", level: .error)
            throw error
        }
    }

    // MARK: - Artifact reads

    public func readConfiguration() async throws -> EngineConfiguration {
        try await withVersionGate("readConfiguration") { try self.configurationReader.read() }
    }

    public func readMetadataStore() async throws -> MetadataStoreReadResult {
        try await withVersionGate("readMetadataStore") { try self.metadataStoreReader.read() }
    }

    public func readActionLog() async throws -> ActionLogReadResult {
        try await withVersionGate("readActionLog") { try self.actionLogReader.read() }
    }

    public func readDuplicateReport() async throws -> ReportContent? {
        try await withVersionGate("readDuplicateReport") { try self.reportsReader.readDuplicateReport() }
    }

    public func readStorageReport() async throws -> ReportContent? {
        try await withVersionGate("readStorageReport") { try self.reportsReader.readStorageReport() }
    }

    public func readLatestDailySummary() async throws -> ReportContent? {
        try await withVersionGate("readLatestDailySummary") { try self.reportsReader.readLatestDailySummary() }
    }

    public func readLatestWeeklySummary() async throws -> ReportContent? {
        try await withVersionGate("readLatestWeeklySummary") { try self.reportsReader.readLatestWeeklySummary() }
    }

    // MARK: - Shared gating helper (the one piece of logic every read method shares)

    /// Runs the version-compatibility gate, then `body`, logging (but not
    /// duplicating the meaning of) any failure from either step. This is
    /// the single place the "check compatibility, then read" sequence is
    /// expressed — every artifact-read method above is a one-line call
    /// into this helper naming its own reader, so that sequence is never
    /// re-typed per artifact type.
    private func withVersionGate<T>(_ operationName: String, _ body: () throws -> T) async throws -> T {
        try await verifyEngineIsCompatible()
        do {
            return try body()
        } catch {
            await logger.log("\(operationName) failed: \(error)", level: .error)
            throw error
        }
    }
}
