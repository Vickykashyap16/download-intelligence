import Foundation
import EngineBridge

/// Full-Screen / Inline — the two layout contexts the shared Error State
/// component renders in (Figma Production Guide §2), per `High-Fidelity UI
/// Specification.md` §14: "a full-screen replacement for a screen-level
/// failure... or an inline/localized treatment for a narrower failure."
public enum ErrorStateLayout: Equatable, Sendable {
    case fullScreen
    case inline
}

/// Everything the shared Error State component needs to render one
/// failure, entirely independent of which underlying error produced it —
/// the view itself has no knowledge of `EngineBridgeError` or any other
/// specific error type; only `forEngineBridgeFailure(_:layout:)` below
/// knows how to translate one into this generic shape, per `High-Fidelity
/// UI Specification.md` §14's "single, consistent pattern rather than
/// one-off error treatments."
public struct ErrorPresentation: Equatable, Sendable {
    public let heading: String
    public let explanation: String
    public let resolutionActionTitle: String?
    public let technicalDetail: String
    public let layout: ErrorStateLayout

    public init(
        heading: String,
        explanation: String,
        resolutionActionTitle: String?,
        technicalDetail: String,
        layout: ErrorStateLayout = .fullScreen
    ) {
        self.heading = heading
        self.explanation = explanation
        self.resolutionActionTitle = resolutionActionTitle
        self.technicalDetail = technicalDetail
        self.layout = layout
    }

    /// Translates a real `EngineBridgeError` into the plain-language
    /// explanation + resolution action + collapsed technical detail the
    /// Error State template requires (`High-Fidelity UI Specification.md`
    /// §14: "the user never sees a raw technical error by default"). This
    /// is the one place in the GUI layer that interprets
    /// `EngineBridgeError` cases into user-facing language — every other
    /// component only ever sees the resulting `ErrorPresentation`, never
    /// the underlying error type itself. `EngineBridgeError` is part of
    /// `EngineBridge`'s public facade contract specifically so a caller
    /// can do this (see that type's own `currentEngineVersion()`
    /// documentation) — this function is that caller, not a reach past
    /// the facade's boundary.
    ///
    /// `layout` defaults to `.fullScreen` since every WP-GUI-01 call site
    /// (the startup readiness check) is a screen-level failure; a future
    /// work package that surfaces a per-file inline error will construct
    /// its own `.inline`-layout presentation, still through this same
    /// mapping for heading/explanation/technicalDetail.
    public static func forEngineBridgeFailure(
        _ error: EngineBridgeError,
        layout: ErrorStateLayout = .fullScreen
    ) -> ErrorPresentation {
        // `EngineBridgeError.description` is already a precise,
        // human-written sentence (WP-GUI-00, `EngineBridgeError.swift`) —
        // used here as the Code/raw-technical-detail register (`06 Visual
        // Design System.md` §4), never as the plain-language explanation
        // itself, since it names internal concepts ("engine," "artifact,"
        // "process") the plain-language copy below deliberately avoids.
        let technicalDetail = String(describing: error)

        switch error {
        case .commandRequiresInteractiveInput:
            return ErrorPresentation(
                heading: "Something went wrong",
                explanation: "This action needs to run interactively, and the app couldn't do that automatically.",
                resolutionActionTitle: "Try again",
                technicalDetail: technicalDetail,
                layout: layout
            )
        case .anotherMutatingOperationInProgress:
            return ErrorPresentation(
                heading: "Already working on something",
                explanation: "Another operation is already running. Please wait for it to finish before starting a new one.",
                resolutionActionTitle: nil,
                technicalDetail: technicalDetail,
                layout: layout
            )
        case .failedToLaunchProcess:
            return ErrorPresentation(
                heading: "Couldn't reach the engine",
                explanation: "The application couldn't start the Downloads Intelligence engine. Make sure it's installed correctly and try again.",
                resolutionActionTitle: "Try again",
                technicalDetail: technicalDetail,
                layout: layout
            )
        case .projectRootNotFound:
            return ErrorPresentation(
                heading: "Installation not found",
                explanation: "The application couldn't find its engine installation in the expected location.",
                resolutionActionTitle: "Check installation",
                technicalDetail: technicalDetail,
                layout: layout
            )
        case .artifactUnreadable(let path, _):
            return ErrorPresentation(
                heading: "Something went wrong",
                explanation: "A file the app needs (\(Self.friendlyFileName(path))) exists but couldn't be read. It may be corrupted.",
                resolutionActionTitle: "Check folder settings",
                technicalDetail: technicalDetail,
                layout: layout
            )
        case .artifactNotFound(let path):
            return ErrorPresentation(
                heading: "Couldn't find something the app needs",
                explanation: "The app expected to find \(Self.friendlyFileName(path)), but it isn't there. This can happen the first time the engine runs, or if it was moved.",
                resolutionActionTitle: "Check folder settings",
                technicalDetail: technicalDetail,
                layout: layout
            )
        case .engineVersionTooOld(let engineVersion, let minimumSupportedVersion):
            return ErrorPresentation(
                heading: "Update needed",
                explanation: "The installed engine (version \(engineVersion)) is older than this app supports (at least \(minimumSupportedVersion) is required). Please update the engine.",
                resolutionActionTitle: "Learn how to update",
                technicalDetail: technicalDetail,
                layout: layout
            )
        case .engineVersionTooNew(let engineVersion, let maximumSupportedVersion):
            return ErrorPresentation(
                heading: "Update needed",
                explanation: "The installed engine (version \(engineVersion)) is newer than this version of the app has been tested with (up to \(maximumSupportedVersion) is supported). Please update the app.",
                resolutionActionTitle: "Check for app updates",
                technicalDetail: technicalDetail,
                layout: layout
            )
        }
    }

    private static func friendlyFileName(_ path: String) -> String {
        (path as NSString).lastPathComponent
    }
}
