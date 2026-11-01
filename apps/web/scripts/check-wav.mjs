#!/usr/bin/env node
/**
 * Minimal Node-based check script for client-side WAV encoding and resampling.
 * Verifies RIFF/WAVE header fields, PCM encoding, and resampling without third-party test runners.
 */

import assert from "node:assert";
import { encodeWav, parseWavHeader, resampleLinear } from "../lib/wav.ts";

console.log("=== Checking WAV Encoder & Resampler ===");

// 1. Test Header Correctness and 16 kHz Mono PCM structure
console.log("1. Verifying WAV Header structure...");
const sampleRate = 16000;
const numSamples = 16000; // 1 second of audio
const syntheticSamples = new Float32Array(numSamples);

// Generate 440 Hz test tone
for (let i = 0; i < numSamples; i++) {
  syntheticSamples[i] = Math.sin((2 * Math.PI * 440 * i) / sampleRate);
}

const buffer = encodeWav(syntheticSamples, sampleRate);
assert.strictEqual(buffer.byteLength, 44 + numSamples * 2, "Buffer length must be 44-byte header + 2 bytes per sample");

const header = parseWavHeader(buffer);
assert.strictEqual(header.format, 1, "Audio format must be 1 (PCM)");
assert.strictEqual(header.channels, 1, "Channel count must be 1 (Mono)");
assert.strictEqual(header.sampleRate, 16000, "Sample rate must be 16000 Hz");
assert.strictEqual(header.bitsPerSample, 16, "Bits per sample must be 16-bit");
assert.strictEqual(header.byteRate, 32000, "Byte rate must be 32000 bytes/sec (16000 * 1 * 2)");
assert.strictEqual(header.blockAlign, 2, "Block align must be 2 bytes (1 * 2)");
assert.strictEqual(header.dataSize, numSamples * 2, "Data chunk size must equal samples * 2");
console.log("   ✓ Header fields correct (PCM 16 kHz mono 16-bit)");

// 2. Test Sample Value Clamping and Int16 Conversion
console.log("2. Verifying sample clamping and 16-bit PCM encoding...");
const testEdgeSamples = new Float32Array([0.0, 1.0, -1.0, 1.5, -2.0, 0.5, -0.5]);
const edgeBuffer = encodeWav(testEdgeSamples, 16000);
const edgeView = new DataView(edgeBuffer);

const readInt16 = (sampleIndex) => edgeView.getInt16(44 + sampleIndex * 2, true);

assert.strictEqual(readInt16(0), 0, "0.0 float should encode to 0");
assert.strictEqual(readInt16(1), 32767, "1.0 float should encode to 32767 (0x7FFF)");
assert.strictEqual(readInt16(2), -32768, "-1.0 float should encode to -32768 (-0x8000)");
assert.strictEqual(readInt16(3), 32767, ">1.0 overflow float must be clamped to 32767");
assert.strictEqual(readInt16(4), -32768, "<-1.0 underflow float must be clamped to -32768");
assert.strictEqual(readInt16(5), Math.round(0.5 * 32767), "0.5 float should encode to ~16384");
assert.strictEqual(readInt16(6), Math.round(-0.5 * 32768), "-0.5 float should encode to -16384");
console.log("   ✓ Value clamping and 16-bit PCM precision correct");

// 3. Test Resampling (48 kHz -> 16 kHz)
console.log("3. Verifying linear resampler...");
const inputRate = 48000;
const targetRate = 16000;
const inputSamples = new Float32Array(4800); // 0.1s at 48 kHz
for (let i = 0; i < inputSamples.length; i++) {
  inputSamples[i] = Math.sin((2 * Math.PI * 100 * i) / inputRate);
}

const resampled = resampleLinear(inputSamples, inputRate, targetRate);
assert.strictEqual(resampled.length, 1600, "Resampling 48 kHz to 16 kHz must reduce sample count by 3x");

// Verify identity resampling (16 kHz -> 16 kHz)
const identity = resampleLinear(resampled, 16000, 16000);
assert.strictEqual(identity.length, resampled.length, "Identity resampling must preserve length");
console.log("   ✓ Resampling length and ratio verified");

// 4. Test 30-Second Size Bound Check
console.log("4. Verifying 30-second audio size limit...");
const thirtySecondsSamples = new Float32Array(30 * 16000);
const thirtySecBuffer = encodeWav(thirtySecondsSamples, 16000);
assert.strictEqual(thirtySecBuffer.byteLength, 44 + 30 * 16000 * 2, "30-second buffer must match expected size");
const thirtySecSizeMb = thirtySecBuffer.byteLength / (1024 * 1024);
console.log(`   ✓ 30-second 16 kHz mono WAV size: ${thirtySecBuffer.byteLength} bytes (~${thirtySecSizeMb.toFixed(2)} MB)`);
assert(thirtySecBuffer.byteLength < 1_000_000, "30-second audio must be under 1 MB limit (fits in 2 MB server limit)");

console.log("\nALL WAV ENCODER TESTS PASSED SUCCESSFULLY.\n");

