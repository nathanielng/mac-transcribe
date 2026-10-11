import SwiftUI

struct RecordingCard: View {
    let recording: Recording
    @ObservedObject var player: PlayerController
    @ObservedObject var library: LibraryModel

    @StateObject private var transcription = TranscriptionState()
    @State private var showTranscript = false
    @State private var renameError: String?

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

            HStack {
                Button(action: { player.toggle(url: recording.url) }) {
                    Label(
                        player.currentURL == recording.url && player.isPlaying ? "Pause" : "Play",
                        systemImage: player.currentURL == recording.url && player.isPlaying ? "pause.fill" : "play.fill"
                    )
                }
                .buttonStyle(.plain)
                .foregroundColor(.accentColor)

                Spacer()
                transcribeControl
            }
            .font(.caption)

            transcriptionDetail
        }
        .padding(12)
        .background(Color(nsColor: .controlBackgroundColor).opacity(0.5))
        .cornerRadius(10)
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color.secondary.opacity(0.15)))
    }

    @ViewBuilder
    private var transcribeControl: some View {
        switch transcription.status {
        case .idle:
            Button(action: { transcription.start(url: recording.url) }) {
                Label(
                    recording.hasTranscriptSidecar ? "Propose Title" : "Transcribe",
                    systemImage: "text.bubble"
                )
            }
            .buttonStyle(.plain)
            .foregroundColor(.accentColor)
            .help(recording.hasTranscriptSidecar
                ? "Transcript already on disk — reuse it and propose a title"
                : "Transcribe locally (mlx-whisper), then propose a title")
        case .running:
            HStack(spacing: 4) {
                ProgressView().controlSize(.small)
                Text("Working…")
            }
            .foregroundColor(.secondary)
        case .proposed, .failed:
            EmptyView() // shown below in transcriptionDetail instead
        case .renamed(let name):
            Label(name, systemImage: "checkmark.circle.fill")
                .foregroundColor(.green)
                .lineLimit(1)
        }
    }

    @ViewBuilder
    private var transcriptionDetail: some View {
        switch transcription.status {
        case .proposed(let transcript):
            VStack(alignment: .leading, spacing: 6) {
                Divider()
                Text("Proposed title — review, edit if needed, then approve:")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                HStack {
                    TextField("Title", text: $transcription.editedTitle)
                        .textFieldStyle(.roundedBorder)
                        .font(.caption)
                    Button("Approve & Rename") { approve(transcript: transcript) }
                        .disabled(transcription.editedTitle.trimmingCharacters(in: .whitespaces).isEmpty)
                    Button("Discard") { transcription.dismiss() }
                }
                if let prefix = recording.datePrefix {
                    Text("Will rename to: \(prefix) \(transcription.editedTitle).\(recording.url.pathExtension)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                } else {
                    Text("No date prefix detected in filename — will rename to just the title.")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                if let renameError {
                    Text(renameError).font(.caption2).foregroundColor(.red)
                }
                DisclosureGroup("Transcript", isExpanded: $showTranscript) {
                    ScrollView {
                        Text(transcript.isEmpty ? "(empty transcript)" : transcript)
                            .font(.caption2)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(maxHeight: 160)
                }
                .font(.caption)
            }
            .padding(.top, 2)
        case .failed(let message):
            VStack(alignment: .leading, spacing: 4) {
                Divider()
                Text(message).font(.caption2).foregroundColor(.red).lineLimit(3)
                Button("Retry") { transcription.start(url: recording.url, force: true) }
                    .font(.caption)
            }
            .padding(.top, 2)
        case .idle, .running, .renamed:
            EmptyView()
        }
    }

    private func approve(transcript: String) {
        let newURL = recording.renamedURL(title: transcription.editedTitle)
        do {
            try library.rename(recording, to: newURL)
            renameError = nil
            transcription.markRenamed(to: newURL.lastPathComponent)
        } catch {
            renameError = error.localizedDescription
        }
    }
}
