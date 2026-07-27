import Foundation

/// The three steps of First Run Experience (`High-Fidelity UI
/// Specification.md` §16: "the three-step guided setup (Source,
/// Destination, Ready to scan)"), modeled as a plain, fully ordered enum —
/// no `EngineBridge` or SwiftUI dependency, so step ordering/indicator/
/// Back-availability logic is unit-testable in isolation, mirroring
/// `HomeProjection`'s own "kept separate... so this logic is unit-testable
/// without an EngineBridge... or any asynchronous code at all" precedent
/// (WP-GUI-03).
public enum FirstRunStep: Int, CaseIterable, Equatable, Sendable {
    case source = 1
    case destination = 2
    case readyToScan = 3

    /// "Labels: step indicator text ('N of 3')" (§16, Content
    /// Specification).
    public var indicatorText: String {
        "\(rawValue) of \(Self.allCases.count)"
    }

    /// "there is no escape from Step 1 back to Welcome other than
    /// closing/quitting, consistent with Welcome's own lack of an escape
    /// action" (§16, User Actions) — Back is only ever available on steps
    /// 2 and 3.
    public var canGoBack: Bool {
        self != .source
    }

    /// `nil` for `.source`, matching `canGoBack` above — there is no step
    /// to return to from Step 1.
    public var previous: FirstRunStep? {
        FirstRunStep(rawValue: rawValue - 1)
    }
}
