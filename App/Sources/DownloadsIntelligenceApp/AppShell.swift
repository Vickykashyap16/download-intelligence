import SwiftUI
import EngineBridge

/// The root view: Sidebar + content area, driven by
/// `AppLifecycleController` through `Desktop Implementation Blueprint.md`
/// §2's phases. This is WP-GUI-01's actual "application shell" deliverable
/// — every Sidebar destination shows placeholder content until the work
/// package that owns it builds the real screen.
public struct AppShell: View {
    @StateObject private var lifecycle: AppLifecycleController

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
        EmptyStateView(
            systemImageName: section.outlineSymbolName,
            heading: section.title,
            explanation: "\(section.title)'s real content isn't built yet — that's a future work package."
        )
    }
}
