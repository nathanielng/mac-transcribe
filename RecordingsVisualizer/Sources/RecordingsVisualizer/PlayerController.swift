import AVFoundation
import Combine

/// Single shared player so clicking a different waveform stops whatever
/// was playing — same one-at-a-time behavior as the original page's
/// single <audio> element.
@MainActor
final class PlayerController: NSObject, ObservableObject {
    @Published private(set) var currentURL: URL?
    @Published private(set) var currentTime: TimeInterval = 0
    @Published private(set) var duration: TimeInterval = 0
    @Published private(set) var isPlaying = false

    private var player: AVAudioPlayer?
    private var timer: Timer?

    func play(url: URL, atFraction fraction: Double) {
        if currentURL != url {
            stop()
            guard let p = try? AVAudioPlayer(contentsOf: url) else { return }
            player = p
            p.delegate = self
            currentURL = url
            duration = p.duration
        }
        guard let p = player else { return }
        p.currentTime = fraction * p.duration
        p.play()
        isPlaying = true
        startTimer()
    }

    func toggle(url: URL) {
        if currentURL == url, isPlaying {
            player?.pause()
            isPlaying = false
            timer?.invalidate()
        } else {
            play(url: url, atFraction: (currentURL == url) ? (currentTime / max(duration, 0.001)) : 0)
        }
    }

    func stop() {
        player?.stop()
        player = nil
        currentURL = nil
        currentTime = 0
        duration = 0
        isPlaying = false
        timer?.invalidate()
    }

    private func startTimer() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, let p = self.player else { return }
                self.currentTime = p.currentTime
            }
        }
    }
}

extension PlayerController: AVAudioPlayerDelegate {
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.stop() }
    }
}
