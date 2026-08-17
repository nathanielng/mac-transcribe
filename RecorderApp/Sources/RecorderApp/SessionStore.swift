import Foundation
import Combine

/// Polls the recordings folder + each session's status.json so the menu list
/// reflects pipeline progress without the app needing IPC with the Python
/// subprocess — it just re-reads what process.py already writes to disk.
@MainActor
final class SessionStore: ObservableObject {
    @Published var sessions: [Session] = []
    private var timer: Timer?

    init() {
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    func refresh() {
        let cfg = AppConfig.load()
        try? FileManager.default.createDirectory(at: cfg.recordingsDir, withIntermediateDirectories: true)
        sessions = Session.scan(recordingsDir: cfg.recordingsDir)
    }

    func regenerate(_ session: Session, stage: String) {
        PipelineRunner.run(sessionDir: session.directory, force: [stage])
    }

    /// For a session with audio on disk but no status.json yet — e.g. a
    /// recording where the app quit or the handoff failed before
    /// PipelineRunner.run() got called. No --force-* flags: this just runs
    /// the normal skip-completed-stages pipeline from scratch.
    func runPipeline(_ session: Session) {
        PipelineRunner.run(sessionDir: session.directory)
    }
}
