import Foundation

/// Reads ~/.config/mac-transcribe/config.toml. Minimal key = "value" parser —
/// avoids pulling in a TOML dependency for what is a handful of flat keys
/// shared with the Python pipeline's mac_transcribe/config.py.
struct AppConfig {
    var recordingsDir: URL
    var autoRenameWithAITitle: Bool

    static let configPath: URL = {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".config/mac-transcribe/config.toml")
    }()

    static let defaultRecordingsDir: URL = {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Recordings/mac-transcribe")
    }()

    static func load() -> AppConfig {
        var recordingsDir = defaultRecordingsDir
        var autoRename = true

        if let text = try? String(contentsOf: configPath, encoding: .utf8) {
            for rawLine in text.split(separator: "\n") {
                let line = rawLine.trimmingCharacters(in: .whitespaces)
                guard !line.isEmpty, !line.hasPrefix("#"), let eq = line.firstIndex(of: "=") else { continue }
                let key = line[line.startIndex..<eq].trimmingCharacters(in: .whitespaces)
                var value = line[line.index(after: eq)...].trimmingCharacters(in: .whitespaces)
                value = value.trimmingCharacters(in: CharacterSet(charactersIn: "\""))

                switch key {
                case "recordings_dir":
                    recordingsDir = URL(fileURLWithPath: (value as NSString).expandingTildeInPath)
                case "auto_rename_with_ai_title":
                    autoRename = (value == "true")
                default:
                    break
                }
            }
        }

        return AppConfig(recordingsDir: recordingsDir, autoRenameWithAITitle: autoRename)
    }

    /// Writes back only the keys this app owns; leaves other keys the pipeline
    /// might rely on (bedrock_model, whisper_model, ...) untouched by reading
    /// existing content first and only replacing/appending known lines.
    func save() throws {
        let dir = Self.configPath.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        var lines: [String] = []
        var seenRecordingsDir = false
        var seenAutoRename = false

        if let existing = try? String(contentsOf: Self.configPath, encoding: .utf8) {
            for rawLine in existing.split(separator: "\n", omittingEmptySubsequences: false) {
                let line = String(rawLine)
                if line.hasPrefix("recordings_dir") {
                    lines.append("recordings_dir = \"\(recordingsDir.path)\"")
                    seenRecordingsDir = true
                } else if line.hasPrefix("auto_rename_with_ai_title") {
                    lines.append("auto_rename_with_ai_title = \(autoRenameWithAITitle)")
                    seenAutoRename = true
                } else {
                    lines.append(line)
                }
            }
        }

        if !seenRecordingsDir {
            lines.append("recordings_dir = \"\(recordingsDir.path)\"")
        }
        if !seenAutoRename {
            lines.append("auto_rename_with_ai_title = \(autoRenameWithAITitle)")
        }

        try lines.joined(separator: "\n").write(to: Self.configPath, atomically: true, encoding: .utf8)
    }
}
