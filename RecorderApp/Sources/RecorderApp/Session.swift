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

    /// Real bug: a session with no status.json at all — e.g. transcript.md
    /// placed there some other way than the normal pipeline, or a run that
    /// wrote transcript.md but crashed before ever writing status.json —
    /// showed the transcript stage as "pending" (⏳) forever, even though
    /// the transcript.md file sitting right there proves it's actually
    /// done. Same for outline. Falls back to inferring completion from the
    /// file's existence only when status.json has no opinion at all, so a
    /// stage explicitly marked "failed"/"running" is never overridden.
    var transcriptState: StageState {
        if let s = status?.stages["transcript"] { return StageState(s) }
        return hasTranscript ? .ok : .pending
    }

    var outlineState: StageState {
        if let s = status?.stages["outline"] { return StageState(s) }
        return hasOutline ? .ok : .pending
    }

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

    /// Raw stdout/stderr from the most recent pipeline run on this session,
    /// if any run has happened since PipelineRunner started writing it —
    /// see PipelineRunner.run()'s doc comment for why this exists.
    var pipelineLogURL: URL? {
        let url = directory.appendingPathComponent(PipelineRunner.logFilename)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        guard let size = try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int, size > 0 else { return nil }
        return url
    }

    /// True if any audio (mp3 or a not-yet-encoded wav) exists in the
    /// session folder — used to distinguish "pipeline never ran on this"
    /// (show a Run button) from "not actually a usable session," and to
    /// gate actions (Reprocess, regenerating the transcript stage) that
    /// need raw audio to do anything — the user may delete mp3s/transcripts
    /// after the fact and keep only the HTML, so these can't be assumed.
    var hasAudio: Bool {
        for name in ["mic.mp3", "system.mp3", "mic.wav", "system.wav"] {
            if FileManager.default.fileExists(atPath: directory.appendingPathComponent(name).path) {
                return true
            }
        }
        return false
    }

    /// Gates regenerating the outline stage — it reads transcript.md, so
    /// there's nothing to regenerate from if that's been deleted too.
    var hasTranscript: Bool {
        FileManager.default.fileExists(atPath: directory.appendingPathComponent("transcript.md").path)
    }

    var hasOutline: Bool {
        FileManager.default.fileExists(atPath: directory.appendingPathComponent("outline.md").path)
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
