import SwiftUI
import EngineBridge

/// The root view: Sidebar + content area, driven by
/// `AppLifecycleController` through `Desktop Implementation Blueprint.md`
/// §2's phases. This is WP-GUI-01's actual "application shell" deliverable
/// — every Sidebar destination shows placeholder content until the work
/// package that owns it builds the real screen.
public struct AppShell: View {
    @StateObject private var lifecycle: AppLifecycleController
    private let bridge: EngineBridge

    // Home reads independently of `lifecycle`'s own best-effort metadata
    // read (see `HomeViewModel`'s documentation). WP-GUI-04 replaces what
    // was, through WP-GUI-03, a shared placeholder for both "Scan now" and
    // "File them now" with the real Scan Progress/Scan Complete flow
    // (`ScanFlowView`) for scanning specifically. `scanViewModel` is
    // `nil` whenever no scan is in flight or being reviewed; creating one
    // (`beginScan()`) is what starts a real `run` invocation. It is owned
    // here, at `AppShell`'s level — not by whichever screen is currently
    // rendering it — precisely so Sidebar navigation away from Scan
    // Progress never cancels the scan (`High-Fidelity UI Specification.md`
    // §3, `Desktop Implementation Blueprint.md` §7).
    @State private var scanViewModel: ScanViewModel?

    // Execute (what Scan Complete's "File the N now" and Home's "File them
    // now" both lead to) — WP-GUI-04's own "not built yet" placeholder here
    // (formerly `isFilingStubShowing`) is filled in for real by WP-GUI-07.
    // Owned here, at `AppShell`'s level, for the same reason `scanViewModel`
    // is: Execute is a real, physical file operation running as a
    // background subprocess, and Sidebar navigation away from it must never
    // silently abandon an in-flight invocation (`ExecuteViewModel`'s own
    // documentation; `Desktop Implementation Blueprint.md` §7). `nil`
    // whenever no Execute flow is in progress or being reviewed; creating
    // one (`beginExecute()`) is what the user's "File them now"/"Execute
    // now"/"File the N now" actions all converge on.
    @State private var executeViewModel: ExecuteViewModel?

    // Undo (what Execute's own result screen leads to, and — as of
    // WP-GUI-09 — what a past batch's own row in History leads to too) —
    // WP-GUI-07's own "not built yet" placeholder here (formerly
    // `isUndoStubShowing`) was filled in for real by WP-GUI-08. `nil`
    // whenever no Undo dialog is open; creating one
    // (`beginUndo(filedRows:target:)`) is what either entry point's own
    // "Undo this batch" leads to. Unlike `scanViewModel`/`executeViewModel`,
    // Undo is not itself a Sidebar-navigable "screen" — per `High-Fidelity
    // UI Specification.md` §9's own Layout Specification, it is "rendered
    // as a Dialog... overlaid on the context it was triggered from," so
    // it's presented via a single `.sheet(...)` hoisted above
    // `placeholderContent(for:)` itself (`body`, `.displayingHome` case),
    // reachable from whichever section is currently on screen, rather than
    // being attached separately underneath each section that can trigger
    // it.
    @State private var undoViewModel: UndoViewModel?

    // Preview (WP-GUI-05) has nothing in flight to preserve across
    // Sidebar navigation the way a running scan does — `PreviewFlowView`
    // owns its own `PreviewViewModel` internally (see that type's own
    // documentation), so this is a plain `Bool`, not a hoisted view model,
    // mirroring `isFilingStubShowing`'s own simplicity. Reachable from Scan
    // Complete's "Review full plan" and, once a plan exists, from Home's
    // "Review the full plan" (`High-Fidelity UI Specification.md` §7).
    // Preview is deliberately not a sixth `AppSection` — `AppSection`'s own
    // documentation is explicit that drill-down states like this live as
    // state within whichever section reaches them, never as an additional
    // case there.
    @State private var isPreviewShowing = false

    // "the last active Sidebar section is restored" (`Desktop
    // Implementation Blueprint.md` §2) — session-local, disposable UI
    // state (`GUI Architecture Specification.md` §7), not business data,
    // so persisting it via `AppStorage` is consistent with the GUI's
    // state-ownership model. At WP-GUI-01's scope every section is always
    // a placeholder, so the "only if the underlying content it pointed to
    // is still meaningfully restorable" validity rule (ibid.) is
    // trivially satisfied for now; it becomes load-bearing once a future
    // work package adds a drill-down state (e.g. Review Detail) that
    // could itself become invalid across launches.
    @AppStorage("DownloadsIntelligence.lastSidebarSection") private var lastSidebarSectionRawValue = AppSection.home.rawValue
    @State private var selectedSection: AppSection = .home

    public init(bridge: EngineBridge) {
        self.bridge = bridge
        _lifecycle = StateObject(wrappedValue: AppLifecycleController(bridge: bridge))
    }

    public var body: some View {
        Group {
            switch lifecycle.phase {
            case .launching, .initializing, .loadingConfiguration, .checkingEngineReadiness, .readingMetadata, .restoringWindowState:
                ProgressIndicatorView(.indeterminate)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .firstRunNeeded:
                // WP-GUI-02: Welcome + First Run Experience, replacing
                // WP-GUI-01's routing-only placeholder. "Scan now" (Step 3)
                // now leads to the real Scan Progress/Scan Complete flow
                // (WP-GUI-04) — the same `ScanFlowView` Home's own "Scan
                // now"/"Scan again" use, never a second, bespoke
                // implementation. Onboarding has no Sidebar of its own
                // (unlike Home's call site below, which renders inside a
                // `NavigationSplitView`), so Scan Complete's real "Review"/
                // "File the N now" actions have nowhere meaningful to route
                // to yet here — both, plus an explicit "Continue to Home"
                // action, all converge on the same outcome: dismiss the
                // scan and re-run the lifecycle from scratch
                // (`await lifecycle.start()`), exactly the same fixed
                // sequence a normal relaunch would perform (`Desktop
                // Implementation Blueprint.md` §15, "Normal Launch...
                // follows the ordinary lifecycle in §2 straight through to
                // Display Home") — now reaching `.displayingHome` for the
                // first time, since the configuration First Run Experience
                // just wrote and verified now has a non-nil
                // `destinationRoot` (WP-GUI-01A's own routing check). This
                // is a deliberate, disclosed scope boundary, not an
                // oversight: WP-GUI-02 already left "Home or any screen
                // reached after 'Scan now'" out of its own scope, and nothing
                // here reopens that decision beyond making the transition a
                // real one instead of a placeholder.
                if let scanViewModel {
                    ScanFlowView(
                        viewModel: scanViewModel,
                        onReview: {
                            self.scanViewModel = nil
                            selectedSection = .reviewQueue
                            Task { await lifecycle.start() }
                        },
                        onFileNow: {
                            self.scanViewModel = nil
                            beginExecute()
                            Task { await lifecycle.start() }
                        },
                        extraCompletionActionTitle: "Continue to Home",
                        extraCompletionAction: {
                            self.scanViewModel = nil
                            Task { await lifecycle.start() }
                        }
                    )
                } else {
                    OnboardingFlowView(bridge: bridge, onScanRequested: { beginScan() })
                }
            case .error(let presentation):
                ErrorStateView(presentation)
            case .displayingHome:
                NavigationSplitView {
                    SidebarView(selection: $selectedSection)
                } detail: {
                    // Hoisted here (WP-GUI-09), rather than attached only to
                    // `.home`'s `ExecuteFlowView` as it was through
                    // WP-GUI-08, so the same Undo dialog/sheet is reachable
                    // from every section that can trigger it — now `.home`
                    // (Execute's own result screen) and `.history` (a past
                    // batch's own "Undo this batch") both converge on this
                    // one `undoViewModel`/`.sheet`, exactly as `High-Fidelity
                    // UI Specification.md` §9 frames Undo: one dialog, two
                    // entry points, never two separate implementations.
                    placeholderContent(for: selectedSection)
                        .sheet(isPresented: Binding(
                            get: { undoViewModel != nil },
                            set: { isPresented in if !isPresented { undoViewModel = nil } }
                        )) {
                            if let undoViewModel {
                                UndoFlowView(viewModel: undoViewModel, onBackToHome: { self.undoViewModel = nil })
                            }
                        }
                }
            }
        }
        .background(WindowAccessor(autosaveName: "DownloadsIntelligenceMainWindow"))
        .task {
            selectedSection = AppSection(rawValue: lastSidebarSectionRawValue) ?? .home
            await lifecycle.start()
        }
        .onChange(of: selectedSection) { newValue in
            lastSidebarSectionRawValue = newValue.rawValue
        }
    }

    /// Starts a new scan — the single place a `ScanViewModel` is created,
    /// so both entry points (below, and the `.firstRunNeeded` case above)
    /// always begin from the exact same fresh state.
    private func beginScan() {
        scanViewModel = ScanViewModel(bridge: bridge)
    }

    /// Starts a new Execute flow — the single place an `ExecuteViewModel`
    /// is created, so every entry point that can reach Execute (Home's
    /// "File them now," Scan Complete's "File the N now," Preview's
    /// "Execute now," and onboarding's own "File the N now") always begins
    /// from the exact same fresh state, mirroring `beginScan()`'s own
    /// single-creation-point pattern.
    private func beginExecute() {
        executeViewModel = ExecuteViewModel(bridge: bridge)
    }

    /// Starts a new Undo flow — the single place an `UndoViewModel` is
    /// created, mirroring `beginExecute()`'s own single-creation-point
    /// pattern. Reachable from two entry points as of WP-GUI-09: Execute's
    /// own result screen pressing "Undo this batch" (`target: .last`, the
    /// original WP-GUI-08 behavior, unchanged) and History's own
    /// per-batch "Undo this batch" (`target: .batchID(_)`, naming the
    /// specific past batch that row belongs to — `filedRows` is that same
    /// screen's own already-computed `HistoryProjection.Batch.filedRows`,
    /// mapped to `ExecuteResultProjection.FiledRow`). See `UndoViewModel`'s
    /// own documentation for why `filedRows` is seeded directly rather
    /// than independently re-derived, and why `target` defaults to `.last`.
    private func beginUndo(filedRows: [ExecuteResultProjection.FiledRow], target: EngineCommand.UndoTarget = .last) {
        undoViewModel = UndoViewModel(bridge: bridge, confirmedRows: filedRows, target: target)
    }

    @ViewBuilder
    private func placeholderContent(for section: AppSection) -> some View {
        switch section {
        case .home:
            if let executeViewModel {
                ExecuteFlowView(
                    viewModel: executeViewModel,
                    onCancel: { self.executeViewModel = nil },
                    onUndo: {
                        // "Undo this batch" is only ever reachable while
                        // Execute's own result screen is on display, so
                        // `executeViewModel.phase` is guaranteed to be
                        // `.result` at the moment this closure runs.
                        if case .result(let result) = executeViewModel.phase {
                            beginUndo(filedRows: result.filedRows)
                        }
                    },
                    onBackToHome: { self.executeViewModel = nil }
                )
            } else if isPreviewShowing {
                PreviewFlowView(
                    bridge: bridge,
                    onExecuteNow: {
                        isPreviewShowing = false
                        beginExecute()
                    },
                    onReview: {
                        isPreviewShowing = false
                        selectedSection = .reviewQueue
                    },
                    onScanNow: {
                        isPreviewShowing = false
                        beginScan()
                    },
                    onBackToHome: {
                        isPreviewShowing = false
                    }
                )
            } else if let scanViewModel {
                ScanFlowView(
                    viewModel: scanViewModel,
                    onReview: {
                        self.scanViewModel = nil
                        selectedSection = .reviewQueue
                    },
                    onFileNow: {
                        self.scanViewModel = nil
                        beginExecute()
                    },
                    onReviewFullPlan: {
                        self.scanViewModel = nil
                        isPreviewShowing = true
                    }
                )
            } else {
                HomeView(
                    bridge: bridge,
                    onGoToReviewQueue: { selectedSection = .reviewQueue },
                    onScanRequested: { beginScan() },
                    onFileThemNow: { beginExecute() },
                    onGoToPreview: { isPreviewShowing = true }
                )
            }
        case .reviewQueue:
            // "Empty: routes to Home's fully caught up empty state rather
            // than a bespoke empty Review Queue screen" (`High-Fidelity UI
            // Specification.md` §5) — a genuinely empty queue at fresh-read
            // time redirects the Sidebar selection itself back to `.home`,
            // rather than rendering separate "empty" content under this
            // section, so the Sidebar highlight always agrees with what's
            // actually on screen.
            ReviewQueueSectionView(
                bridge: bridge,
                onQueueEmpty: { selectedSection = .home }
            )
        case .history:
            HistorySectionView(
                bridge: bridge,
                onUndoBatch: { batchID, filedRows in
                    beginUndo(filedRows: filedRows, target: .batchID(batchID))
                }
            )
        default:
            EmptyStateView(
                systemImageName: section.outlineSymbolName,
                heading: section.title,
                explanation: "\(section.title)'s real content isn't built yet — that's a future work package."
            )
        }
    }
}
