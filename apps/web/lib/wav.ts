/**
 * Client-side 16 kHz Mono 16-bit PCM WAV recording and encoding utilities.
 * Uses only browser Web Audio / MediaRecorder APIs without third-party dependencies.
 */

export interface WavHeaderInfo {
  format: number;
  channels: number;
  sampleRate: number;
  byteRate: number;
  blockAlign: number;
  bitsPerSample: number;
  dataSize: number;
}

/**
 * Pure linear interpolation resampler for Float32Array samples.
 * Can execute in both Node.js test environments and browser environments.
 */
export function resampleLinear(
  input: Float32Array,
  inputRate: number,
  targetRate = 16000,
): Float32Array {
  if (inputRate === targetRate || input.length === 0) {
    return new Float32Array(input);
  }
  const ratio = inputRate / targetRate;
  const targetLength = Math.round(input.length / ratio);
  const output = new Float32Array(targetLength);

  for (let i = 0; i < targetLength; i++) {
    const srcIndex = i * ratio;
    const low = Math.floor(srcIndex);
    const high = Math.min(low + 1, input.length - 1);
    const weight = srcIndex - low;
    output[i] = input[low] * (1 - weight) + input[high] * weight;
  }
  return output;
}

/**
 * Encodes a Float32Array of mono audio samples into a 16-bit PCM WAV ArrayBuffer.
 */
export function encodeWav(samples: Float32Array, sampleRate = 16000): ArrayBuffer {
  const numChannels = 1;
  const bitsPerSample = 16;
  const bytesPerSample = bitsPerSample / 8;
  const blockAlign = numChannels * bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataSize = samples.length * bytesPerSample;
  const bufferSize = 44 + dataSize;

  const buffer = new ArrayBuffer(bufferSize);
  const view = new DataView(buffer);

  // Helper to write ASCII strings into DataView
  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  // RIFF header
  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true); // ChunkSize: total file size - 8
  writeString(8, "WAVE");

  // "fmt " sub-chunk
  writeString(12, "fmt ");
  view.setUint32(16, 16, true); // Subchunk1Size (16 for PCM)
  view.setUint16(20, 1, true); // AudioFormat (1 = PCM)
  view.setUint16(22, numChannels, true); // NumChannels (1 = Mono)
  view.setUint32(24, sampleRate, true); // SampleRate (16000)
  view.setUint32(28, byteRate, true); // ByteRate (32000)
  view.setUint16(32, blockAlign, true); // BlockAlign (2)
  view.setUint16(34, bitsPerSample, true); // BitsPerSample (16)

  // "data" sub-chunk
  writeString(36, "data");
  view.setUint32(40, dataSize, true); // Subchunk2Size

  // 16-bit PCM samples (little-endian)
  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    // Clamp to [-1.0, 1.0]
    const s = Math.max(-1.0, Math.min(1.0, samples[i]));
    const sampleInt16 = s < 0 ? s * 0x8000 : s * 0x7fff;
    view.setInt16(offset, Math.round(sampleInt16), true);
    offset += 2;
  }

  return buffer;
}

/**
 * Parses and validates the standard 44-byte header of a PCM WAV file.
 */
export function parseWavHeader(buffer: ArrayBuffer): WavHeaderInfo {
  if (buffer.byteLength < 44) {
    throw new Error(`WAV buffer too small: ${buffer.byteLength} bytes (expected >= 44)`);
  }
  const view = new DataView(buffer);
  const readString = (offset: number, length: number) => {
    let str = "";
    for (let i = 0; i < length; i++) {
      str += String.fromCharCode(view.getUint8(offset + i));
    }
    return str;
  };

  const riff = readString(0, 4);
  const wave = readString(8, 4);
  const fmt = readString(12, 4);
  const data = readString(36, 4);

  if (riff !== "RIFF" || wave !== "WAVE") {
    throw new Error(`Invalid WAV format magic: RIFF="${riff}", WAVE="${wave}"`);
  }
  if (fmt !== "fmt ") {
    throw new Error(`Expected fmt chunk, got "${fmt}"`);
  }
  if (data !== "data") {
    throw new Error(`Expected data chunk, got "${data}"`);
  }

  return {
    format: view.getUint16(20, true),
    channels: view.getUint16(22, true),
    sampleRate: view.getUint32(24, true),
    byteRate: view.getUint32(28, true),
    blockAlign: view.getUint16(32, true),
    bitsPerSample: view.getUint16(34, true),
    dataSize: view.getUint32(40, true),
  };
}

/**
 * Resamples an AudioBuffer to 16 kHz Mono and encodes to WAV using OfflineAudioContext.
 */
export async function resampleAndEncodeToWav(audioBuffer: AudioBuffer): Promise<Blob> {
  const targetRate = 16000;
  const numChannels = 1;
  const duration = audioBuffer.duration;
  const targetLength = Math.max(1, Math.ceil(duration * targetRate));

  // If available, use OfflineAudioContext for high-quality browser resampling
  const OfflineCtxClass =
    typeof window !== "undefined"
      ? window.OfflineAudioContext ||
        (window as unknown as { webkitOfflineAudioContext: typeof OfflineAudioContext })
          .webkitOfflineAudioContext
      : null;

  if (OfflineCtxClass) {
    try {
      const offlineCtx = new OfflineCtxClass(numChannels, targetLength, targetRate);
      const source = offlineCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(offlineCtx.destination);
      source.start(0);

      const renderedBuffer = await offlineCtx.startRendering();
      const monoSamples = renderedBuffer.getChannelData(0);
      const wavArrayBuffer = encodeWav(monoSamples, targetRate);
      return new Blob([wavArrayBuffer], { type: "audio/wav" });
    } catch {
      // Fallback to pure linear resampling below
    }
  }

  // Fallback: extract channel 0 and resample linearly
  const monoSamples = audioBuffer.getChannelData(0);
  const resampled = resampleLinear(monoSamples, audioBuffer.sampleRate, targetRate);
  const wavArrayBuffer = encodeWav(resampled, targetRate);
  return new Blob([wavArrayBuffer], { type: "audio/wav" });
}

/**
 * Converts a recorded audio Blob (e.g. from MediaRecorder) to a 16 kHz mono 16-bit PCM WAV Blob.
 */
export async function convertBlobTo16kMonoWav(blob: Blob): Promise<Blob> {
  if (typeof window === "undefined") {
    throw new Error("convertBlobTo16kMonoWav is only supported in browser environments.");
  }

  const arrayBuffer = await blob.arrayBuffer();
  const AudioCtxClass =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;

  if (!AudioCtxClass) {
    throw new Error("Web Audio API is not supported in this browser.");
  }

  const audioCtx = new AudioCtxClass();
  try {
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer.slice(0));
    return await resampleAndEncodeToWav(audioBuffer);
  } finally {
    try {
      await audioCtx.close();
    } catch {
      // Ignore close errors
    }
  }
}

