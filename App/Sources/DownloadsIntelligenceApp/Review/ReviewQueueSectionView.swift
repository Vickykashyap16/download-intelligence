import SwiftUI
import EngineBridge

/// The single entry point `AppShell` uses for the `.reviewQueue` Sidebar
/// section. Owns the one `ReviewQueueViewModel` both the list and a Review
/// Detail drill-down share — Detail is state nested *under* Review Queue,
/// never a separate `AppSection` (`GUI Architecture Specification.md` line
/// 99), so `detailFileID` lives here as plain, local `@State` rather than
/// anywhere in `AppShell` itself, exactly mirroring how `PreviewFlowView`
/// keeps Preview's own internal state to itself.
///
/// `AppShell` re-creates this whole view (and therefore its
/// `@StateObject` `ReviewQueueViewModel`) fresh every time `.reviewQueue`
/// is (re-)selected — nothing here persists across a Sidebar navigation
/// away and back, matching every other screen's own "always fresh on
/// revisit" precedent (`GUI Architecture Specification.md` §7).
struct ReviewQueueSectionView: View {
    @StateObject private var reviewQueueViewModel: ReviewQueueViewModel
    private let bridge: EngineBridge
    private let onQueueEmpty: () -> Void

    @State private var detailFileID: String?

    init(bridge: EngineBridge, onQueueEmpty: @escaping () -> Void) {
        self.bridge = bridge
        _reviewQueueViewModel = StateObject(wrappedValue: ReviewQueueViewModel(bridge: bridge))
        self.onQueueEmpty = onQueueEmpty
    }

    var body: some View {
        if let detailFileID {
            ReviewDetailFlowView(
                bridge: bridge,
                fileID: detailFileID,
                reviewQueueViewModel: reviewQueueViewModel,
                onBackToQueue: { self.detailFileID = nil }
            )
        } else {
            ReviewQueueFlowView(
                viewModel: reviewQueueViewModel,
                onOpenDetail: { fileID in self.detailFileID = fileID },
                onOpenWhy: { fileID in self.detailFileID = fileID },
                onQueueEmpty: onQueueEmpty
            )
        }
    }
}
