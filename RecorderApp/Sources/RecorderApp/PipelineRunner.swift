import Foundation

/// Spawns the Python pipeline (Stages 2-3) as a detached subprocess after a
/// recording finishes, or on a manual "Regenerate ..." click. Runs
/// `python3 -m mac_transcribe.process <session-dir>` from the pipeline/
/// directory checked into this same repo, using the user's existing venv.
enum PipelineRunner {
    /// Adjust if the pipeline moves relative to this app, or make configurable
    /// later — kept simple since both live in the same mac-transcribe checkout.
    static var pipelineDir: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // Sources/RecorderApp
            .deletingLastPathComponent() // Sources
            .deletingLastPathComponent() // RecorderApp/
            .deletingLastPathComponent() // mac-transcribe/
            .appendingPathComponent("pipeline")
    }

    static var pythonPath: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".venv/bin/python3")
    }

    /// force: which stages to force-regenerate, e.g. ["outline"] or ["title"].
    static func run(sessionDir: URL, force: Set<String> = []) {
        let process = Process()
        process.executableURL = pythonPath
        process.currentDirectoryURL = pipelineDir

        var args = ["-m", "mac_transcribe.process", sessionDir.path]
        args += force.map { "--force-\($0)" }
        process.arguments = args

        do {
            try process.run()
        } catch {
            NSLog("mac-transcribe: failed to launch pipeline: \(error)")
        }
        // Deliberately not waiting here — the menu bar app polls status.json
        // independently (see SessionStore) rather than blocking on this call.
    }
}
