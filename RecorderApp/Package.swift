// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "RecorderApp",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "RecorderApp",
            path: "Sources/RecorderApp",
            exclude: ["Info.plist"],
            linkerSettings: [
                // SPM produces a bare Mach-O binary, not a .app bundle, so
                // there's no Info.plist by default — but AVAudioEngine mic
                // access requires NSMicrophoneUsageDescription to be present
                // or the process is killed instead of prompting. Embedding
                // the plist into the __TEXT,__info_plist section is the
                // standard way to give a plain SPM executable one.
                .unsafeFlags([
                    "-Xlinker", "-sectcreate",
                    "-Xlinker", "__TEXT",
                    "-Xlinker", "__info_plist",
                    "-Xlinker", "Sources/RecorderApp/Info.plist",
                ])
            ]
        )
    ]
)
