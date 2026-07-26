import SwiftUI
import AppKit

/// The Sidebar's three variants (Figma Production Guide §2): Default /
/// Hover / Active (filled icon). One fixed icon per destination (`06
/// Visual Design System.md` §5), reused nowhere else in the product.
struct SidebarNavigationItemView: View {
    let section: AppSection
    let isActive: Bool
    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: isActive ? section.filledSymbolName : section.outlineSymbolName)
                .frame(width: 20)
            Text(section.title)
            Spacer()
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(backgroundColor, in: RoundedRectangle(cornerRadius: 6, style: .continuous))
        // The active section's indicator uses the Primary color; every
        // other item uses a muted neutral tone (`06 Visual Design
        // System.md` §3, "Sidebar").
        .foregroundStyle(isActive ? Color.accentColor : Color.primary)
        .onHover { isHovered = $0 }
        .contentShape(Rectangle())
        .accessibilityAddTraits(isActive ? [.isButton, .isSelected] : .isButton)
    }

    private var backgroundColor: Color {
        if isActive { return Color.accentColor.opacity(0.15) }
        if isHovered { return Color.secondary.opacity(0.1) }
        return .clear
    }
}

/// The five-item Sidebar shell wired to placeholder content
/// (`GUI Engineering Work Packages.md`, WP-GUI-01 scope). This is the
/// single source of navigation truth (`GUI Architecture Specification.md`
/// §6) — there is no separate menu-bar-driven navigation path that could
/// fall out of sync with it.
public struct SidebarView: View {
    @Binding var selection: AppSection

    public init(selection: Binding<AppSection>) {
        self._selection = selection
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(AppSection.allCases) { section in
                Button {
                    selection = section
                } label: {
                    SidebarNavigationItemView(section: section, isActive: section == selection)
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(8)
        .frame(minWidth: 200, maxHeight: .infinity, alignment: .top)
        // A distinct background tone from the main content area,
        // establishing it as structural chrome rather than page content
        // (`06 Visual Design System.md` §3, "Sidebar").
        .background(Color(nsColor: .windowBackgroundColor).opacity(0.6))
    }
}
