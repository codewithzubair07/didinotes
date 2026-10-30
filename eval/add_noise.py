#!/usr/bin/env python3
"""Add acoustic noise to an audio file at a specified Signal-to-Noise Ratio (SNR).

Uses only standard library (wave, argparse, pathlib) and numpy.
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mix noise into a WAV audio file at a target SNR.")
    parser.add_argument("--clean", type=Path, required=True, help="Path to clean WAV file")
    parser.add_argument("--noise", type=Path, required=True, help="Path to noise WAV file")
    parser.add_argument(
        "--snr",
        type=float,
        default=10.0,
        help="Target Signal-to-Noise Ratio in decibels (dB), e.g. 15, 10, 5, 0",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to output mixed WAV file",
    )
    return parser.parse_args()


def read_wav(path: Path) -> tuple[np.ndarray, int, int, int]:
    """Read a WAV file and return (samples_float, nchannels, sampwidth, framerate)."""
    with wave.open(str(path), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        raw_bytes = wf.readframes(nframes)

    if sampwidth == 2:
        dtype = np.int16
    elif sampwidth == 1:
        dtype = np.uint8
    elif sampwidth == 4:
        dtype = np.int32
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth} bytes in {path}")

    data = np.frombuffer(raw_bytes, dtype=dtype).astype(np.float64)

    # Convert unsigned 8-bit to centered signed range if needed
    if sampwidth == 1:
        data = (data - 128.0) * 256.0

    return data, nchannels, sampwidth, framerate


def write_wav(
    path: Path, data: np.ndarray, nchannels: int, sampwidth: int, framerate: int
) -> None:
    """Save floating-point samples to a PCM WAV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if sampwidth == 2:
        clipped = np.clip(data, -32768.0, 32767.0).astype(np.int16)
        out_bytes = clipped.tobytes()
    elif sampwidth == 1:
        scaled = np.clip(data / 256.0 + 128.0, 0.0, 255.0).astype(np.uint8)
        out_bytes = scaled.tobytes()
    elif sampwidth == 4:
        clipped = np.clip(data, -2147483648.0, 2147483647.0).astype(np.int32)
        out_bytes = clipped.tobytes()
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth} bytes")

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(out_bytes)


def mix_noise_at_snr(
    clean: np.ndarray,
    noise: np.ndarray,
    snr_db: float,
) -> np.ndarray:
    """Mix clean signal and noise array at the target SNR (dB).

    SNR = 10 * log10(Power_signal / Power_noise)
    """
    clean_len = len(clean)
    noise_len = len(noise)
    if noise_len == 0:
        raise ValueError("Noise array is empty.")
    if clean_len == 0:
        raise ValueError("Clean signal array is empty.")

    # Match noise length to clean audio
    if noise_len < clean_len:
        repeats = int(np.ceil(clean_len / noise_len))
        noise_matched = np.tile(noise, repeats)[:clean_len]
    else:
        noise_matched = noise[:clean_len]

    # Calculate powers
    clean_power = np.mean(clean**2)
    noise_power = np.mean(noise_matched**2)

    if clean_power == 0:
        # If clean signal is completely silent, return noise directly
        return noise_matched

    if noise_power == 0:
        # If noise is completely silent, return clean signal
        return clean.copy()

    # Calculate required noise scaling factor alpha
    # target_noise_power = clean_power / (10 ** (snr_db / 10))
    # alpha = sqrt(target_noise_power / noise_power)
    target_noise_power = clean_power / (10.0 ** (snr_db / 10.0))
    alpha = np.sqrt(target_noise_power / noise_power)

    scaled_noise = alpha * noise_matched
    mixed = clean + scaled_noise
    return mixed


def add_noise(
    clean_path: Path,
    noise_path: Path,
    snr_db: float,
    output_path: Path,
) -> None:
    """Read clean audio and noise audio, mix at target SNR, and write to output path."""
    clean_data, nchannels, sampwidth, framerate = read_wav(clean_path)
    noise_data, _, _, noise_framerate = read_wav(noise_path)

    if framerate != noise_framerate:
        # Resample noise using linear interpolation if sample rates differ
        num_target_samples = int(len(noise_data) * (framerate / noise_framerate))
        x_orig = np.linspace(0, 1, len(noise_data))
        x_target = np.linspace(0, 1, num_target_samples)
        noise_data = np.interp(x_target, x_orig, noise_data)

    mixed = mix_noise_at_snr(clean_data, noise_data, snr_db)
    write_wav(output_path, mixed, nchannels, sampwidth, framerate)


def main() -> None:
    args = parse_args()
    add_noise(args.clean, args.noise, args.snr, args.output)
    print(f"Mixed {args.clean.name} + {args.noise.name} at {args.snr} dB SNR -> {args.output}")


if __name__ == "__main__":
    main()
