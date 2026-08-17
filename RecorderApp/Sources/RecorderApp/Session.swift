import Foundation

/// Mirrors the shape pipeline/mac_transcribe/status.py writes, so the app can
/// poll a session's status.json to render progress in the menu.
struct StageStatus: Decodable {
    var status: String // "pending" | "running" | "ok" | "failed"
    var error: String?
}

struct SessionStatus: Decodable {
    var stages: [String: StageStatus]

    static func load(from sessionDir: URL) -> SessionStatus? {
        let path = sessionDir.appendingPathComponent("status.json")
        guard let data = try? Data(contentsOf: path) else { return nil }
        return try? JSONDecoder().decode(SessionStatus.self, from: data)
    }
}

enum StageState {
    case pending, running, ok, failed(String)

    init(_ s: StageStatus?) {
        switch s?.status {
        case "ok": self = .ok
        case "running": self = .running
        case "failed": self = .failed(s?.error ?? "unknown error")
        default: self = .pending
        }
    }

    var isAuthFailure: Bool {
        if case .failed(let msg) = self { return msg.hasPrefix("auth:") }
        return false
    }
}

/// One row in the recent-recordings list — a session folder on disk plus its
/// parsed status.json (if the pipeline has started/finished writing it).
struct Session: Identifiable {
    let id: String // folder name, unique per session
    let directory: URL
    let date: String
    let title: String
    var status: SessionStatus?

    var transcriptState: StageState { StageState(status?.stages["transcript"]) }
    var outlineState: StageState { StageState(status?.stages["outline"]) }
    var titleState: StageState { StageState(status?.stages["title_rename"]) }

    var htmlURL: URL? {
        let url = directory.appendingPathComponent("\(id).html")
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    var micURL: URL? {
        let url = directory.appendingPathComponent("mic.mp3")
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    var systemURL: URL? {
        let url = directory.appendingPathComponent("system.mp3")
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    /// True if any audio (mp3 or a not-yet-encoded wav) exists in the
    /// session folder — used to distinguish "pipeline never ran on this"
    /// (show a Run button) from "not actually a usable session."
    var hasAudio: Bool {
        for name in ["mic.mp3", "system.mp3", "mic.wav", "system.wav"] {
            if FileManager.default.fileExists(atPath: directory.appendingPathComponent(name).path) {
                return true
            }
        }
        return false
    }

    static func scan(recordingsDir: URL) -> [Session] {
        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: recordingsDir, includingPropertiesForKeys: [.contentModificationDateKey]
        ) else { return [] }

        let sessions: [Session] = entries.compactMap { dir in
            var isDir: ObjCBool = false
            guard FileManager.default.fileExists(atPath: dir.path, isDirectory: &isDir), isDir.boolValue else { return nil }

            let name = dir.lastPathComponent
            let parts = name.split(separator: "-", maxSplits: 3)
            guard parts.count >= 3 else { return nil }
            let date = parts[0...2].joined(separator: "-")
            let title = parts.count > 3 ? String(parts[3]) : "recording"

            return Session(id: name, directory: dir, date: date, title: title, status: SessionStatus.load(from: dir))
        }

        return sessions.sorted { $0.id > $1.id } // newest first, since names are date-prefixed
    }
}
