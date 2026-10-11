// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "RecordingsVisualizer",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "RecordingsVisualizer",
            path: "Sources/RecordingsVisualizer"
        )
    ]
)
