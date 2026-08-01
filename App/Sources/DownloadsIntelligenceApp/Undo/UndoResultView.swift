import SwiftUI

/// Undo's result state (`High-Fidelity UI Specification.md` §9;
/// `Wireframes — MVP.md` screen 15). Rendered as a `DialogSheet`
/// (WP-GUI-01, frozen), reusing the same `.result` single-button kind
/// Execute's own result screen conceptually mirrors, per §9 Layout
/// Specification's "single-purpose Dialog body."
///
/// Title stays "Restored." in both the full-success and partial-failure
/// case — §9 Content Specification names only one result title, and its
/// own States example ("39 of 41 restored; 2 files couldn't be
/// restored...") carries the count and per-file detail in the supporting
/// sentence, not the heading, unlike Execute's own result screen (which
/// does vary its heading between "N filed."/"N of M filed."). This view
/// follows §9's own example shape rather than borrowing Execute's heading
/// convention.
///
/// §9 States' partial-failure example ends "...see details," implying a
/// link into History. No History screen exists yet at WP-GUI-08's scope
/// (`GUI Engineering Work Packages.md`, WP-GUI-08: reachable from the
/// Execute result screen only) — there is nothing to link to. Rather than
/// inventing a navigation target this work package has no authority to
/// build, the specific problem files and their reasons are named directly
/// in the message text instead, honestly disclosed here as a scope-bound
/// adaptation of the source copy, in the same spirit as Execute's own
/// result screen naming its problem files inline.
///
/// Same disclosed icon-pairing gap as `UndoConfirmationView` — see that
/// type's own documentation.
public struct UndoResultView: View {
    private let result: UndoResultProjection
    private let onBackToHome: () -> Void

    public init(result: UndoResultProjection, onBackToHome: @escaping () -> Void) {
        self.result = result
        self.onBackToHome = onBackToHome
    }

    public var body: some View {
        DialogSheet(
            title: "Restored.",
            message: messageText,
            kind: .result(dismissTitle: "Back to Home"),
            onPrimary: onBackToHome
        )
    }

    private var messageText: String {
        if result.isFullSuccess {
            return "\(result.restoredCount) file\(result.restoredCount == 1 ? "" : "s") are back in Downloads, exactly as they were."
        }
        let problemDescriptions = result.problemRows
            .map { "\($0.originalName) (\($0.reason))" }
            .joined(separator: ", ")
        return "\(result.restoredCount) of \(result.totalAttempted) restored. "
            + "\(result.problemRows.count) file\(result.problemRows.count == 1 ? "" : "s") couldn't be restored: \(problemDescriptions)."
    }
}
