import SwiftUI
import EngineBridge

/// Scan Progress (`High-Fidelity UI Specification.md` §3): a single
/// centered vertical stack — status line, Progress Indicator, reassurance
/// line — with no buttons at all ("no cancel action is specified... a
/// short, bounded, read-only operation"). The Sidebar itself is supplied by
/// whichever container renders this view (`AppShell`), exactly like every
/// other screen in this app — this view has no opinion about navigation
/// chrome.
public struct ScanProgressView: View {
    private let phase: ScanProgress.Phase

    public init(phase: ScanProgress.Phase) {
        self.phase = phase
    }

    public var body: some View {
        VStack(spacing: 20) {
            Text("Looking at your files…")
                .font(.title2.weight(.semibold))
                .accessibilityAddTraits(.isHeader)
            ProgressIndicatorView(indicatorStyle)
                .frame(maxWidth: 280)
            Text("Nothing is being moved yet.")
                .font(.body)
                .foregroundStyle(.secondary)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var indicatorStyle: ProgressIndicatorStyle {
        switch phase {
        case .indeterminate: return .indeterminate
        case .determinate(let progress): return .determinate(progress)
        }
    }
}
