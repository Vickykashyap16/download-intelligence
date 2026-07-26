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
        case enable
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
            case .enable:
                return ["provider", "enable"]
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
    /// `provider enable`'s lack of any non-interactive mode today is a real,
    /// disclosed gap between what a future AI Provider Settings screen will
    /// need (a way to invoke `provider enable` after the GUI has already
    /// shown its own disclosure and collected confirmation) and what the CLI
    /// currently exposes. WP-GUI-00 does not resolve that gap — resolving it
    /// would mean adding a new flag to `src/cli.py`, a change to a frozen
    /// module requiring its own authorization under the
    /// `Frozen Module Change Policy`, entirely out of this work package's
    /// scope (`GUI Architecture Specification.md` §3's explicit "flags it
    /// here as a concrete, well-scoped future engineering request... not as
    /// something decided or built now" precedent, applied to this specific
    /// case). It is recorded here, in code, precisely so the AI Provider
    /// Settings work package (WP-GUI-12) inherits this fact rather than
    /// re-discovering it.
    public var requiresInteractiveInput: Bool {
        switch self {
        case .initialSetup:
            return true
        case .execute(let yes, _):
            return !yes
        case .provider(.enable):
            return true
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
