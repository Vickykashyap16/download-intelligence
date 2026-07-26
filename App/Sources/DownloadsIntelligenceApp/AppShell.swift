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
    // read (see `HomeViewModel`'s documentation) — WP-GUI-03's stub
    // navigation targets for "Scan now" / "Scan again" / "File them now"
    // land here, as a simple inline replacement of the content area,
    // matching the same placeholder pattern already used for every other
    // not-yet-built Sidebar section below.
    @State private var isScanStubShowing = false

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
                // First Run Experience's real content is WP-GUI-02's
                // scope; this is a routing placeholder only, per
                // WP-GUI-01's own "out of scope: any screen's real
                // content."
                EmptyStateView(
                    systemImageName: "folder",
                    heading: "Let's get set up",
                    explanation: "First-time setup isn't built yet — that's the next work package."
                )
            case .error(let presentation):
                ErrorStateView(presentation)
            case .displayingHome:
                NavigationSplitView {
                    SidebarView(selection: $selectedSection)
                } detail: {
                    placeholderContent(for: selectedSection)
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

    @ViewBuilder
    private func placeholderContent(for section: AppSection) -> some View {
        switch section {
        case .home:
            if isScanStubShowing {
                EmptyStateView(
                    systemImageName: "arrow.triangle.2.circlepath",
                    heading: "Scan Progress isn't built yet",
                    explanation: "That's a future work package.",
                    secondaryActionTitle: "Back to Home",
                    secondaryAction: { isScanStubShowing = false }
                )
            } else {
                HomeView(
                    bridge: bridge,
                    onGoToReviewQueue: { selectedSection = .reviewQueue },
                    onScanRequested: { isScanStubShowing = true },
                    onFileThemNow: { isScanStubShowing = true }
                )
            }
        default:
            EmptyStateView(
                systemImageName: section.outlineSymbolName,
                heading: section.title,
                explanation: "\(section.title)'s real content isn't built yet — that's a future work package."
            )
        }
    }
}
