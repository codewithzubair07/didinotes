"use client";

import { useEffect, useState } from "react";
import { api, errorText, getBilingualTaskLabel, type Entry } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { todayIso } from "@/lib/date";

export default function DiaryPage() {
  const { lang, t } = useLang();
  const [date, setDate] = useState(todayIso());
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draftCount, setDraftCount] = useState("1");
  const [draftRef, setDraftRef] = useState("");

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .entriesOn(date)
      .then(setEntries)
      .catch((err: unknown) => setError(errorText(err, lang, t("offline"), t("error"))))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  const save = async (id: number) => {
    setError(null);
    try {
      await api.patchEntry(id, {
        count: Number(draftCount),
        beneficiary_ref: draftRef.trim() || null,
      });
      // An edit marks the entry "corrected"; re-confirm so it counts in the claim.
      await api.confirmEntry(id);
      setEditingId(null);
      load();
    } catch (err) {
      setError(errorText(err, lang, t("offline"), t("error")));
    }
  };

  const remove = async (id: number) => {
    if (!window.confirm(t("confirm_delete"))) return;
    setError(null);
    try {
      await api.deleteEntry(id);
      load();
    } catch (err) {
      setError(errorText(err, lang, t("offline"), t("error")));
    }
  };

  return (
    <div className="space-y-4">
      <label className="block space-y-1">
        <span className="font-bold">{t("date")}</span>
        <input
          type="date"
          value={date}
          max={todayIso()}
          onChange={(event) => setDate(event.target.value)}
          className="min-h-14 w-full rounded-lg border-2 border-black px-3 text-lg"
        />
      </label>

      {loading && <p role="status" className="font-bold">{t("loading")}</p>}
      {error && (
        <div className="space-y-2">
          <p role="alert" className="font-bold">{error}</p>
          <button type="button" className="min-h-12 rounded-lg border-2 border-black px-4 font-bold" onClick={load}>
            {t("retry")}
          </button>
        </div>
      )}
      {!loading && !error && entries.length === 0 && <p>{t("none_today")}</p>}

      <ul className="space-y-3">
        {entries.map((entry) => (
          <li key={entry.id} className="space-y-2 border-2 border-black p-3">
            <div>
              <span className="text-xs font-semibold uppercase text-gray-600 block">
                {lang === "bn" ? "কাজের বিবরণ / Task" : "Task / কাজের বিবরণ"}:
              </span>
              <span className="text-lg font-bold">
                {getBilingualTaskLabel(entry.task_type, entry.task_label_bn, entry.task_label_en)}
              </span>
            </div>
            <div className="grid grid-cols-4 gap-2 text-sm pt-1 border-t border-gray-200">
              <div>
                <span className="font-semibold text-gray-600 block">{t("date")}:</span>
                <span>{entry.event_date || "-"}</span>
              </div>
              <div>
                <span className="font-semibold text-gray-600 block">{t("count")}:</span>
                <span>{entry.count ?? "-"}</span>
              </div>
              <div>
                <span className="font-semibold text-gray-600 block">{t("beneficiary")}:</span>
                <span>{entry.beneficiary_ref || "-"}</span>
              </div>
              <div>
                <span className="font-semibold text-gray-600 block">
                  {lang === "bn" ? "অবস্থা" : "Status"}:
                </span>
                <span className="capitalize">{entry.status || "-"}</span>
              </div>
            </div>
            {entry.checklist && (
              <div className="rounded border border-gray-400 bg-gray-50 p-2 text-sm space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs uppercase tracking-wider text-gray-700">
                    {lang === "bn" ? "ভিজিট চেকলিস্ট" : "Visit Checklist"} (
                    {entry.checklist.checklist_id.toUpperCase()})
                  </span>
                  {entry.checklist.has_danger_sign && (
                    <span className="rounded bg-red-600 px-2 py-0.5 text-xs font-bold text-white">
                      ⚠️ {lang === "bn" ? "বিপদ লক্ষণ" : "Danger Sign"}
                    </span>
                  )}
                </div>
                <ul className="mt-1 divide-y divide-gray-200">
                  {Object.entries(entry.checklist.answers).map(([key, val]) => (
                    <li key={key} className="flex items-center justify-between py-1 text-xs">
                      <span className="text-gray-800">{val.text || key}:</span>
                      <span
                        className={`font-semibold ${
                          val.is_danger_sign && val.answer === "yes"
                            ? "font-bold text-red-700"
                            : ""
                        }`}
                      >
                        {String(val.answer)} {val.unit ?? ""}
                      </span>
                    </li>
                  ))}
                </ul>
                {entry.checklist.has_danger_sign && (
                  <div className="mt-2 rounded border border-red-500 bg-red-100 p-2 text-xs font-bold text-red-900">
                    ⚠️ {lang === "bn" ? "ANM বা ডাক্তারকে জানান" : "Please inform your ANM or doctor"}
                  </div>
                )}
              </div>
            )}
            {editingId === entry.id ? (
              <div className="space-y-2">
                <label className="block space-y-1">
                  <span>{t("count")}</span>
                  <input
                    type="number"
                    min={1}
                    max={99}
                    value={draftCount}
                    onChange={(event) => setDraftCount(event.target.value)}
                    className="min-h-12 w-full rounded-lg border-2 border-black px-3"
                  />
                </label>
                <label className="block space-y-1">
                  <span>{t("beneficiary")}</span>
                  <input
                    value={draftRef}
                    onChange={(event) => setDraftRef(event.target.value)}
                    placeholder="R"
                    className="min-h-12 w-full rounded-lg border-2 border-black px-3"
                  />
                </label>
                <div className="flex gap-2">
                  <button type="button" className="min-h-12 flex-1 rounded-lg border-2 border-black font-bold" onClick={() => void save(entry.id)}>
                    {t("save")}
                  </button>
                  <button type="button" className="min-h-12 flex-1 rounded-lg border-2 border-black font-bold" onClick={() => setEditingId(null)}>
                    {t("cancel")}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <button
                  type="button"
                  className="min-h-12 flex-1 rounded-lg border-2 border-black font-bold"
                  onClick={() => {
                    setEditingId(entry.id);
                    setDraftCount(String(entry.count));
                    setDraftRef(entry.beneficiary_ref ?? "");
                  }}
                >
                  {t("edit")}
                </button>
                <button type="button" className="min-h-12 flex-1 rounded-lg border-2 border-black font-bold" onClick={() => void remove(entry.id)}>
                  {t("delete")}
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
