import Foundation

/// Per-card transcribe → propose-title → human-approve-or-edit → rename
/// state machine. One instance per RecordingCard (not shared/persisted —
/// restarting the app loses an in-progress proposal, which is fine: the
/// transcript sidecar on disk is kept, so re-transcribing is skipped, only
/// the title call reruns).
@MainActor
final class TranscriptionState: ObservableObject {
    enum Status: Equatable {
        case idle
        case running
        case proposed(transcript: String)
        case failed(String)
        case renamed(to: String)
    }

    @Published private(set) var status: Status = .idle
    @Published var editedTitle: String = ""

    /// force: true re-transcribes even if a transcript sidecar already
    /// exists (e.g. the user wants a fresh pass, or the first transcript
    /// came out garbled on a noisy/short clip).
    func start(url: URL, force: Bool = false) {
        status = .running
        Task {
            do {
                let result = try await TranscriptionService.describe(url: url, force: force)
                editedTitle = result.proposedTitle ?? ""
                status = .proposed(transcript: result.transcript ?? "")
            } catch {
                status = .failed(error.localizedDescription)
            }
        }
    }

    func dismiss() {
        status = .idle
    }

    func markRenamed(to name: String) {
        status = .renamed(to: name)
    }
}
