import Foundation
import Combine
import os

private let logger = Logger(subsystem: "com.mac-transcribe.RecorderApp", category: "SessionStore")

/// Polls the recordings folder + each session's status.json so the menu list
/// reflects pipeline progress without the app needing IPC with the Python
/// subprocess — it just re-reads what process.py already writes to disk.
@MainActor
final class SessionStore: ObservableObject {
    @Published var sessions: [Session] = []
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
        do {
            try FileManager.default.createDirectory(at: cfg.recordingsDir, withIntermediateDirectories: true)
        } catch {
            logger.error("refresh() could not create/access \(cfg.recordingsDir.path, privacy: .public): \(String(describing: error), privacy: .public)")
        }
        let scanned = Session.scan(recordingsDir: cfg.recordingsDir)
        logger.notice("refresh() dir=\(cfg.recordingsDir.path, privacy: .public) found=\(scanned.count, privacy: .public) sessions=\(scanned.map { $0.id }.joined(separator: ","), privacy: .public)")
        sessions = scanned
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

    /// Forces every stage to re-run from scratch, even ones that already
    /// succeeded — unlike regenerate(_:stage:), which only targets one
    /// stage and is meant for retrying a *failure*. Useful after changing
    /// the outline backend/model in Settings and wanting an already-
    /// completed session redone with it, or just wanting a clean rebuild.
    func reprocess(_ session: Session) {
        PipelineRunner.run(sessionDir: session.directory, force: ["transcript", "outline", "title"])
    }
}
