import Foundation

enum OutlineBackend: String, CaseIterable, Identifiable {
    case bedrock
    case mlxLM = "mlx_lm"
    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .bedrock: return "Amazon Bedrock"
        case .mlxLM: return "Local (MLX)"
        }
    }
}

/// A curated Bedrock model to offer in the picker, alongside "Custom" for
/// anything else the pipeline's free-text bedrock_model config accepts.
struct BedrockModelOption: Identifiable, Hashable {
    let id: String // the actual model ID sent to Bedrock
    let label: String

    static let recommended: [BedrockModelOption] = [
        BedrockModelOption(id: "global.anthropic.claude-sonnet-5", label: "Claude Sonnet 5"),
        BedrockModelOption(id: "deepseek.v3.2", label: "DeepSeek V3.2 (open-weight, Sonnet-tier)"),
        BedrockModelOption(id: "qwen.qwen3-vl-235b-a22b", label: "Qwen3-235B-A22B (open-weight, Haiku-tier)"),
    ]
}

struct MLXModelOption: Identifiable, Hashable {
    let id: String
    let label: String

    static let recommended: [MLXModelOption] = [
        MLXModelOption(id: "mlx-community/Qwen3.5-4B-MLX-4bit", label: "Qwen3.5 4B (fast, ~4GB)"),
        MLXModelOption(id: "mlx-community/Qwen3.5-9B-MLX-4bit", label: "Qwen3.5 9B (balanced, ~6GB)"),
        MLXModelOption(id: "mlx-community/Qwen3.5-27B-4bit", label: "Qwen3.5 27B (highest quality, ~16GB+)"),
    ]
}

/// Reads/writes ~/.config/mac-transcribe/config.toml. Minimal key = "value"
/// parser — avoids pulling in a TOML dependency for what is a handful of
/// flat keys shared with the Python pipeline's mac_transcribe/config.py.
///
/// Keeps the raw key/value dict around (not just typed fields) so save()
/// preserves any keys this app doesn't know about yet (or pipeline-only
/// keys), rather than clobbering them.
struct AppConfig {
    private var raw: [String: String]

    static let configPath: URL = {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".config/mac-transcribe/config.toml")
    }()

    static let defaultRecordingsDir: URL = {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Recordings/mac-transcribe")
    }()

    // Mirrors mac_transcribe/config.py's DEFAULTS.
    private static let defaults: [String: String] = [
        "recordings_dir": defaultRecordingsDir.path,
        "whisper_model": "mlx-community/whisper-large-v3-turbo",
        "outline_backend": "bedrock",
        "bedrock_model": "global.anthropic.claude-sonnet-5",
        "bedrock_region": "us-east-1",
        "bedrock_profile": "default",
        "mlx_outline_model": "mlx-community/Qwen3.5-4B-MLX-4bit",
        "auto_rename_with_ai_title": "true",
        "prevent_sleep_while_recording": "true",
    ]

    static func load() -> AppConfig {
        var values = defaults

        if let text = try? String(contentsOf: configPath, encoding: .utf8) {
            for rawLine in text.split(separator: "\n") {
                let line = rawLine.trimmingCharacters(in: .whitespaces)
                guard !line.isEmpty, !line.hasPrefix("#"), let eq = line.firstIndex(of: "=") else { continue }
                let key = line[line.startIndex..<eq].trimmingCharacters(in: .whitespaces)
                var value = line[line.index(after: eq)...].trimmingCharacters(in: .whitespaces)
                value = value.trimmingCharacters(in: CharacterSet(charactersIn: "\""))
                values[key] = value
            }
        }

        return AppConfig(raw: values)
    }

    func save() throws {
        let dir = Self.configPath.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        // Write in the same order as Python's DEFAULTS so the file reads the
        // same regardless of which side (Swift or Python) wrote it last, plus
        // any keys this app doesn't recognize (forward-compat with pipeline
        // config additions this Swift copy hasn't been updated for yet).
        var lines: [String] = []
        var written = Set<String>()
        for key in ["recordings_dir", "whisper_model", "outline_backend", "bedrock_model",
                    "bedrock_region", "bedrock_profile", "mlx_outline_model", "auto_rename_with_ai_title",
                    "prevent_sleep_while_recording"] {
            lines.append(tomlLine(key: key, value: raw[key] ?? Self.defaults[key] ?? ""))
            written.insert(key)
        }
        for (key, value) in raw where !written.contains(key) {
            lines.append(tomlLine(key: key, value: value))
        }

        try lines.joined(separator: "\n").write(to: Self.configPath, atomically: true, encoding: .utf8)
    }

    private func tomlLine(key: String, value: String) -> String {
        if value == "true" || value == "false" {
            return "\(key) = \(value)"
        }
        return "\(key) = \"\(value)\""
    }

    // MARK: - Typed accessors

    var recordingsDir: URL {
        get { URL(fileURLWithPath: ((raw["recordings_dir"] ?? Self.defaults["recordings_dir"]!) as NSString).expandingTildeInPath) }
        set { raw["recordings_dir"] = newValue.path }
    }

    var autoRenameWithAITitle: Bool {
        get { raw["auto_rename_with_ai_title"] == "true" }
        set { raw["auto_rename_with_ai_title"] = newValue ? "true" : "false" }
    }

    /// When true (default), Start Recording holds an IOKit assertion that
    /// prevents system sleep — including with the lid closed, no external
    /// display needed — for as long as the recording runs, released
    /// automatically on Stop Recording or app quit. See SleepAssertion.swift.
    var preventSleepWhileRecording: Bool {
        get { raw["prevent_sleep_while_recording"] != "false" }
        set { raw["prevent_sleep_while_recording"] = newValue ? "true" : "false" }
    }

    var whisperModel: String {
        get { raw["whisper_model"] ?? Self.defaults["whisper_model"]! }
        set { raw["whisper_model"] = newValue }
    }

    var outlineBackend: OutlineBackend {
        get { OutlineBackend(rawValue: raw["outline_backend"] ?? "") ?? .bedrock }
        set { raw["outline_backend"] = newValue.rawValue }
    }

    var bedrockModel: String {
        get { raw["bedrock_model"] ?? Self.defaults["bedrock_model"]! }
        set { raw["bedrock_model"] = newValue }
    }

    var bedrockRegion: String {
        raw["bedrock_region"] ?? Self.defaults["bedrock_region"]!
    }

    var mlxOutlineModel: String {
        get { raw["mlx_outline_model"] ?? Self.defaults["mlx_outline_model"]! }
        set { raw["mlx_outline_model"] = newValue }
    }

    /// What to show the user as "currently configured for outline generation" —
    /// combines backend + model + a local/cloud label in one line.
    var outlineModelSummary: String {
        switch outlineBackend {
        case .bedrock:
            let label = BedrockModelOption.recommended.first { $0.id == bedrockModel }?.label ?? bedrockModel
            return "\(label) (Bedrock, cloud)"
        case .mlxLM:
            let label = MLXModelOption.recommended.first { $0.id == mlxOutlineModel }?.label ?? mlxOutlineModel
            return "\(label) (local)"
        }
    }

    var transcriptionModelSummary: String {
        "\(whisperModel) (local)"
    }
}
