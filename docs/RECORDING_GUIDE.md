# ASHA Diary Speech Recording & Dataset Collection Guide

This guide describes how to record, format, transcribe, and benchmark a 30 to 40 clip real-speech evaluation dataset for DidiNotes (ASHA Diary) in West Bengal.

---

## 1. Compliance, Privacy & Data Rules

> [!IMPORTANT]
> **Check Competition & Institutional Data Rules First**:
> Before collecting or recording any audio, verify the competition's privacy terms and your institution's data governance policies.

1. **Informed Consent**: If anyone other than yourself speaks in any recording, obtain explicit informed consent for their voice to be used strictly for technical benchmarking.
2. **Zero Real Patient Data**:
   - **NEVER** speak real patient or community member names, phone numbers, addresses, Aadhaar numbers, or real clinical histories.
   - All references to beneficiaries **must be synthetic single initials** (e.g. *"Rina"* -> `"R"`, *"Sita"* -> `"S"`) or synthetic alphanumeric IDs (e.g. `"R12"`, `"B4"`).
3. **Recordings Never Committed to Git**:
   - Audio files (`*.wav`, `*.mp3`, `*.ogg`, `*.webm`) and the directory `eval/audio/` are included in `.gitignore`.
   - Never commit raw recordings, background noise recordings, or transcripts containing personal identifiable information.

---

## 2. Recording Target & Audio Specifications

- **Total Clips**: 30 to 40 short audio recordings.
- **Duration**: 5 to 20 seconds per clip (hard limit on Gnani STT is 30 seconds; keep clips under 25 seconds).
- **Format**:
  - Container: **WAV** (`audio/wav`)
  - Sample Rate: **16,000 Hz (16 kHz)**
  - Channels: **1 (Mono)**
  - Bit Depth: **16-bit PCM** (linear signed integer)
- **Equipment**: Standard mobile phone microphone (e.g. default Android/iOS voice recorder app or browser recorder), simulating how an ASHA health worker would hold her phone in the field.

---

## 3. Linguistic & Acoustic Mix

### Acoustic Conditions (50 / 50 Mix)
- **15–20 Quiet Clips**: Recorded indoors (e.g. quiet room, sub-centre office) with minimal ambient noise.
- **15–20 Realistic Background Noise Clips**: Recorded in realistic rural field environments:
  - Ceiling fan or pedestal fan hum
  - Distant village courtyard chatter or children playing
  - Road/traffic ambient sounds (passing motorized rickshaws/autos)
  - Clinic waiting room background murmurs

### Linguistic Mix (Bengali & Benglish)
ASHA workers frequently codemix Bengali grammatical structures with common English health terms:
- **Bengali script & spoken Bengali**:
  - *"আজ রিনা-র ANC ভিজিট করলাম, ২ জন বাচ্চার পোলিও টিকা দিলাম"*
  - *"কাল সুমিতা-র বাড়ি গিয়ে PNC চেক করলাম"*
  - *"আজ ৫ জন কিশোরীকে আয়রন ট্যাবলেট দিলাম"*
- **Benglish (Romanised / Codemixed)**:
  - *"aaj Rina ANC visit korlam, 2 jon"*
  - *"kal Sita-r barite PNC korlam"*
  - *"aaj 3 jon baccha ke vaccination dilam"*
  - *"R12-r delivery case hospital-e pathalam"*

---

## 4. Directory Structure & File Naming

Place clean, un-augmented recordings inside `eval/audio/clean/`:

```
eval/
└── audio/
    ├── clean/
    │   ├── clip_001.wav
    │   ├── clip_002.wav
    │   └── ...
    ├── noisy/             (generated automatically by make_noisy_set.py)
    │   ├── clip_001_snr20db.wav
    │   ├── clip_001_snr10db.wav
    │   └── ...
    └── manifest.jsonl
```

- Clean clips: `clip_001.wav` to `clip_040.wav`.
- Never use personal names in filenames.

---

## 5. Manifest Format (`eval/audio/manifest.jsonl`)

The dataset manifest is a JSON Lines (`.jsonl`) file stored at `eval/audio/manifest.jsonl`. Each line represents one clip with reference transcript and expected structured extraction entries.

### Required Fields
- `file`: Path relative to `eval/audio/` (e.g. `"clean/clip_001.wav"`).
- `reference`: Ground-truth transcript as spoken (Bengali script or Benglish).
- `noise_label`: `"clean"` for clean clips, or SNR tag (e.g. `"snr_20db"`, `"snr_10db"`, `"snr_5db"`).
- `expected_entries`: Array of expected structured records:
  - `task_type`: Task identifier (e.g. `anc_visit`, `pnc_visit`, `immunization`, `delivery_hospital`, `hb_iron`, `general_survey`).
  - `count`: Integer number of beneficiaries/services.
  - `event_date`: ISO format date (`YYYY-MM-DD`).
  - `beneficiary_ref`: Initial or ID (e.g. `"R"`, `"S"`, `"R12"`), or `null`.

### Example Line
```json
{"file": "clean/clip_001.wav", "reference": "aaj Rina ANC visit korlam, 2 jon", "noise_label": "clean", "expected_entries": [{"task_type": "anc_visit", "count": 2, "event_date": "2026-11-01", "beneficiary_ref": "R"}]}
```

---

## 6. Execution Workflow

### Step 1: Verify Dry Run First
Ensure tooling detects your clips and manifest without making live API calls:
```powershell
python eval/run_stt_eval.py --dry-run --configs eval/stt_configs.json
```

### Step 2: Generate Noisy Test Sets (Optional)
If you have a background noise WAV file (e.g. `field_noise.wav`):
```powershell
python eval/make_noisy_set.py --noise field_noise.wav
```
This automatically produces 20 dB, 10 dB, and 5 dB SNR variants in `eval/audio/noisy/` and extends `manifest.jsonl`.

### Step 3: Run STT Benchmark Across Configurations
Run sequential evaluation across the 7 candidate Gnani configurations with a safety cap on API calls:
```powershell
python eval/run_stt_eval.py --configs eval/stt_configs.json --max-calls 50
```
Reports are automatically saved in `eval/results/` as JSON and Markdown.

### Step 4: Run End-to-End Extraction Evaluation
Compare audio transcription and extraction accuracy against text-only baselines:
```powershell
python eval/run_e2e_eval.py
```
This isolates the cost of speech recognition errors on downstream diary records.

