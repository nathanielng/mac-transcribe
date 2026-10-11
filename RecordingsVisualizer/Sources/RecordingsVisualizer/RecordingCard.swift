import SwiftUI

struct RecordingCard: View {
    let recording: Recording
    @ObservedObject var player: PlayerController

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(recording.name)
                .font(.system(size: 13, weight: .medium))
                .lineLimit(1)
                .truncationMode(.tail)
                .help(recording.name)

            HStack(spacing: 10) {
                if recording.duration > 0 {
                    Text(recording.formattedDuration).fontWeight(.semibold)
                }
                if recording.sampleRate > 0 {
                    Text("\(Int(recording.sampleRate / 1000)) kHz")
                }
                if recording.channels > 0 {
                    Text(recording.channels == 1 ? "mono" : recording.channels == 2 ? "stereo" : "\(recording.channels) ch")
                }
                if let db = recording.peakDB {
                    Text("peak \(db, specifier: "%.1f") dBFS")
                }
                Text(recording.formattedSize)
            }
            .font(.caption)
            .foregroundColor(.secondary)

            WaveformView(recording: recording, player: player)
                .onTapGesture(count: 2) { player.toggle(url: recording.url) }

            if let error = recording.error {
                Text(error).font(.caption2).foregroundColor(.red)
            }

            Button(action: { player.toggle(url: recording.url) }) {
                Label(
                    player.currentURL == recording.url && player.isPlaying ? "Pause" : "Play",
                    systemImage: player.currentURL == recording.url && player.isPlaying ? "pause.fill" : "play.fill"
                )
            }
            .buttonStyle(.plain)
            .font(.caption)
            .foregroundColor(.accentColor)
        }
        .padding(12)
        .background(Color(nsColor: .controlBackgroundColor).opacity(0.5))
        .cornerRadius(10)
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color.secondary.opacity(0.15)))
    }
}
