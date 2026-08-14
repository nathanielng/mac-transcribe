import AVFoundation

/// Records the default input device to a WAV file via AVAudioEngine. Encoding
/// to mp3 happens afterward (see Encoder.swift) — recording to a lossless
/// intermediate keeps the capture path simple and avoids encoder latency
/// glitches during the live tap.
final class MicRecorder {
    private let engine = AVAudioEngine()
    private var file: AVAudioFile?
    private(set) var isRecording = false

    func start(to wavURL: URL) throws {
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)

        file = try AVAudioFile(forWriting: wavURL, settings: format.settings)

        input.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, _ in
            try? self?.file?.write(from: buffer)
        }

        try engine.start()
        isRecording = true
    }

    func stop() {
        guard isRecording else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        file = nil
        isRecording = false
    }
}
