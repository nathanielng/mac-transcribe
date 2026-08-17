import AppKit
import Foundation
import Combine

enum RecordingSource: String, CaseIterable, Identifiable {
    case mic = "Mic"
    case system = "System Audio"
    case both = "Both"
    var id: String { rawValue }
}

@MainActor
final class RecordingController: ObservableObject {
    @Published var isRecording = false
    @Published var selectedSource: RecordingSource = .mic
    @Published var detectedSource: DetectedSource = .none
    @Published var errorMessage: String?
    /// 0...1 mic input RMS level, updated live while recording — lets the user
    /// confirm the mic is actually picking up sound before trusting a session
    /// to a full recording.
    @Published var micLevel: Float = 0
    /// Same as micLevel but for system audio — the main way to confirm
    /// ScreenCaptureKit is actually capturing (vs. startCapture() having
    /// succeeded but no audio actually flowing, e.g. a missing permission).
    @Published var systemLevel: Float = 0

    private let micRecorder = MicRecorder()
    private let systemRecorder = SystemAudioRecorder()
    private let sleepAssertion = SleepAssertion()
    private var sessionDir: URL?
    private var startedAt: Date?

    let sessionStore: SessionStore

    var recordingsDir: URL { AppConfig.load().recordingsDir }

    init(sessionStore: SessionStore) {
        self.sessionStore = sessionStore
    }

    func openRecordingsFolder() {
        let dir = recordingsDir
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        NSWorkspace.shared.open(dir)
    }

    func start() {
        guard !isRecording else { return }
        errorMessage = nil
        detectedSource = DetectedSource.detectFrontmost()

        let dir = makeSessionDir()
        sessionDir = dir
        startedAt = Date()

        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

            if selectedSource == .mic || selectedSource == .both {
                micRecorder.onLevel = { [weak self] level in
                    Task { @MainActor in self?.micLevel = level }
                }
                try micRecorder.start(to: dir.appendingPathComponent("mic.wav"))
            }
            if selectedSource == .system || selectedSource == .both {
                systemRecorder.onLevel = { [weak self] level in
                    Task { @MainActor in self?.systemLevel = level }
                }
                Task {
                    do {
                        try await systemRecorder.start(to: dir.appendingPathComponent("system.wav"))
                    } catch {
                        await MainActor.run { self.errorMessage = "System audio capture failed: \(error.localizedDescription)" }
                    }
                }
            }
            isRecording = true
            if AppConfig.load().preventSleepWhileRecording {
                sleepAssertion.enable()
            }
        } catch {
            errorMessage = "Failed to start recording: \(error.localizedDescription)"
            sessionDir = nil
        }
    }

    /// Exposed so the UI can show whether sleep is currently being prevented —
    /// tied entirely to recording state, not a separate toggle to remember.
    var isSleepPrevented: Bool { sleepAssertion.isActive }

    func stop() {
        guard isRecording, let dir = sessionDir else {
            NSLog("mac-transcribe: stop() called but isRecording=\(isRecording) sessionDir=\(String(describing: sessionDir))")
            return
        }
        isRecording = false
        micLevel = 0
        systemLevel = 0
        sleepAssertion.disable()
        NSLog("mac-transcribe: stop() -> finalizing session at \(dir.path)")

        micRecorder.stop()

        Task {
            await systemRecorder.stop()
            await finalize(sessionDir: dir)
        }
    }

    private func finalize(sessionDir dir: URL) async {
        NSLog("mac-transcribe: finalize() started for \(dir.path)")
        for name in ["mic", "system"] {
            let wav = dir.appendingPathComponent("\(name).wav")
            guard FileManager.default.fileExists(atPath: wav.path) else {
                NSLog("mac-transcribe: no \(name).wav present, skipping")
                continue
            }
            let mp3 = dir.appendingPathComponent("\(name).mp3")
            NSLog("mac-transcribe: encoding \(name).wav -> \(name).mp3")
            do {
                try MP3Encoder.encodeToMP3(wavURL: wav, mp3URL: mp3)
                NSLog("mac-transcribe: encoded \(name).mp3 successfully")
            } catch {
                NSLog("mac-transcribe: encoding \(name) FAILED: \(error)")
                await MainActor.run { self.errorMessage = "Encoding \(name) failed: \(error.localizedDescription)" }
            }
        }

        NSLog("mac-transcribe: launching pipeline for \(dir.path)")
        PipelineRunner.run(sessionDir: dir)
        sessionStore.refresh()
        sessionDir = nil
        NSLog("mac-transcribe: finalize() complete")
    }

    private func makeSessionDir() -> URL {
        let cfg = AppConfig.load()
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        let date = df.string(from: Date())

        let source = DetectedSource.detectFrontmost()
        detectedSource = source
        var name = "\(date)-\(source.slug)"
        var suffix = 2
        while FileManager.default.fileExists(atPath: cfg.recordingsDir.appendingPathComponent(name).path) {
            name = "\(date)-\(source.slug)-\(suffix)"
            suffix += 1
        }

        return cfg.recordingsDir.appendingPathComponent(name)
    }
}
