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

            let (peaks, peakDB) = try decodePeaks(asset: asset, track: track)
            rec.peaks = peaks
            rec.peakDB = peakDB
        } catch {
            rec.error = error.localizedDescription
        }
        return rec
    }

    /// Reads the track down-mixed to mono Int16 PCM and reduces it to
    /// `buckets` max-abs values, same approach as the Python version's
    /// ffmpeg pipe + np.array_split (just without the subprocess).
    private static func decodePeaks(asset: AVAsset, track: AVAssetTrack) throws -> ([Float], Double?) {
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

        var samples: [Int16] = []
        while let buffer = output.copyNextSampleBuffer() {
            guard let blockBuffer = CMSampleBufferGetDataBuffer(buffer) else { continue }
            let length = CMBlockBufferGetDataLength(blockBuffer)
            var data = [UInt8](repeating: 0, count: length)
            CMBlockBufferCopyDataBytes(blockBuffer, atOffset: 0, dataLength: length, destination: &data)
            data.withUnsafeBytes { raw in
                let int16Buf = raw.bindMemory(to: Int16.self)
                samples.append(contentsOf: int16Buf)
            }
        }
        if reader.status == .failed {
            throw reader.error ?? NSError(domain: "WaveformExtractor", code: -2)
        }
        if samples.isEmpty { return ([], nil) }

        let bucketCount = min(buckets, samples.count)
        let chunkSize = max(1, samples.count / bucketCount)
        var rawPeaks: [Float] = []
        rawPeaks.reserveCapacity(bucketCount)
        var i = 0
        while i < samples.count {
            let end = min(i + chunkSize, samples.count)
            var maxV: Int16 = 0
            for s in samples[i..<end] { maxV = max(maxV, s == .min ? .max : abs(s)) }
            rawPeaks.append(Float(maxV))
            i = end
        }
        let top = rawPeaks.max() ?? 0
        let peakDB: Double? = top > 0 ? 20 * log10(Double(top) / 32768) : nil
        let normalized = rawPeaks.map { top > 0 ? $0 / top : 0 }
        return (normalized, peakDB.map { (($0 * 10).rounded() / 10) })
    }
}
