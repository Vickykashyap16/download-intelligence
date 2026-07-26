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

import PackageDescription

let package = Package(
    name: "DownloadsIntelligenceApp",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .library(name: "EngineBridge", targets: ["EngineBridge"])
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
        )
    ]
)
