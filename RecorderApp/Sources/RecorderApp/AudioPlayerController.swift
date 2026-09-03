import AVFoundation

/// Plays a session's mic/system mp3 in-app via AVAudioPlayer, instead of
/// handing off to whatever the user's default app for .mp3 is — the
/// previous NSWorkspace.shared.open() approach opened an external player
/// with no way to stop it from RecorderApp itself. One shared player: only
/// one clip plays at a time, so starting a second stops the first rather
/// than overlapping.
@MainActor
final class AudioPlayerController: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published private(set) var currentURL: URL?
    private var player: AVAudioPlayer?

    func isPlaying(_ url: URL) -> Bool {
        currentURL == url
    }

    /// Play/Stop toggle for a single button: tapping the currently-playing
    /// clip's button stops it; tapping any other clip's button switches to it.
    func toggle(_ url: URL) {
        if isPlaying(url) {
            stop()
        } else {
            play(url)
        }
    }

    private func play(_ url: URL) {
        stop()
        do {
            let newPlayer = try AVAudioPlayer(contentsOf: url)
            newPlayer.delegate = self
            newPlayer.play()
            player = newPlayer
            currentURL = url
        } catch {
            NSLog("mac-transcribe: failed to play \(url.lastPathComponent): \(error)")
        }
    }

    func stop() {
        player?.stop()
        player = nil
        currentURL = nil
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in
            // Only clear if this callback is for the still-current player —
            // a stale finish callback from a clip that was already stopped
            // and replaced shouldn't clobber the new one's state.
            if self.player === player {
                self.player = nil
                self.currentURL = nil
            }
        }
    }
}
