import SwiftUI
import EngineBridge

/// The single entry point `AppShell` uses for the `.reports` Sidebar
/// section — mirrors `HistorySectionView`'s own precedent exactly:
/// `AppShell` re-creates this whole view (and therefore its own
/// `@StateObject` `ReportsViewModel`) fresh every time `.reports` is
/// (re-)selected, so entering Reports always triggers a fresh generate-
/// and-read cycle rather than showing a `ReportsViewModel` left over from
/// a previous visit.
struct ReportsSectionView: View {
    @StateObject private var reportsViewModel: ReportsViewModel

    init(bridge: EngineBridge) {
        _reportsViewModel = StateObject(wrappedValue: ReportsViewModel(bridge: bridge))
    }

    var body: some View {
        ReportsView(viewModel: reportsViewModel)
    }
}
