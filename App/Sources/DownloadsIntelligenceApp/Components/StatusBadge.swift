import SwiftUI

/// The three Status Badge variants named in the Figma Production Guide §2:
/// Duplicate / Archived / Unknown-category tag — distinct from
/// `ConfidenceChip`, since "two distinct badge types coexist... never
/// visually merged into one combined badge type, since they answer
/// different questions" (`06 Visual Design System.md` §7).
public enum StatusBadgeKind: Equatable, Sendable, CaseIterable {
    case duplicate
    case archived
    case unknownCategory

    public var label: String {
        switch self {
        case .duplicate: return "Duplicate"
        case .archived: return "Archived"
        case .unknownCategory: return "Unknown"
        }
    }

    /// A paired/overlapping-shape mark for Duplicate; a calm container/box
    /// mark for Archived — deliberately never a trash/deletion icon
    /// (`06 Visual Design System.md` §5); and the same neutral, generic
    /// document mark used for the Unknown category everywhere else in the
    /// system (§5's "Unknown-category files use a plain, neutral
    /// placeholder mark").
    public var iconSystemName: String {
        switch self {
        case .duplicate: return "square.on.square"
        case .archived: return "archivebox"
        case .unknownCategory: return "doc"
        }
    }
}

public struct StatusBadge: View {
    private let kind: StatusBadgeKind

    public init(_ kind: StatusBadgeKind) {
        self.kind = kind
    }

    public var body: some View {
        HStack(spacing: 4) {
            Image(systemName: kind.iconSystemName)
                .font(.caption2)
            Text(kind.label)
                .font(.caption2.weight(.medium))
        }
        .padding(.vertical, 3)
        .padding(.horizontal, 8)
        .background(Color.secondary.opacity(0.12), in: Capsule())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(kind.label)
    }
}
