import SwiftUI

/// Sheet-style, single-purpose, never stacked (`06 Visual Design System.md`
/// §6, §7; `GUI Architecture Specification.md` §5). This view is the body
/// content presented via SwiftUI's native `.sheet(...)` modifier by
/// whichever screen opens it — it does not manage its own presentation
/// state, since "never stacked" and "always attached to the screen that
/// opened it" (`Desktop Implementation Blueprint.md` §4) are the
/// presenting screen's responsibility, not this shared component's.
public struct DialogSheet: View {
    private let title: String
    private let message: String
    private let kind: DialogKind
    private let onPrimary: () -> Void
    private let onCancel: (() -> Void)?

    public init(
        title: String,
        message: String,
        kind: DialogKind,
        onPrimary: @escaping () -> Void,
        onCancel: (() -> Void)? = nil
    ) {
        self.title = title
        self.message = message
        self.kind = kind
        self.onPrimary = onPrimary
        self.onCancel = onCancel
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(title)
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
            Text(message)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Spacer()
                switch kind {
                case .confirmation(let confirmTitle, let cancelTitle):
                    SecondaryButton(cancelTitle) { onCancel?() }
                        .fixedSize()
                    PrimaryButton(confirmTitle, action: onPrimary)
                        .fixedSize()
                case .result(let dismissTitle):
                    PrimaryButton(dismissTitle, action: onPrimary)
                        .fixedSize()
                }
            }
        }
        .padding(24)
        .frame(minWidth: 360, maxWidth: 480)
    }
}
