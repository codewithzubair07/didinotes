"use client";

import { useEffect, useRef, useState } from "react";
import { api, errorText, type Entry, type TurnResponse } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { todayIso } from "@/lib/date";
import { speakBrowser, playBase64Audio } from "@/lib/speech";
import { convertBlobTo16kMonoWav } from "@/lib/wav";

const DEV_PANEL = process.env.NEXT_PUBLIC_DEV_PANEL === "true";

function sessionId(): string {
  const key = "asha_session";
  let id = window.localStorage.getItem(key);
  if (!id) {
    id = Math.random().toString(36).slice(2, 12);
    window.localStorage.setItem(key, id);
  }
  return id;
}

export default function TalkPage() {
  const { lang, t } = useLang();
  const [turn, setTurn] = useState<TurnResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [recording, setRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [micOk, setMicOk] = useState(true);
  const [needsManualPlay, setNeedsManualPlay] = useState(false);
  const [today, setToday] = useState<Entry[]>([]);
  const [loadingToday, setLoadingToday] = useState(true);
  const [todayError, setTodayError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const loadToday = () => {
    setLoadingToday(true);
    setTodayError(null);
    api
      .entriesOn(todayIso())
      .then(setToday)
      .catch((err: unknown) => setTodayError(errorText(err, lang, t("offline"), t("error"))))
      .finally(() => setLoadingToday(false));
  };

  useEffect(() => {
    loadToday();
    setMicOk(typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!turn) {
      setNeedsManualPlay(false);
      return;
    }
    if (turn.response_audio) {
      playBase64Audio(turn.response_audio).then((played) => {
        setNeedsManualPlay(!played);
      });
    } else {
      setNeedsManualPlay(false);
      if (turn.ui_hint !== "refusal") {
        speakBrowser(turn.response_text, lang === "bn" ? "bn-IN" : "en-IN");
      }
    }
  }, [turn, lang]);

  const send = async (text: string) => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.turnText(sessionId(), text.trim(), lang);
      setTurn(result);
      if (result.ui_hint === "saved") loadToday();
    } catch (err) {
      setError(errorText(err, lang, t("offline"), t("error")));
    } finally {
      setBusy(false);
    }
  };

  const stopRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    setRecording(false);
  };

  const startRecording = async () => {
    if (busy) return;
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: 16000 },
      });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const rawBlob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        await sendAudio(rawBlob);
      };

      recorder.start(250);
      recorderRef.current = recorder;
      setRecording(true);
      setRecordSeconds(0);

      const startTime = Date.now();
      timerRef.current = setInterval(() => {
        const elapsedSec = Math.floor((Date.now() - startTime) / 1000);
        setRecordSeconds(elapsedSec);
        if (elapsedSec >= 29) {
          stopRecording();
        }
      }, 500);
    } catch (err: unknown) {
      setRecording(false);
      const isPermissionDenied =
        err instanceof Error &&
        (err.name === "NotAllowedError" || err.name === "PermissionDeniedError");
      if (isPermissionDenied) {
        setError(t("mic_denied"));
      } else {
        setMicOk(false);
        setError(t("mic_unavailable"));
      }
    }
  };

  const sendAudio = async (rawBlob: Blob) => {
    setBusy(true);
    setError(null);
    try {
      // Convert raw browser audio (WebM/OGG) to 16 kHz Mono 16-bit PCM WAV
      const wavBlob = await convertBlobTo16kMonoWav(rawBlob);

      const form = new FormData();
      form.append("session_id", sessionId());
      form.append("audio", wavBlob, "recording.wav");
      form.append("lang", lang);

      const response = await fetch("/api/turn", { method: "POST", body: form });
      if (!response.ok) {
        if (response.status === 429) {
          throw new Error(t("speech_busy"));
        }
        if (response.status === 402) {
          throw new Error(t("no_credit"));
        }
        if (response.status === 413) {
          throw new Error(t("recording_too_long"));
        }
        if (response.status >= 500) {
          throw new Error(t("service_error"));
        }
        const body = (await response.json().catch(() => null)) as {
          detail?: { bn: string; en: string };
        } | null;
        throw new Error(body?.detail?.[lang] ?? t("error"));
      }

      const result = (await response.json()) as TurnResponse;
      setTurn(result);
      if (result.ui_hint === "saved") loadToday();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  };

  const answer = (text: string) => {
    setTyped("");
    void send(text);
  };

  const showReadback = turn?.ui_hint === "confirm";

  return (
    <div className="space-y-4">
      <section className="space-y-3">
        <button
          type="button"
          disabled={!micOk || busy}
          onPointerDown={() => void startRecording()}
          onPointerUp={stopRecording}
          onPointerLeave={() => recording && stopRecording()}
          className={`h-40 w-full rounded-2xl border-4 border-black text-2xl font-bold transition-colors disabled:opacity-40 ${
            recording ? "bg-red-100 text-red-900 border-red-900 animate-pulse" : "bg-white"
          }`}
        >
          {recording ? (
            <div className="flex flex-col items-center gap-1">
              <span>{t("recording")}</span>
              <span className="text-lg font-mono font-semibold bg-red-200 px-3 py-0.5 rounded-full">
                {recordSeconds}s / 29s
              </span>
            </div>
          ) : (
            t("hold_to_talk")
          )}
        </button>
        {!micOk && <p className="font-bold text-red-700">{t("mic_unavailable")}</p>}

        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            answer(typed);
          }}
        >
          <input
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder={t("type_placeholder")}
            className="min-h-14 flex-1 rounded-lg border-2 border-black px-3 text-lg"
          />
          <button
            type="submit"
            disabled={busy}
            className="min-h-14 rounded-lg border-2 border-black px-4 font-bold"
          >
            {t("send")}
          </button>
        </form>
      </section>

      {busy && (
        <p role="status" className="font-bold">
          {t("loading")}
        </p>
      )}
      {error && (
        <p role="alert" className="border-2 border-black bg-yellow-50 p-3 font-bold text-red-900">
          {error}
        </p>
      )}

      {turn && (
        <section className="space-y-3 border-4 border-black p-3">
          <div className="flex items-start justify-between gap-2">
            <p className="text-lg">{turn.response_text}</p>
            {needsManualPlay && turn.response_audio && (
              <button
                type="button"
                onClick={() => {
                  if (turn.response_audio) {
                    playBase64Audio(turn.response_audio).then(() => setNeedsManualPlay(false));
                  }
                }}
                className="shrink-0 rounded-lg border-2 border-black bg-blue-100 px-3 py-1 font-bold text-sm shadow hover:bg-blue-200"
              >
                🔊 {t("tap_to_hear")}
              </button>
            )}
          </div>

          {showReadback && (
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                className="min-h-16 rounded-lg border-4 border-black text-xl font-bold hover:bg-gray-100"
                onClick={() => answer(lang === "bn" ? "হ্যাঁ" : "yes")}
              >
                {t("yes")}
              </button>
              <button
                type="button"
                className="min-h-16 rounded-lg border-4 border-black text-xl font-bold hover:bg-gray-100"
                onClick={() => answer(lang === "bn" ? "না" : "no")}
              >
                {t("no")}
              </button>
              <button
                type="button"
                className="min-h-16 rounded-lg border-4 border-black text-xl font-bold hover:bg-gray-100"
                onClick={() => answer(lang === "bn" ? "সংশোধন" : "change")}
              >
                {t("edit")}
              </button>
            </div>
          )}

          {DEV_PANEL && (
            <div className="border-t-2 border-black pt-2 text-xs space-y-1">
              <p className="font-bold text-sm uppercase tracking-wide">Developer Panel</p>
              <dl className="grid grid-cols-2 gap-x-2 gap-y-1">
                <dt className="font-semibold">STT Provider / Model:</dt>
                <dd className="font-mono">{turn.dev?.stt_model ?? turn.providers.stt}</dd>

                <dt className="font-semibold">STT Format:</dt>
                <dd className="font-mono">{turn.dev?.stt_format ?? "default"}</dd>

                <dt className="font-semibold">STT Latency:</dt>
                <dd className="font-mono">{turn.timings_ms.stt} ms</dd>

                <dt className="font-semibold">STT Request ID:</dt>
                <dd className="font-mono truncate" title={turn.dev?.stt_request_id ?? "none"}>
                  {turn.dev?.stt_request_id ?? "none"}
                </dd>

                <dt className="font-semibold">TTS Provider / Model:</dt>
                <dd className="font-mono">{turn.dev?.tts_model ?? turn.providers.tts}</dd>

                <dt className="font-semibold">TTS Voice:</dt>
                <dd className="font-mono">{turn.dev?.tts_voice ?? "n/a"}</dd>

                <dt className="font-semibold">TTS Latency:</dt>
                <dd className="font-mono">{turn.timings_ms.tts} ms</dd>

                <dt className="font-semibold">TTS Cache Hit:</dt>
                <dd className="font-mono">{turn.dev?.tts_cached ? "Yes (Hit)" : "No (Miss)"}</dd>

                <dt className="font-semibold">TTS Request ID:</dt>
                <dd className="font-mono truncate" title={turn.dev?.tts_request_id ?? "none"}>
                  {turn.dev?.tts_request_id ?? "none"}
                </dd>

                <dt className="font-semibold">TTS Fallback:</dt>
                <dd className="font-mono text-red-800">
                  {turn.tts_fallback ? `Yes (${turn.tts_fallback})` : "No"}
                </dd>

                <dt className="font-semibold">NLU Latency:</dt>
                <dd className="font-mono">{turn.timings_ms.nlu} ms</dd>

                <dt className="font-semibold">LLM Latency:</dt>
                <dd className="font-mono">{turn.timings_ms.llm ?? 0} ms</dd>
              </dl>
            </div>
          )}
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-xl font-bold">{t("today_entries")}</h2>
        {loadingToday && <p>{t("loading")}</p>}
        {todayError && (
          <div className="space-y-2">
            <p role="alert" className="font-bold">
              {todayError}
            </p>
            <button
              type="button"
              className="min-h-12 rounded-lg border-2 border-black px-4 font-bold"
              onClick={loadToday}
            >
              {t("retry")}
            </button>
          </div>
        )}
        {!loadingToday && !todayError && today.length === 0 && <p>{t("none_today")}</p>}
        <ul className="space-y-2">
          {today.map((entry) => (
            <li key={entry.id} className="border-2 border-black p-2">
              {entry.task_type} · {entry.count} · {entry.beneficiary_ref ?? "-"} · {entry.status}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
