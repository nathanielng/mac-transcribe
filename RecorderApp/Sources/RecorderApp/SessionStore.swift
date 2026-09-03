import Foundation
import Combine

/// Polls the recordings folder + each session's status.json so the menu list
/// reflects pipeline progress without the app needing IPC with the Python
/// subprocess — it just re-reads what process.py already writes to disk.
@MainActor
final class SessionStore: ObservableObject {
    @Published var sessions: [Session] = []
    /// Bumped on every refresh() — see MenuBarView, which keys the list's
    /// `.id()` to this. MenuBarExtra's `.window` style has been observed to
    /// cache its content view and not always re-render on a plain
    /// `@Published [Session]` mutation; forcing identity to change
    /// guarantees a real re-render instead of relying on that diffing.
    @Published var lastRefreshed = Date()
    private var timer: Timer?

    init() {
        refresh()
        let timer = Timer(timeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
        // Default-mode timers stop firing while a menu/popover is being
        // tracked (NSMenu's tracking run loop mode is .eventTracking, not
        // .default) — so with the menu left open, refresh would silently
        // stop every 3s tick until it's closed. .common covers both.
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    func refresh() {
        let cfg = AppConfig.load()
        try? FileManager.default.createDirectory(at: cfg.recordingsDir, withIntermediateDirectories: true)
        sessions = Session.scan(recordingsDir: cfg.recordingsDir)
        lastRefreshed = Date()
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
