import Foundation

/// The eleven engine operations the CLI exposes today (`src/cli.py`'s
/// `_COMMANDS` dict), modeled as a single, exhaustively-typed enum rather than
/// a free-form argument list — this is what makes it impossible, at compile
/// time, to construct an invalid combination such as `undo` with both a batch
/// ID *and* `--last` (which `src/cli.py`'s own `_cmd_undo()` rejects at
/// runtime with a usage error; here it simply cannot be expressed).
///
/// This type adds no capability the CLI doesn't already have and removes
/// none — every case maps to a real, existing subcommand, exactly as
/// documented in `src/cli.py`'s `build_parser()`. Per
/// `GUI Architecture Specification.md` §8: "No new commands or flags are
/// assumed to exist."
public enum EngineCommand: Equatable, Sendable {
    case scan
    case run
    case preview
    case execute(yes: Bool, debug: Bool)
    case undo(UndoTarget)
    case report
    case status
    case version
    case config(setSource: String? = nil, setDestination: String? = nil)
    /// Maps to the CLI's `init` subcommand. Not spelled `init` here since
    /// that is a reserved word for Swift initializers.
    case initialSetup
    case provider(ProviderAction)

    public enum UndoTarget: Equatable, Sendable {
        case last
        case batchID(String)
    }

    public enum ProviderAction: Equatable, Sendable {
        /// `yes: true` maps to the CLI's `-y`/`--yes` flag (INFRA-01 /
        /// OD-GUI-5), skipping only the interactive confirmation prompt —
        /// the disclosure text itself still prints engine-side regardless.
        /// Mirrors `EngineCommand.execute(yes: Bool, debug: Bool)`'s exact
        /// existing shape. The default (`false`) reproduces the exact
        /// pre-INFRA-01 behavior byte-for-byte — still refused by
        /// `ProcessRunner` without an explicit `allowInteractive` opt-in,
        /// still mapping to bare `["provider", "enable"]` — for any caller
        /// that constructs `.enable()` with no argument. Swift's own
        /// pattern-matching rules mean this default only helps at
        /// construction sites, not `switch`/`case` sites, so every existing
        /// bare `.provider(.enable)` reference (a handful of call sites in
        /// this package's own tests) needed updating to `.enable(yes:)`
        /// alongside this change — a one-time, fully mechanical migration,
        /// not a behavior change for any of them.
        case enable(yes: Bool = false)
        case disable
        case status
    }

    /// The `argv` this command maps to, *after* `python3 -m src.cli` —
    /// i.e. exactly what a terminal user would type following that prefix.
    /// Mirrors `src/cli.py`'s `build_parser()` argument names precisely
    /// (`-y`/`--yes`, `--debug`, positional `batch_id` vs. `--last`,
    /// `--set-source`/`--set-destination`, and the `provider` subcommand's
    /// own `enable`/`disable`/`status` sub-subparser).
    var argv: [String] {
        switch self {
        case .scan:
            return ["scan"]
        case .run:
            return ["run"]
        case .preview:
            return ["preview"]
        case .execute(let yes, let debug):
            var args = ["execute"]
            if yes { args.append("-y") }
            if debug { args.append("--debug") }
            return args
        case .undo(let target):
            switch target {
            case .last:
                return ["undo", "--last"]
            case .batchID(let id):
                return ["undo", id]
            }
        case .report:
            return ["report"]
        case .status:
            return ["status"]
        case .version:
            return ["version"]
        case .config(let setSource, let setDestination):
            var args = ["config"]
            if let setSource { args.append(contentsOf: ["--set-source", setSource]) }
            if let setDestination { args.append(contentsOf: ["--set-destination", setDestination]) }
            return args
        case .initialSetup:
            return ["init"]
        case .provider(let action):
            switch action {
            case .enable(let yes):
                var args = ["provider", "enable"]
                if yes { args.append("-y") }
                return args
            case .disable:
                return ["provider", "disable"]
            case .status:
                return ["provider", "status"]
            }
        }
    }

    /// Whether this specific invocation requires a real, attached interactive
    /// terminal to complete successfully. Three real paths in the existing
    /// CLI read from stdin: `init` (prompts for both settings, unconditionally
    /// — `src/cli.py`'s `_cmd_init()`/`_prompt_path()`/`_confirm()`),
    /// `execute` without `-y` when any `approval_required` record exists
    /// (`_collect_decisions_interactively()`/`_prompt_decision()`), and
    /// `provider enable` (its own `_confirm()` call in `_provider_enable()`
    /// — there is no `-y`/non-interactive flag for this subcommand in the
    /// CLI today).
    ///
    /// `GUI Architecture Specification.md` §8 is explicit that "the GUI never
    /// tries to feed simulated keystrokes into an interactive terminal
    /// prompt" — instead, the GUI's own screens collect the decision first
    /// and invoke non-interactively (e.g. `execute(yes: true, ...)` after
    /// Review Queue/Review Detail have already gathered every approval
    /// decision). This property is what lets `ProcessRunner` enforce that
    /// rule mechanically rather than by convention: by default (see
    /// `ProcessRunner.run(_:allowInteractive:)`), invoking a command for
    /// which this is `true` fails fast with a clear Swift error *before* a
    /// subprocess is even spawned, rather than silently spawning one that is
    /// guaranteed to fail (or, absent the stdin-closing discipline this
    /// package also applies unconditionally, to hang forever waiting on
    /// input that will never arrive).
    ///
    /// `provider enable`'s original lack of any non-interactive mode was a
    /// real, disclosed gap (tracked as OD-GUI-5) between what the AI
    /// Provider Settings screen needs (a way to invoke `provider enable`
    /// after the GUI has already shown its own disclosure and collected
    /// confirmation) and what the CLI exposed at WP-GUI-00 time. It was
    /// resolved by INFRA-01, which added `-y`/`--yes` to `provider enable`
    /// in `src/cli.py` under the Frozen Module Change Policy's lightweight
    /// patch path (`OD-GUI-5`, now Resolved). `.provider(.enable(yes:))`'s
    /// `yes` parameter is this case's own counterpart to that flag, mirroring
    /// `.execute(yes:debug:)` exactly: passing `yes: true` is what actually
    /// reaches the new flag via `argv` above, and is also what this property
    /// uses to report that the invocation no longer requires an interactive
    /// terminal — both must agree, the same way `.execute`'s `yes` already
    /// governs both its own `argv` and this property together.
    public var requiresInteractiveInput: Bool {
        switch self {
        case .initialSetup:
            return true
        case .execute(let yes, _):
            return !yes
        case .provider(.enable(let yes)):
            return !yes
        default:
            return false
        }
    }

    /// Whether this command can ever change engine-owned state on disk
    /// (the metadata store, the action log, the sources configuration file,
    /// or files in the user's source/destination folders) — as opposed to
    /// being purely read-only. Drives `EngineMutationGuard`'s single-slot
    /// rule (`GUI Architecture Specification.md` §9,
    /// `Desktop Implementation Blueprint.md` §7): exactly one mutating
    /// command may run at a time; read-only commands are never serialized
    /// against each other or against a running mutation.
    ///
    /// `preview` is deliberately classified as read-only: it computes and
    /// prints a plan but writes nothing (`src/cli.py`'s `_cmd_preview()`
    /// calls `run_preview()`, which is the same read-only `preview()`
    /// documented throughout the Master Plan and Architecture Specification
    /// as never moving or persisting anything). `report` is classified as
    /// mutating because it writes new report files to `Runtime/Reports/`
    /// (`src/storage/runtime_io.py`'s `write_daily_summary()` and siblings)
    /// even though it never touches the metadata store or action log —
    /// `Desktop Implementation Blueprint.md` §5 leaves this exact
    /// classification to the Engine Bridge's own judgment ("if report
    /// generation itself is a write operation... it may run alongside other
    /// read-only operations without contention, but should still respect the
    /// single-engine-mutation-slot rule if report generation is itself
    /// classified as a mutating operation on disk state") — classified here
    /// as mutating, the more conservative of the two allowed readings, since
    /// it does perform a real filesystem write.
    public var isMutating: Bool {
        switch self {
        case .preview, .status, .version:
            return false
        case .provider(.status):
            return false
        default:
            return true
        }
    }
}

extension EngineCommand: CustomStringConvertible {
    /// Renders as the exact `argv` this command maps to, space-joined
    /// (e.g. `"execute -y --debug"`, `"provider enable"`) — deliberately
    /// not Swift's default enum-mirror description, so a GUI log line or
    /// test failure message shows exactly what would be typed after
    /// `python3 -m src.cli`, not an internal case-name representation.
    public var description: String {
        argv.joined(separator: " ")
    }
}
