import SwiftUI
import EngineBridge

/// The single entry point `AppShell` uses for the `.history` Sidebar
/// section — mirrors `ReviewQueueSectionView`'s own precedent exactly:
/// `AppShell` re-creates this whole view (and therefore its own
/// `@StateObject` `HistoryViewModel`) fresh every time `.history` is
/// (re-)selected, so History performs a genuinely fresh read on every
/// visit rather than persisting a `HistoryViewModel` at `AppShell`'s own
/// level the way `scanViewModel`/`executeViewModel` are (those two must
/// survive a Sidebar navigation away because they represent an in-flight
/// background operation; History has nothing in flight to preserve).
struct HistorySectionView: View {
    @StateObject private var historyViewModel: HistoryViewModel
    private let onUndoBatch: (String, [ExecuteResultProjection.FiledRow]) -> Void

    init(bridge: EngineBridge, onUndoBatch: @escaping (String, [ExecuteResultProjection.FiledRow]) -> Void) {
        _historyViewModel = StateObject(wrappedValue: HistoryViewModel(bridge: bridge))
        self.onUndoBatch = onUndoBatch
    }

    var body: some View {
        HistoryView(viewModel: historyViewModel, onUndoBatch: onUndoBatch)
    }
}
