import Foundation

struct DescribeResult: Decodable {
    var transcriptPath: String?
    var transcript: String?
    var proposedTitle: String?
    var error: String?

    enum CodingKeys: String, CodingKey {
        case transcriptPath = "transcript_path"
        case transcript
        case proposedTitle = "proposed_title"
        case error
    }
}

/// Shells out to the Python pipeline's describe_recording module for
/// transcription + title proposal — local inference first (mlx-whisper,
/// then whatever outline_backend/model is already configured for titles,
/// mlx_lm by default). Deliberately not reimplemented in Swift: reuses the
/// exact same mlx-whisper path and TITLE_PROMPT the main pipeline already
/// uses, rather than a second, divergent implementation. Amazon Transcribe
/// is out of scope here (see describe_recording.py's docstring) — kept in
/// view for later, not wired in yet.
enum TranscriptionService {
    /// Mirrors RecorderApp/PipelineRunner.swift's pipelineDir/pythonPath
    /// resolution — both apps live in the same checkout, one directory
    /// level apart from the repo root.
    static var pipelineDir: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // Sources/RecordingsVisualizer
            .deletingLastPathComponent() // Sources
            .deletingLastPathComponent() // RecordingsVisualizer/
            .deletingLastPathComponent() // mac-transcribe/
            .appendingPathComponent("pipeline")
    }

    static var pythonPath: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".venv/bin/python3")
    }

    enum ServiceError: LocalizedError {
        case processFailed(String)
        case invalidOutput

        var errorDescription: String? {
            switch self {
            case .processFailed(let msg): return msg
            case .invalidOutput: return "describe_recording produced no parseable output"
            }
        }
    }

    /// Transcribes (mlx-whisper, writing/reusing a "<name>.transcript.txt"
    /// sidecar) and proposes a title. Model load + a long recording's
    /// decode can both take real wall-clock time — this is meant to be
    /// awaited from a background Task, never the main actor directly.
    static func describe(url: URL, force: Bool = false) async throws -> DescribeResult {
        try await withCheckedThrowingContinuation { continuation in
            let process = Process()
            process.executableURL = pythonPath
            process.currentDirectoryURL = pipelineDir
            var args = ["-m", "mac_transcribe.describe_recording", url.path]
            if force { args.append("--force") }
            process.arguments = args
            process.standardInput = FileHandle.nullDevice

            let stdout = Pipe()
            let stderr = Pipe()
            process.standardOutput = stdout
            process.standardError = stderr

            process.terminationHandler = { finished in
                let outData = stdout.fileHandleForReading.readDataToEndOfFile()
                let errData = stderr.fileHandleForReading.readDataToEndOfFile()
                // describe_recording.py always prints exactly one JSON
                // object as its *last* line of stdout (progress bars from
                // model downloads/loads can precede it on the same
                // stream) — take the last non-empty line rather than the
                // whole blob.
                let outText = String(data: outData, encoding: .utf8) ?? ""
                let lastLine = outText.split(separator: "\n").last.map(String.init) ?? ""
                guard let jsonData = lastLine.data(using: .utf8),
                      let result = try? JSONDecoder().decode(DescribeResult.self, from: jsonData) else {
                    let errText = String(data: errData, encoding: .utf8) ?? ""
                    let detail = errText.isEmpty ? outText : errText
                    continuation.resume(throwing: ServiceError.processFailed(
                        detail.isEmpty ? "exit code \(finished.terminationStatus)" : detail
                    ))
                    return
                }
                if let err = result.error {
                    continuation.resume(throwing: ServiceError.processFailed(err))
                } else {
                    continuation.resume(returning: result)
                }
            }

            do {
                try process.run()
            } catch {
                continuation.resume(throwing: error)
            }
        }
    }
}
