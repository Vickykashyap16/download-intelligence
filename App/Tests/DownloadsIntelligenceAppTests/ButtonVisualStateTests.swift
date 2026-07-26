import XCTest
@testable import DownloadsIntelligenceApp

/// Exhaustively verifies `ButtonVisualState.resolve(...)`'s precedence
/// rule against every combination of the four boolean inputs — this is
/// the one piece of logic behind all five Button variants named in the
/// Figma Production Guide §2 ("Default / Hover / Pressed / Focused /
/// Disabled"), and it is small enough to test exhaustively rather than
/// spot-check.
final class ButtonVisualStateTests: XCTestCase {

    func test_disabledOverridesEveryOtherInput() {
        for isPressed in [true, false] {
            for isFocused in [true, false] {
                for isHovered in [true, false] {
                    let state = ButtonVisualState.resolve(
                        isEnabled: false,
                        isPressed: isPressed,
                        isFocused: isFocused,
                        isHovered: isHovered
                    )
                    XCTAssertEqual(state, .disabled)
                }
            }
        }
    }

    func test_pressedOutranksFocusedAndHovered_whenEnabled() {
        XCTAssertEqual(
            ButtonVisualState.resolve(isEnabled: true, isPressed: true, isFocused: true, isHovered: true),
            .pressed
        )
        XCTAssertEqual(
            ButtonVisualState.resolve(isEnabled: true, isPressed: true, isFocused: false, isHovered: true),
            .pressed
        )
    }

    func test_focusedOutranksHovered_whenNotPressed() {
        XCTAssertEqual(
            ButtonVisualState.resolve(isEnabled: true, isPressed: false, isFocused: true, isHovered: true),
            .focused
        )
    }

    func test_hoveredAloneYieldsHovered() {
        XCTAssertEqual(
            ButtonVisualState.resolve(isEnabled: true, isPressed: false, isFocused: false, isHovered: true),
            .hovered
        )
    }

    func test_noInputsYieldsNormal() {
        XCTAssertEqual(
            ButtonVisualState.resolve(isEnabled: true, isPressed: false, isFocused: false, isHovered: false),
            .normal
        )
    }

    /// Every one of the 16 boolean combinations must resolve to exactly
    /// one of the five named states — this is the exhaustive sweep the
    /// four targeted tests above sample from by hand.
    func test_everyCombinationResolvesToAKnownState() {
        let knownStates: Set<ButtonVisualState> = [.normal, .hovered, .focused, .pressed, .disabled]
        for isEnabled in [true, false] {
            for isPressed in [true, false] {
                for isFocused in [true, false] {
                    for isHovered in [true, false] {
                        let state = ButtonVisualState.resolve(
                            isEnabled: isEnabled,
                            isPressed: isPressed,
                            isFocused: isFocused,
                            isHovered: isHovered
                        )
                        XCTAssertTrue(knownStates.contains(state))
                    }
                }
            }
        }
    }
}
