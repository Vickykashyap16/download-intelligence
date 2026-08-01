import SwiftUI
import EngineBridge

/// The single entry point `AppShell` uses for the `.settings` Sidebar
/// section — mirrors `ReportsSectionView`/`HistorySectionView`'s own
/// precedent exactly: `AppShell` re-creates this whole view (and therefore
/// its own `@StateObject` `SettingsViewModel`) fresh every time `.settings`
/// is (re-)selected, so entering Settings always re-reads the current
/// configuration and engine version rather than showing state left over
/// from a previous visit.
///
/// **AI Provider Settings (WP-GUI-12), added additively.** `isShowingAIProviderSettings`
/// is this section's own local, `NavigationLink`-free drill-down state —
/// the same "state within whichever section reaches it, never a sixth
/// `AppSection`" idiom `AppShell`'s own `isPreviewShowing` already
/// establishes for Home's own drill-down. `aiProviderSettingsViewModel` is
/// hoisted here (not owned by `AIProviderSettingsView` itself) purely so
/// re-entering the sub-screen within the same Settings visit doesn't
/// discard in-progress state; leaving `.settings` for another Sidebar
/// section and returning re-creates this whole type fresh, per the
/// existing precedent above, which is the desired "no stale state carried
/// forward" behavior across a real navigation, not just a local toggle.
struct SettingsSectionView: View {
    @StateObject private var settingsViewModel: SettingsViewModel
    @StateObject private var aiProviderSettingsViewModel: AIProviderSettingsViewModel
    @State private var isShowingAIProviderSettings = false

    init(bridge: EngineBridge) {
        _settingsViewModel = StateObject(wrappedValue: SettingsViewModel(bridge: bridge))
        _aiProviderSettingsViewModel = StateObject(wrappedValue: AIProviderSettingsViewModel(bridge: bridge))
    }

    var body: some View {
        if isShowingAIProviderSettings {
            AIProviderSettingsView(
                viewModel: aiProviderSettingsViewModel,
                onBack: { isShowingAIProviderSettings = false }
            )
        } else {
            SettingsView(
                viewModel: settingsViewModel,
                onOpenAIProviderSettings: { isShowingAIProviderSettings = true }
            )
        }
    }
}
