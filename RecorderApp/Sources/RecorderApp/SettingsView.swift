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

            Section("Transcription (local, MLX-Whisper)") {
                TextField("Model", text: $config.whisperModel)
                    .textFieldStyle(.roundedBorder)
                Text("Any mlx-whisper-compatible model repo works as a drop-in swap.")
                    .font(.caption)
                    .foregroundColor(.secondary)
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

            HStack {
                if saved {
                    Text("Saved").font(.caption).foregroundColor(.green)
                }
                Spacer()
                Button("Save") { save() }
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
