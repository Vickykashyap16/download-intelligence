import Foundation

/// One individually-unparseable unit within an otherwise-readable artifact
/// — one bad line in `action_log.jsonl`, or one malformed record inside
/// `metadata_store.json`'s array. Shared by `ActionLogReader` and
/// `MetadataStoreReader` rather than each reader inventing its own
/// per-error record shape, per WP-GUI-00's "do not duplicate parsing
/// logic" requirement applied to error reporting, not just to happy-path
/// parsing.
///
/// This exists because of a deliberate, spec-driven design choice: one
/// corrupted entry must never blind the GUI to every other, well-formed
/// entry in the same file (the same "isolated failure, not whole-batch
/// failure" principle `GUI Architecture Specification.md` §12 states for
/// engine invocations, applied here to reading the engine's own artifacts).
/// At the same time, a parse failure must never be silently swallowed —
/// `GUI Architecture Specification.md` §15 is explicit that engine-produced
/// evidence is never paraphrased or lost — so every skipped unit is
/// captured here with enough of its original content to investigate later,
/// not just a bare count.
public struct ArtifactParseIssue: Equatable, Sendable {
    /// The line number (1-based, for JSONL artifacts) or array index
    /// (0-based, for JSON-array artifacts) of the unparseable unit, within
    /// whichever artifact produced this issue.
    public let index: Int

    /// The original, unparsed content, truncated to a bounded length so a
    /// single pathological line cannot make the issue list itself
    /// unreasonably large. Never rewritten or summarized — truncated only.
    public let rawContent: String

    /// A human-readable description of why this unit failed to decode.
    public let reason: String

    private static let maximumRawContentLength = 2000

    public init(index: Int, rawContent: String, reason: String) {
        self.index = index
        if rawContent.count > Self.maximumRawContentLength {
            self.rawContent = String(rawContent.prefix(Self.maximumRawContentLength)) + "…"
        } else {
            self.rawContent = rawContent
        }
        self.reason = reason
    }
}
