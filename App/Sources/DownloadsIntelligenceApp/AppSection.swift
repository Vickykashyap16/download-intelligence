import Foundation

/// The five-item Information Architecture the whole product's navigation is
/// built around (`GUI Architecture Specification.md` §6): Home, Review
/// Queue, History, Reports, Settings. This is the single, simple
/// "current section" selection §6 describes — there is no sixth section
/// and no hierarchical nesting at this level; drill-down states (Review
/// Detail, an expanded History row) are modeled as state *within* a
/// section by whichever future work package builds that section's real
/// content, never as an additional case here.
///
/// WP-GUI-01's scope is the Sidebar shell and navigation only — every
/// section's actual content is a placeholder until the work package that
/// owns it (per `GUI Implementation Roadmap.md`) is implemented.
public enum AppSection: String, CaseIterable, Identifiable, Sendable {
    case home
    case reviewQueue
    case history
    case reports
    case settings

    public var id: String { rawValue }

    /// The per-screen title register (`06 Visual Design System.md` §4,
    /// Heading) — also the Sidebar's own label for each destination, per
    /// the Figma Production Guide's Component Inventory ("Sidebar
    /// Navigation Item").
    public var title: String {
        switch self {
        case .home: return "Home"
        case .reviewQueue: return "Review Queue"
        case .history: return "History"
        case .reports: return "Reports"
        case .settings: return "Settings"
        }
    }

    /// The outline-style SF Symbol used for this destination's Default/
    /// Hover variants. `06 Visual Design System.md` §5 requires "one icon
    /// style... used everywhere," names no specific icon source, and
    /// requires each Sidebar destination to have "one fixed icon... used
    /// only there." SF Symbols (Apple's own system icon set) is the
    /// concrete choice made here to satisfy that requirement natively —
    /// the same kind of small, easily-revised implementation default
    /// `Package.swift` already documents for the macOS 13 minimum-version
    /// choice, not a new visual-design decision. Final bespoke icon marks
    /// (per `06 Visual Design System.md` §5's per-icon descriptions) remain
    /// a Figma production task, not something WP-GUI-01 is scoped to draw.
    public var outlineSymbolName: String {
        switch self {
        case .home: return "house"
        case .reviewQueue: return "tray.full"
        case .history: return "clock"
        case .reports: return "chart.bar.doc.horizontal"
        case .settings: return "gearshape"
        }
    }

    /// The filled counterpart used for the Active variant only (`06 Visual
    /// Design System.md` §5's "single deliberate exception of a filled
    /// variant for an otherwise-outline icon's active/selected state").
    public var filledSymbolName: String {
        outlineSymbolName + ".fill"
    }
}
