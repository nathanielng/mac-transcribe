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

    /// Name of the per-session raw stdout/stderr capture — see run()'s doc
    /// comment on why this exists alongside status.json's own error field.
    static let logFilename = "pipeline.log"

    /// Keeps each Process (and its Pipe) alive for the duration of the run —
    /// run() doesn't block/wait on the process, so without holding a strong
    /// reference somewhere, ARC could deallocate them as soon as run()
    /// returns, tearing down the pipe mid-stream.
    private static var activeProcesses: [Process] = []

    /// force: which stages to force-regenerate, e.g. ["outline"] or ["title"].
    static func run(sessionDir: URL, force: Set<String> = []) {
        let process = Process()
        process.executableURL = pythonPath
        process.currentDirectoryURL = pipelineDir

        var args = ["-m", "mac_transcribe.process", sessionDir.path]
        args += force.map { "--force-\($0)" }
        process.arguments = args

        // Same defensive detach as MP3Encoder: never let a spawned subprocess
        // inherit this app's controlling tty (see the SIGTTOU/ffmpeg hang this
        // fixed there — python itself is less likely to touch termios, but
        // there's no reason for any of our subprocesses to share a terminal).
        process.standardInput = FileHandle.nullDevice

        // status.json's "error" field only covers exceptions process.py
        // itself catches — a hard crash before that (wrong venv path,
        // missing mac_transcribe module, an import error, a bug that
        // escapes every try/except) would otherwise leave genuinely no
        // trace anywhere, matching a real report of "the button doesn't
        // seem to do anything and I don't know where to look." Overwritten
        // (not appended) each run, so it always reflects the most recent
        // invocation only.
        let logURL = sessionDir.appendingPathComponent(logFilename)
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let logHandle = try? FileHandle(forWritingTo: logURL)

        // Tee stdout+stderr (merged into one pipe) to both pipeline.log AND
        // this app's own stdout — if RecorderApp itself is running attached
        // to a real terminal (e.g. launched via `swift build && .build/
        // debug/RecorderApp` in a screen/tmux session for development),
        // pipeline progress shows up live there too, not just in the log
        // file after the fact. Harmless no-op if RecorderApp's own stdout
        // isn't attached to anything interactive.
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            try? logHandle?.write(contentsOf: data)
            try? FileHandle.standardOutput.write(contentsOf: data)
        }

        process.terminationHandler = { finished in
            pipe.fileHandleForReading.readabilityHandler = nil
            try? logHandle?.close()
            DispatchQueue.main.async {
                activeProcesses.removeAll { $0 === finished }
            }
        }

        do {
            try process.run()
            activeProcesses.append(process)
        } catch {
            NSLog("mac-transcribe: failed to launch pipeline: \(error)")
        }
        // Deliberately not waiting here — the menu bar app polls status.json
        // independently (see SessionStore) rather than blocking on this call.
    }
}
