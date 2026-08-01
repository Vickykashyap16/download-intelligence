import EngineBridge

/// Derives the one-line, plain-language flag reason a "Flagged for you"
/// Review Card shows (`High-Fidelity UI Specification.md` §5, Content
/// Specification: "a one-line plain-language flag reason on each 'Flagged
/// for you' card," pulled from "the same hard-floor reasoning," per
/// `Wireframes — MVP.md` screen 10, annotation 5).
///
/// The engine's own hard-floor reasoning (`hard_floors_applied`, from
/// `src/pipeline/confidence.py`'s `apply_hard_floors()`) is **not**
/// persisted on `FileRecord`/`FileRecordSnapshot` at all — it exists only
/// as a transient detail on the one-time `score_confidence` action-log
/// entry written at scoring time, never re-derivable from a fresh
/// `metadata_store.json` read the way this GUI's every other projection
/// works (`GUI Architecture Specification.md` §7: always re-read current
/// on-disk state, never a historical log entry). Rather than reaching into
/// the action log for this one screen (a materially different, one-off
/// read path every other screen avoids), this type reconstructs the exact
/// same four hard-floor trigger conditions locally, from fields that *are*
/// persisted and already mirrored: `category`, `classificationSignals`,
/// `duplicateSignals` — the identical fields `confidence.py`'s own
/// `_trigger_unknown_category`/`_trigger_fuzzy_duplicate`/
/// `_trigger_multi_document`/`_trigger_locked_file` inspect, walked in the
/// same fixed order `_HARD_FLOORS` itself defines.
///
/// "Unknown category" and "Corrupted file" share one message here for the
/// same reason `confidence.py`'s own comment gives: the engine's hard-floor
/// table itself treats them as one indistinguishable trigger (a corrupted,
/// unparseable file and a file the classifier genuinely can't categorize
/// both simply end up `Category.unknown`) — there is no persisted signal
/// this package could use to tell them apart, so presenting two different
/// messages would fabricate a distinction the underlying data doesn't
/// support.
///
/// When no hard floor triggered at all — a record that reached
/// `review_required` purely from accumulated point deductions — the
/// reason shown is the single largest-magnitude deduction from
/// `ConfidenceDeductionFormatter`'s own breakdown (a disclosed, confirmed
/// product decision: concrete and reuses the same translation already
/// built for Review Detail, rather than a generic "confidence too low"
/// placeholder).
public enum FlagReasonResolver {
    public static func resolve(for record: FileRecordSnapshot) -> String {
        // Fixed order, matching `confidence.py`'s own `_HARD_FLOORS` table
        // row order exactly.
        if record.category == .unknown {
            return "This file's category couldn't be determined"
        }
        if record.duplicateSignals?.fuzzyDuplicate == true {
            return "Near-duplicate or fuzzy image match found"
        }
        if record.classificationSignals?.multiDocumentDetected == true {
            return "This file appears to contain more than one document"
        }
        if record.classificationSignals?.locked == true {
            return "Locked or password-protected file"
        }

        // No hard floor triggered — fall back to the single largest-
        // magnitude deduction (most negative `points`); a tie is broken by
        // `ConfidenceDeductionFormatter`'s own fixed ordering, since `min`
        // returns the first minimal element it encounters.
        let lines = ConfidenceDeductionFormatter.lines(from: record.confidenceBreakdown)
        if let largest = lines.min(by: { $0.points < $1.points }) {
            return largest.text
        }

        // Defensive-only fallback — should not occur for a genuinely
        // `review_required` record produced by the real engine, since every
        // such record has either a triggered hard floor or a non-empty
        // breakdown that pushed its score below 80.
        return "This file needs your review"
    }
}
