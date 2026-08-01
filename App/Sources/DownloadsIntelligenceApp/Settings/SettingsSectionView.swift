import SwiftUI
import EngineBridge

/// The single entry point `AppShell` uses for the `.settings` Sidebar
/// section — mirrors `ReportsSectionView`/`HistorySectionView`'s own
/// precedent exactly: `AppShell` re-creates this whole view (and therefore
/// its own `@StateObject` `SettingsViewModel`) fresh every time `.settings`
/// is (re-)selected, so entering Settings always re-reads the current
/// configuration and engine version rather than showing state left over
/// from a previous visit.
struct SettingsSectionView: View {
    @StateObject private var settingsViewModel: SettingsViewModel

    init(bridge: EngineBridge) {
        _settingsViewModel = StateObject(wrappedValue: SettingsViewModel(bridge: bridge))
    }

    var body: some View {
        SettingsView(viewModel: settingsViewModel)
    }
}
