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

    private let micRecorder = MicRecorder()
    private let systemRecorder = SystemAudioRecorder()
    private var sessionDir: URL?
    private var startedAt: Date?

    let sessionStore: SessionStore

    init(sessionStore: SessionStore) {
        self.sessionStore = sessionStore
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
                try micRecorder.start(to: dir.appendingPathComponent("mic.wav"))
            }
            if selectedSource == .system || selectedSource == .both {
                Task {
                    do {
                        try await systemRecorder.start(to: dir.appendingPathComponent("system.wav"))
                    } catch {
                        await MainActor.run { self.errorMessage = "System audio capture failed: \(error.localizedDescription)" }
                    }
                }
            }
            isRecording = true
        } catch {
            errorMessage = "Failed to start recording: \(error.localizedDescription)"
            sessionDir = nil
        }
    }

    func stop() {
        guard isRecording, let dir = sessionDir else {
            NSLog("mac-transcribe: stop() called but isRecording=\(isRecording) sessionDir=\(String(describing: sessionDir))")
            return
        }
        isRecording = false
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
