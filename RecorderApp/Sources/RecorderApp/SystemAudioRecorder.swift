import AVFoundation
import Foundation
import ScreenCaptureKit

/// Records system audio output (e.g. the other side of a Zoom/Teams call)
/// via ScreenCaptureKit's audio-only capture — no virtual audio driver
/// (BlackHole/Loopback) required. Requires Screen Recording permission.
final class SystemAudioRecorder: NSObject, SCStreamOutput, SCStreamDelegate {
    private var stream: SCStream?
    private var file: AVAudioFile?
    private var wavURL: URL?
    private(set) var isRecording = false

    // SCStream has no native pause; the delegate callback below also runs on
    // a background queue (not the main actor RecordingController lives on),
    // so this needs its own lock rather than a plain var.
    private let stateLock = NSLock()
    private var _isPaused = false
    private var isPaused: Bool {
        get { stateLock.withLock { _isPaused } }
        set { stateLock.withLock { _isPaused = newValue } }
    }

    /// Called on every sample buffer with a 0...1 RMS level, same purpose as
    /// MicRecorder.onLevel — lets the UI confirm ScreenCaptureKit is
    /// actually capturing audio, not just that startCapture() succeeded.
    var onLevel: ((Float) -> Void)?

    func start(to url: URL) async throws {
        wavURL = url
        isPaused = false

        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else {
            throw NSError(domain: "SystemAudioRecorder", code: 1, userInfo: [NSLocalizedDescriptionKey: "No display available to capture audio from"])
        }

        let filter = SCContentFilter(display: display, excludingWindows: [])
        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)

        let stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: .init(label: "system-audio-capture"))
        try await stream.startCapture()

        self.stream = stream
        isRecording = true
    }

    func stop() async {
        guard isRecording else { return }
        try? await stream?.stopCapture()
        stream = nil
        file = nil
        isRecording = false
    }

    /// Pauses without stopping capture — the stream keeps running (stopping/
    /// restarting SCStream is heavier and risks a capture gap), but sample
    /// buffers are dropped instead of written while paused, and the level
    /// meter stops updating along with it.
    func pause() {
        isPaused = true
    }

    func resume() {
        isPaused = false
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sampleBuffer.isValid, let url = wavURL, !isPaused else { return }

        guard let pcmBuffer = sampleBuffer.asPCMBuffer else { return }

        if file == nil {
            file = try? AVAudioFile(forWriting: url, settings: pcmBuffer.format.settings)
        }
        try? file?.write(from: pcmBuffer)

        if let level = Self.rmsLevel(of: pcmBuffer) {
            onLevel?(level)
        }
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
        // System audio (the other side of a call, app playback, etc.) tends
        // to run quieter than a close-talking mic, so scale up more
        // aggressively than MicRecorder's 4x to keep the meter legible.
        return min(1.0, rms * 4)
    }
}

private extension CMSampleBuffer {
    /// Converts a ScreenCaptureKit audio CMSampleBuffer to an AVAudioPCMBuffer
    /// so it can be written with AVAudioFile, the same as MicRecorder's path.
    var asPCMBuffer: AVAudioPCMBuffer? {
        try? withAudioBufferList { audioBufferList, _ in
            guard let absd = formatDescription?.audioStreamBasicDescription else { return nil }
            guard let format = AVAudioFormat(standardFormatWithSampleRate: absd.mSampleRate, channels: absd.mChannelsPerFrame) else { return nil }
            return AVAudioPCMBuffer(pcmFormat: format, bufferListNoCopy: audioBufferList.unsafePointer)
        }
    }
}
