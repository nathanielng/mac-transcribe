import AVFoundation
import ScreenCaptureKit

/// Records system audio output (e.g. the other side of a Zoom/Teams call)
/// via ScreenCaptureKit's audio-only capture — no virtual audio driver
/// (BlackHole/Loopback) required. Requires Screen Recording permission.
final class SystemAudioRecorder: NSObject, SCStreamOutput, SCStreamDelegate {
    private var stream: SCStream?
    private var file: AVAudioFile?
    private var wavURL: URL?
    private(set) var isRecording = false

    func start(to url: URL) async throws {
        wavURL = url

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

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sampleBuffer.isValid, let url = wavURL else { return }

        guard let pcmBuffer = sampleBuffer.asPCMBuffer else { return }

        if file == nil {
            file = try? AVAudioFile(forWriting: url, settings: pcmBuffer.format.settings)
        }
        try? file?.write(from: pcmBuffer)
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
