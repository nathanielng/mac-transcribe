import AVFoundation
import Foundation

/// Native replacement for iPhone-Recorder/visualize.py's ffmpeg+numpy peak
/// extraction: decode the file to mono PCM via AVAssetReader, bucket into
/// a fixed number of bars, keep each bucket's max absolute sample. No
/// ffmpeg/ffprobe dependency to bundle or shell out to.
enum WaveformExtractor {
    static let buckets = 240

    /// Runs on a background thread — AVAssetReader decoding a multi-hour
    /// file is not instant, and this must never block the UI.
    static func analyse(url: URL) async -> Recording {
        let attrs = try? FileManager.default.attributesOfItem(atPath: url.path)
        let size = (attrs?[.size] as? Int64) ?? 0
        let mtime = (attrs?[.modificationDate] as? Date) ?? Date()
        var rec = Recording(url: url, size: size, mtime: mtime)

        if size == 0 {
            rec.error = "Empty file (0 bytes)"
            return rec
        }

        let asset = AVURLAsset(url: url)
        do {
            let duration = try await asset.load(.duration)
            rec.duration = duration.seconds.isFinite ? duration.seconds : 0
            guard let track = try await asset.loadTracks(withMediaType: .audio).first else {
                rec.error = "No audio stream found"
                return rec
            }
            let formatDescs = try await track.load(.formatDescriptions)
            if let fmt = formatDescs.first,
               let basic = CMAudioFormatDescriptionGetStreamBasicDescription(fmt) {
                rec.sampleRate = basic.pointee.mSampleRate
                rec.channels = Int(basic.pointee.mChannelsPerFrame)
            }

            let estimatedSamples = Int(rec.duration * max(rec.sampleRate, 1))
            let (peaks, peakDB) = try await decodePeaksOffPool(
                asset: asset, track: track, estimatedSampleCount: estimatedSamples
            )
            rec.peaks = peaks
            rec.peakDB = peakDB
        } catch {
            rec.error = error.localizedDescription
        }
        return rec
    }

    /// `decodePeaks` below blocks synchronously on `copyNextSampleBuffer()`
    /// in a tight loop. Calling that directly from an async Task (as a
    /// previous version did) ran it on Swift's cooperative thread pool,
    /// whose thread count is capped near the core count — with enough
    /// concurrent analyse() calls in flight, every pool thread ends up
    /// stuck in that blocking loop simultaneously, and `asset.load(...)`'s
    /// own internal continuations (needed to even get this far) can no
    /// longer find a thread to resume on: a real deadlock seen in testing
    /// (all tasks stuck mid-analysis, zero completions for 60s+ on files
    /// that decode in under a second standalone). Dispatching the blocking
    /// work onto a plain GCD queue via a continuation keeps it off that
    /// pool entirely.
    private static func decodePeaksOffPool(
        asset: AVAsset, track: AVAssetTrack, estimatedSampleCount: Int
    ) async throws -> ([Float], Double?) {
        try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    continuation.resume(returning: try decodePeaks(
                        asset: asset, track: track, estimatedSampleCount: estimatedSampleCount
                    ))
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    /// Reads the track down-mixed to mono Int16 PCM and reduces it to
    /// `buckets` max-abs values, same approach as the Python version's
    /// ffmpeg pipe + np.array_split — but bucketed incrementally as each
    /// `CMSampleBuffer` streams in, rather than first collecting every
    /// decoded sample into one `[Int16]` via repeated `append(contentsOf:)`.
    /// That first version was fine for short clips but effectively hung on
    /// a real ~5.7-hour, 494MB recording in testing: ~1 billion samples
    /// means ~2GB of reallocating array growth before a single bucket is
    /// computed. Bucketing on the fly keeps memory bounded to the bucket
    /// array regardless of file length. `estimatedSampleCount` (duration ×
    /// sample rate, both already known from the asset) sizes the buckets
    /// upfront; being slightly off from the true decoded count just shifts
    /// the last bucket's boundary, which is invisible at 240 bars wide.
    private static func decodePeaks(
        asset: AVAsset, track: AVAssetTrack, estimatedSampleCount: Int
    ) throws -> ([Float], Double?) {
        let reader = try AVAssetReader(asset: asset)
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsFloatKey: false,
            AVNumberOfChannelsKey: 1,
        ]
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: settings)
        reader.add(output)
        guard reader.startReading() else {
            throw reader.error ?? NSError(domain: "WaveformExtractor", code: -1)
        }

        let bucketCount = max(1, min(buckets, max(estimatedSampleCount, 1)))
        let chunkSize = max(1, estimatedSampleCount / bucketCount)
        var rawPeaks = [Float](repeating: 0, count: bucketCount)
        var sampleIndex = 0
        var overallMax: Int16 = 0

        while let buffer = output.copyNextSampleBuffer() {
            guard let blockBuffer = CMSampleBufferGetDataBuffer(buffer) else { continue }
            let length = CMBlockBufferGetDataLength(blockBuffer)
            var data = [UInt8](repeating: 0, count: length)
            CMBlockBufferCopyDataBytes(blockBuffer, atOffset: 0, dataLength: length, destination: &data)
            data.withUnsafeBytes { raw in
                for s in raw.bindMemory(to: Int16.self) {
                    let mag = s == .min ? Int16.max : abs(s)
                    let bucket = min(sampleIndex / chunkSize, bucketCount - 1)
                    if Float(mag) > rawPeaks[bucket] { rawPeaks[bucket] = Float(mag) }
                    if mag > overallMax { overallMax = mag }
                    sampleIndex += 1
                }
            }
        }
        if reader.status == .failed {
            throw reader.error ?? NSError(domain: "WaveformExtractor", code: -2)
        }
        if sampleIndex == 0 { return ([], nil) }

        let top = overallMax
        let peakDB: Double? = top > 0 ? 20 * log10(Double(top) / 32768) : nil
        let normalized = rawPeaks.map { top > 0 ? $0 / Float(top) : 0 }
        return (normalized, peakDB.map { (($0 * 10).rounded() / 10) })
    }
}
