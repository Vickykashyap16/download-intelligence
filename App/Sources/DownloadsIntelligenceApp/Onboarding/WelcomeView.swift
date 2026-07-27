import SwiftUI

/// Screen 1: "the first thing anyone sees before any configuration exists"
/// (`High-Fidelity UI Specification.md` §1). No `EngineBridge` dependency
/// at all — "this screen has exactly one state" (§1, States) and "no
/// operation has been attempted yet that could fail" (§1, Error) — so this
/// view takes no bridge, only the one action it can produce.
public struct WelcomeView: View {
    private let onGetStarted: () -> Void

    public init(onGetStarted: @escaping () -> Void) {
        self.onGetStarted = onGetStarted
    }

    public var body: some View {
        VStack(spacing: 20) {
            Text("Downloads Intelligence")
                .font(.title.weight(.semibold))
                .accessibilityAddTraits(.isHeader)
            Text("Your Downloads folder, sorted — and always reversible.")
                .font(.title3)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            PrimaryButton("Get started", action: onGetStarted)
                .fixedSize()
        }
        .frame(maxWidth: 420)
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
