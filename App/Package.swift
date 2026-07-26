// swift-tools-version:5.9
//
// Downloads Intelligence — Desktop App package manifest.
//
// This package lives entirely outside `src/` (the frozen Python engine) per
// `GUI Architecture Specification.md` §4 (Folder Architecture) and
// `Desktop Implementation Blueprint.md` §15/§19: nothing in this package
// modifies, imports, or links against any engine code. The `EngineBridge`
// target is WP-GUI-00's deliverable — the process-boundary integration layer
// specified in `GUI Architecture Specification.md` §3/§7/§8/§9/§16 and
// `Desktop Implementation Blueprint.md` §2/§5/§6/§8/§13/§14/§19.
//
// Minimum platform: macOS 13 (Ventura). The Architecture Specification and
// Implementation Blueprint both explicitly deferred "minimum supported macOS
// version" to implementation time (Architecture §17, Blueprint §22) — this is
// that deferred decision being made now, as a small, easily-revised default,
// not a re-litigation of anything those documents settled. macOS 13 is chosen
// as a reasonably current baseline that has Swift Concurrency (async/await,
// actors) fully available, which this package relies on throughout.
//
// Dependency: Yams, for reading `src/config/sources.yaml`. The engine's own
// config format is real YAML (comments, a nested `sources:` list, top-level
// scalar keys) — hand-rolling a parser for that would mean either an
// incomplete, fragile implementation (exactly the "shortcut" the engineering
// standards for this work package rule out) or silently re-deriving a large
// fraction of a real YAML parser ourselves (duplicated logic, also ruled
// out). Yams is a well-established, widely used Swift YAML library. This is a
// library choice for reading one existing, unmodified file — it does not
// touch, wrap, or reinterpret any engine logic, and it introduces no new
// architecture: `GUI Architecture Specification.md` §3/§8 already establishes
// that the Engine Bridge reads the engine's on-disk artifacts directly.

// WP-GUI-01 (`GUI Engineering Work Packages.md`) adds the application shell
// and shared component library on top of WP-GUI-00's `EngineBridge`. Per
// `GUI Architecture Specification.md` §2, the specific UI framework was
// deliberately left as an implementation detail deferred past the
// architecture documents ("SwiftUI vs. AppKit, or a mix"); SwiftUI is the
// concrete choice made here, for the same reason macOS 13 was chosen above
// as a small, easily-revised default rather than a re-litigated decision:
// it renders genuinely native macOS chrome (window, sidebar, sheets)
// satisfying `06 Visual Design System.md` §10's macOS Alignment
// requirements directly, it is fully available on the macOS 13 baseline
// already fixed in this file, and it lets the shared component library
// (§7 of that same document) be expressed as small, independently
// testable view types consistent with `GUI Architecture Specification.md`
// §4's "one implementation per component, reused everywhere" rule.
import PackageDescription

let package = Package(
    name: "DownloadsIntelligenceApp",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .library(name: "EngineBridge", targets: ["EngineBridge"]),
        .executable(name: "DownloadsIntelligenceApp", targets: ["DownloadsIntelligenceApp"])
    ],
    dependencies: [
        .package(url: "https://github.com/jpsim/Yams.git", from: "5.0.6")
    ],
    targets: [
        .target(
            name: "EngineBridge",
            dependencies: ["Yams"]
        ),
        .testTarget(
            name: "EngineBridgeTests",
            dependencies: ["EngineBridge"],
            resources: [
                .copy("Fixtures")
            ]
        ),
        .executableTarget(
            name: "DownloadsIntelligenceApp",
            dependencies: ["EngineBridge"]
        ),
        .testTarget(
            name: "DownloadsIntelligenceAppTests",
            dependencies: ["DownloadsIntelligenceApp"],
            resources: [
                .copy("Fixtures")
            ]
        )
    ]
)
