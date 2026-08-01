import SwiftUI

/// Execute's result state (`High-Fidelity UI Specification.md` §8;
/// `Wireframes — MVP.md` screen 13): completion heading → per-destination
/// breakdown → Undo action → Back to Home action — the exact content
/// grouping §8's Layout Specification names for this state. "Undo this
/// batch" is deliberately given primary-adjacent visual weight, a
/// considered exception to the usual primary/secondary weighting (§8's
/// Screen Hierarchy: "Undo is deliberately given attention closer to
/// primary than a typical 'secondary' action would receive").
///
/// Partial-failure variant: "N of M filed" with the specific problem files
/// named (§8 States/Edge Cases; `Wireframes — MVP.md` screen 13's own
/// "Partial failure variant" note), never silently rounded to a bare
/// success message.
///
/// Undo itself is out of scope for this work package (`GUI Engineering Work
/// Packages.md`, WP-GUI-07 Scope: "Out of scope: Undo (next milestone)") —
/// `onUndo` routes to whatever "not built yet" presentation the caller
/// supplies, the same "the button exists and is reachable, but the
/// capability behind it isn't built yet" stub pattern `AppShell`'s own
/// `filingStub` already establishes for Execute itself prior to this work
/// package.
public struct ExecuteResultView: View {
    private let result: ExecuteResultProjection
    private let onUndo: () -> Void
    private let onBackToHome: () -> Void
    @AccessibilityFocusState private var isHeadingFocused: Bool

    public init(
        result: ExecuteResultProjection,
        onUndo: @escaping () -> Void,
        onBackToHome: @escaping () -> Void
    ) {
        self.result = result
        self.onUndo = onUndo
        self.onBackToHome = onBackToHome
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 8) {
                    Image(systemName: "checkmark.circle")
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                    Text(headingText)
                        .font(.title.weight(.semibold))
                }
                .accessibilityElement(children: .combine)
                .accessibilityAddTraits(.isHeader)
                .accessibilityFocused($isHeadingFocused)

                if !result.destinationBreakdown.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(result.destinationBreakdown, id: \.destinationFolder) { row in
                            HStack {
                                Text(row.destinationFolder)
                                Spacer()
                                Text("\(row.count)").monospacedDigit()
                            }
                        }
                    }
                    .padding(.top, 24)
                }

                if !result.problemRows.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Didn't file")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        ForEach(result.problemRows, id: \.fileID) { row in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.originalName)
                                Text(row.reason)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .accessibilityElement(children: .combine)
                        }
                    }
                    .padding(.top, 24)
                }

                // "Undo this batch" rendered with Primary-Button visual
                // weight (§8's noted exception) even though the nominal
                // default forward action remains "Back to Home".
                PrimaryButton("Undo this batch", action: onUndo)
                    .fixedSize()
                    .padding(.top, 32)
                    .accessibilityLabel(Text("Undo this batch"))

                SecondaryButton("Back to Home", action: onBackToHome)
                    .fixedSize()
                    .padding(.top, 16)
            }
            .padding(32)
            .frame(maxWidth: 560, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .onAppear { isHeadingFocused = true }
    }

    /// "N files filed." (full success) vs. "N of M filed." (partial
    /// failure) — §8 Content Specification / States.
    private var headingText: String {
        if result.isFullSuccess {
            return "\(result.filedCount) file\(result.filedCount == 1 ? "" : "s") filed."
        }
        return "\(result.filedCount) of \(result.totalAttempted) filed."
    }
}
