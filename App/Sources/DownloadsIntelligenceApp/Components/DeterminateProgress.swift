import Foundation

/// The pure logic behind the Progress Indicator component's Determinate
/// variant — `06 Visual Design System.md` §7: "Always determinate when a
/// real count is known... always paired with a plain-language count in
/// text, never a bar shown alone." Kept as a separate, plain type so its
/// fraction-clamping and label-formatting behavior is unit-testable
/// without instantiating any SwiftUI view.
public struct DeterminateProgress: Equatable, Sendable {
    public let completed: Int
    public let total: Int

    /// Negative inputs are clamped to zero rather than propagated — a
    /// negative count has no honest interpretation here, and this
    /// component's job (per §7 above) is to always show a real, sensible
    /// count, never to reflect an impossible upstream value uncritically.
    public init(completed: Int, total: Int) {
        self.completed = max(0, completed)
        self.total = max(0, total)
    }

    /// Clamped to `0...1`; `0` when `total` is `0` rather than dividing by
    /// zero, since a zero-total progress bar has nothing to show yet.
    public var fraction: Double {
        guard total > 0 else { return 0 }
        return min(1, Double(completed) / Double(total))
    }

    /// The always-required plain-language count, e.g. "12 of 41 files" —
    /// never a bar shown without this text alongside it (`06 Visual
    /// Design System.md` §7).
    public var label: String {
        "\(min(completed, total)) of \(total) files"
    }
}
