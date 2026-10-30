"use client";

import { useEffect, useRef, useState } from "react";
import { api, errorText, type Entry, type TurnResponse } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { todayIso } from "@/lib/date";
import { speakBrowser, playBase64Audio } from "@/lib/speech";

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
  const [micOk, setMicOk] = useState(true);
  const [today, setToday] = useState<Entry[]>([]);
  const [loadingToday, setLoadingToday] = useState(true);
  const [todayError, setTodayError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!turn) return;
    if (turn.response_audio) playBase64Audio(turn.response_audio);
    else if (turn.ui_hint !== "refusal") speakBrowser(turn.response_text, lang === "bn" ? "bn-IN" : "en-IN");
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

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => chunksRef.current.push(event.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        await sendAudio(blob);
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      setMicOk(false);
    }
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setRecording(false);
  };

  const sendAudio = async (blob: Blob) => {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("session_id", sessionId());
      form.append("audio", blob, "turn.webm");
      form.append("lang", lang);
      const response = await fetch("/api/turn", { method: "POST", body: form });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: { bn: string; en: string } } | null;
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
          className="h-40 w-full rounded-2xl border-4 border-black text-2xl font-bold disabled:opacity-40"
        >
          {recording ? t("recording") : t("hold_to_talk")}
        </button>
        {!micOk && <p className="font-bold">{t("mic_unavailable")}</p>}

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
          <button type="submit" disabled={busy} className="min-h-14 rounded-lg border-2 border-black px-4 font-bold">
            {t("send")}
          </button>
        </form>
      </section>

      {busy && <p role="status" className="font-bold">{t("loading")}</p>}
      {error && (
        <p role="alert" className="border-2 border-black p-3 font-bold">
          {error}
        </p>
      )}

      {turn && (
        <section className="space-y-3 border-4 border-black p-3">
          <p className="text-lg">{turn.response_text}</p>
          {showReadback && (
            <div className="grid grid-cols-3 gap-2">
              <button type="button" className="min-h-16 rounded-lg border-4 border-black text-xl font-bold" onClick={() => answer(lang === "bn" ? "হ্যাঁ" : "yes")}>
                {t("yes")}
              </button>
              <button type="button" className="min-h-16 rounded-lg border-4 border-black text-xl font-bold" onClick={() => answer(lang === "bn" ? "না" : "no")}>
                {t("no")}
              </button>
              <button type="button" className="min-h-16 rounded-lg border-4 border-black text-xl font-bold" onClick={() => answer(lang === "bn" ? "সংশোধন" : "change")}>
                {t("edit")}
              </button>
            </div>
          )}
          {DEV_PANEL && (
            <dl className="grid grid-cols-2 gap-1 border-t-2 border-black pt-2 text-sm">
              <dt>STT</dt>
              <dd>
                {turn.providers.stt} {turn.timings_ms.stt}ms
              </dd>
              <dt>NLU</dt>
              <dd>{turn.timings_ms.nlu}ms</dd>
              <dt>TTS</dt>
              <dd>
                {turn.providers.tts} {turn.timings_ms.tts}ms
              </dd>
            </dl>
          )}
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-xl font-bold">{t("today_entries")}</h2>
        {loadingToday && <p>{t("loading")}</p>}
        {todayError && (
          <div className="space-y-2">
            <p role="alert" className="font-bold">{todayError}</p>
            <button type="button" className="min-h-12 rounded-lg border-2 border-black px-4 font-bold" onClick={loadToday}>
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
