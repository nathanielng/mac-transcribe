import AVFoundation
import Foundation

/// Records the default input device to a WAV file via AVAudioEngine. Encoding
/// to mp3 happens afterward (see Encoder.swift) — recording to a lossless
/// intermediate keeps the capture path simple and avoids encoder latency
/// glitches during the live tap.
final class MicRecorder {
    private let engine = AVAudioEngine()
    private var file: AVAudioFile?
    private(set) var isRecording = false

    /// Called on every tap buffer with a 0...1 RMS level, so the UI can show a
    /// live input meter — the only practical way to confirm "yes, the mic is
    /// actually picking up sound" before committing to a full recording.
    var onLevel: ((Float) -> Void)?

    func start(to wavURL: URL) throws {
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)

        file = try AVAudioFile(forWriting: wavURL, settings: format.settings)

        input.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, _ in
            try? self?.file?.write(from: buffer)
            if let level = Self.rmsLevel(of: buffer) {
                self?.onLevel?(level)
            }
        }

        try engine.start()
        isRecording = true
    }

    private static func rmsLevel(of buffer: AVAudioPCMBuffer) -> Float? {
        guard let channelData = buffer.floatChannelData else { return nil }
        let frameLength = Int(buffer.frameLength)
        guard frameLength > 0 else { return nil }

        let channelCount = Int(buffer.format.channelCount)
        var sumSquares: Float = 0
        for channel in 0..<channelCount {
            let samples = channelData[channel]
            for i in 0..<frameLength {
                sumSquares += samples[i] * samples[i]
            }
        }
        let rms = sqrt(sumSquares / Float(frameLength * channelCount))
        // Map RMS (roughly 0...0.3 for normal speech) to a 0...1 meter value,
        // clamped — a raw RMS scale makes anything but shouting look empty.
        return min(1.0, rms * 4)
    }

    func stop() {
        guard isRecording else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        file = nil
        isRecording = false
    }

    /// Pauses the engine without tearing down the tap or closing the file —
    /// resume() just restarts the same engine and picks up where it left
    /// off, appending to the same WAV rather than needing a second file to
    /// stitch together later.
    func pause() {
        guard isRecording else { return }
        engine.pause()
    }

    func resume() throws {
        guard isRecording else { return }
        try engine.start()
    }
}
