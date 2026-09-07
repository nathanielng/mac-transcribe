import SwiftUI
import AppKit

/// Settings window: recordings folder, transcription model, and outline
/// backend/model — the pipeline reads the same config.toml this writes, so
/// changes apply on the next recording without restarting either side.
struct SettingsView: View {
    @State private var config = AppConfig.load()
    @State private var saved = false
    @State private var customBedrockModel = false
    @State private var customMLXModel = false
    @State private var detectingAccountID = false
    @State private var accountIDError: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Form {
            Section("Recordings Folder") {
                HStack {
                    Text(config.recordingsDir.path)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .foregroundColor(.secondary)
                    Spacer()
                    Button("Choose…") { chooseFolder() }
                }
            }

            Section("Transcription") {
                Picker("Backend", selection: $config.transcribeBackend) {
                    ForEach(TranscribeBackend.allCases) { backend in
                        Text(backend.displayName).tag(backend)
                    }
                }
                .pickerStyle(.segmented)

                switch config.transcribeBackend {
                case .mlxWhisper:
                    whisperModelFields
                case .amazonTranscribe:
                    amazonTranscribeFields
                }
            }

            Section("Outline Generation") {
                Picker("Backend", selection: $config.outlineBackend) {
                    ForEach(OutlineBackend.allCases) { backend in
                        Text(backend.displayName).tag(backend)
                    }
                }
                .pickerStyle(.segmented)

                switch config.outlineBackend {
                case .bedrock:
                    bedrockModelPicker
                case .mlxLM:
                    mlxModelPicker
                }
            }

            Section {
                Toggle("Auto-generate title & rename files", isOn: $config.autoRenameWithAITitle)
                Text("Uses the same outline backend/model above for a second, concurrent AI call.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Section {
                Toggle("Prevent sleep while recording", isOn: $config.preventSleepWhileRecording)
                Text("Keeps recording even with the lid closed and no external display, by holding a system sleep assertion for the duration of the recording (like caffeinate -s). Off means the Mac can sleep mid-recording, which pauses/ends it.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            HStack {
                if saved {
                    Text("Saved").font(.caption).foregroundColor(.green)
                }
                Spacer()
                Button("Save") { save() }
                Button("Save & Close") {
                    save()
                    dismiss()
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(16)
        .frame(width: 420)
        .onAppear {
            customBedrockModel = !BedrockModelOption.recommended.contains { $0.id == config.bedrockModel }
            customMLXModel = !MLXModelOption.recommended.contains { $0.id == config.mlxOutlineModel }
        }
    }

    private var whisperModelFields: some View {
        VStack(alignment: .leading, spacing: 6) {
            TextField("Model", text: $config.whisperModel)
                .textFieldStyle(.roundedBorder)
            Text("Any mlx-whisper-compatible model repo works as a drop-in swap. Fully local — no speaker diarization.")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private var amazonTranscribeFields: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                TextField("S3 bucket", text: $config.transcribeS3Bucket)
                    .textFieldStyle(.roundedBorder)
                Button(detectingAccountID ? "Detecting…" : "Suggest…") { detectAccountIDAndSuggestBucket() }
                    .disabled(detectingAccountID)
            }
            if let error = accountIDError {
                Text(error).font(.caption).foregroundColor(.red)
            }
            TextField("AWS region", text: $config.transcribeRegion)
                .textFieldStyle(.roundedBorder)
            TextField("AWS profile", text: $config.transcribeProfile)
                .textFieldStyle(.roundedBorder)
            Stepper("Max speakers: \(config.transcribeMaxSpeakers)", value: $config.transcribeMaxSpeakers, in: 2...30)
            Text("Adds real speaker diarization (Speaker 1/2/3…) for multiple people on one audio source, e.g. an in-person meeting on a single mic. Requires an S3 bucket you own (\"Suggest…\" only proposes a name via aws sts get-caller-identity — it does not create the bucket) and makes real, billable AWS API calls. See README.md for required IAM permissions.")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private func detectAccountIDAndSuggestBucket() {
        accountIDError = nil
        detectingAccountID = true
        let profile = config.transcribeProfile
        let region = config.transcribeRegion
        DispatchQueue.global(qos: .userInitiated).async {
            let result = Self.runAWSCommand(
                ["sts", "get-caller-identity", "--profile", profile, "--query", "Account", "--output", "text"]
            )
            DispatchQueue.main.async {
                detectingAccountID = false
                switch result {
                case .success(let accountID):
                    config.transcribeS3Bucket = "mac-transcribe-\(accountID)-\(region)"
                case .failure(let error):
                    accountIDError = error.message
                }
            }
        }
    }

    private struct AWSCommandError: Error { let message: String }

    /// Shells out to the `aws` CLI rather than linking an AWS SDK into this
    /// app just for one read-only identity lookup — the pipeline side
    /// already documents `aws sts get-caller-identity` as a prerequisite
    /// check (see README.md), so it's a reasonable thing to assume is
    /// on PATH. This only ever suggests a bucket *name*; it never creates
    /// or modifies any AWS resource.
    private static func runAWSCommand(_ arguments: [String]) -> Result<String, AWSCommandError> {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["aws"] + arguments
        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr
        do {
            try process.run()
        } catch {
            return .failure(AWSCommandError(message: "Couldn't run the aws CLI: \(error.localizedDescription). Is it installed and on PATH?"))
        }
        process.waitUntilExit()
        let outData = stdout.fileHandleForReading.readDataToEndOfFile()
        let errData = stderr.fileHandleForReading.readDataToEndOfFile()
        guard process.terminationStatus == 0 else {
            let message = String(data: errData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
            return .failure(AWSCommandError(message: message?.isEmpty == false ? message! : "aws CLI exited with status \(process.terminationStatus)"))
        }
        let output = String(data: outData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !output.isEmpty else {
            return .failure(AWSCommandError(message: "aws CLI returned no output"))
        }
        return .success(output)
    }

    private var bedrockModelPicker: some View {
        VStack(alignment: .leading, spacing: 6) {
            Picker("Model", selection: bedrockSelection) {
                ForEach(BedrockModelOption.recommended) { option in
                    Text(option.label).tag(option.id)
                }
                Text("Custom…").tag("__custom__")
            }
            if customBedrockModel {
                TextField("Bedrock model ID", text: $config.bedrockModel)
                    .textFieldStyle(.roundedBorder)
            }
            Text("Requires AWS credentials with Bedrock access in \(config.bedrockRegion).")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private var bedrockSelection: Binding<String> {
        Binding(
            get: { customBedrockModel ? "__custom__" : config.bedrockModel },
            set: { newValue in
                if newValue == "__custom__" {
                    customBedrockModel = true
                } else {
                    customBedrockModel = false
                    config.bedrockModel = newValue
                }
            }
        )
    }

    private var mlxModelPicker: some View {
        VStack(alignment: .leading, spacing: 6) {
            Picker("Model", selection: mlxSelection) {
                ForEach(MLXModelOption.recommended) { option in
                    Text(option.label).tag(option.id)
                }
                Text("Custom…").tag("__custom__")
            }
            if customMLXModel {
                TextField("mlx-lm model repo", text: $config.mlxOutlineModel)
                    .textFieldStyle(.roundedBorder)
            }
            Text("Fully local — no network or AWS credentials needed. Requires the mlx_lm extra: uv pip install -e \".[mlx_lm]\"")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private var mlxSelection: Binding<String> {
        Binding(
            get: { customMLXModel ? "__custom__" : config.mlxOutlineModel },
            set: { newValue in
                if newValue == "__custom__" {
                    customMLXModel = true
                } else {
                    customMLXModel = false
                    config.mlxOutlineModel = newValue
                }
            }
        )
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.directoryURL = config.recordingsDir
        if panel.runModal() == .OK, let url = panel.url {
            config.recordingsDir = url
        }
    }

    private func save() {
        try? config.save()
        saved = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { saved = false }
    }
}
