import Foundation

/// Reads just the one key this app cares about from
/// ~/.config/mac-transcribe/config.toml — the same recordings folder
/// RecorderApp writes into — so RecordingsVisualizer opens to the same
/// place by default instead of an unrelated folder. Deliberately minimal
/// (no shared target with RecorderApp, by design — see README) rather than
/// a full config parser; falls back to RecorderApp's own default path if
/// the file or key is missing, matching RecorderApp/Config.swift.
enum SharedConfig {
    static let defaultRecordingsDir: URL = {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Recordings/mac-transcribe")
    }()

    static var recordingsDir: URL {
        let configPath = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".config/mac-transcribe/config.toml")
        guard let text = try? String(contentsOf: configPath, encoding: .utf8) else {
            return defaultRecordingsDir
        }
        for rawLine in text.split(separator: "\n") {
            let line = rawLine.trimmingCharacters(in: .whitespaces)
            guard !line.hasPrefix("#"), let eq = line.firstIndex(of: "=") else { continue }
            let key = line[line.startIndex..<eq].trimmingCharacters(in: .whitespaces)
            guard key == "recordings_dir" else { continue }
            var value = line[line.index(after: eq)...].trimmingCharacters(in: .whitespaces)
            if value.hasPrefix("\""), value.hasSuffix("\""), value.count >= 2 {
                value = String(value.dropFirst().dropLast())
            }
            guard !value.isEmpty else { break }
            return URL(fileURLWithPath: (value as NSString).expandingTildeInPath)
        }
        return defaultRecordingsDir
    }
}
