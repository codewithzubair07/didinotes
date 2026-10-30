"use client";

import { useEffect, useState } from "react";
import { api, errorText, type Claim } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { currentMonthIso } from "@/lib/date";

export default function ClaimPage() {
  const { lang, t } = useLang();
  const [month, setMonth] = useState(currentMonthIso());
  const [claim, setClaim] = useState<Claim | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .claim(month)
      .then(setClaim)
      .catch((err: unknown) => setError(errorText(err, lang, t("offline"), t("error"))))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  const copyRegister = async () => {
    if (!claim) return;
    await navigator.clipboard.writeText(claim.register_lines.join("\n"));
    setCopied(true);
  };

  const label = (row: Claim["rows"][number]) => (lang === "bn" ? row.task_label_bn : row.task_label_en);

  return (
    <div className="space-y-4">
      <label className="block space-y-1">
        <span className="font-bold">{t("month")}</span>
        <input
          type="month"
          value={month}
          onChange={(event) => setMonth(event.target.value)}
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

      {claim && !loading && !error && (
        <>
          <table className="w-full border-2 border-black text-left">
            <thead>
              <tr className="border-b-2 border-black">
                <th className="p-2">{t("task")}</th>
                <th className="p-2">{t("count")}</th>
                <th className="p-2">{t("total")}</th>
              </tr>
            </thead>
            <tbody>
              {claim.rows.map((row) => (
                <tr key={row.task_type} className="border-b border-black">
                  <td className="p-2">{label(row)}</td>
                  <td className="p-2">{row.entry_count}</td>
                  <td className="p-2">{row.amount_inr ?? t("not_configured")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="font-bold">
            {t("total")}: {claim.total_inr ?? t("not_configured")}
          </p>

          <h2 className="text-xl font-bold">{t("attention")}</h2>
          {claim.attention.length === 0 && <p>-</p>}
          <ul className="space-y-2">
            {claim.attention.map((entry) => (
              <li key={entry.id} className="border-2 border-black p-2">
                {entry.event_date} · {lang === "bn" ? entry.task_label_bn : entry.task_label_en}
                {entry.missing_documents.length > 0 && (
                  <span className="block font-bold">
                    {t("missing_docs")}: {entry.missing_documents.join(", ")}
                  </span>
                )}
                <span className="block text-sm">{entry.attention_reasons.join(", ")}</span>
              </li>
            ))}
          </ul>

          {claim.entries.length === 0 && <p>{t("no_entries")}</p>}

          <div className="grid grid-cols-1 gap-2">
            <a
              className="block min-h-14 rounded-lg border-2 border-black p-3 text-center font-bold"
              href={`/api/claims/${month}/export`}
            >
              {t("export_csv")}
            </a>
            <a
              className="block min-h-14 rounded-lg border-2 border-black p-3 text-center font-bold"
              href={`/api/claims/${month}/print`}
              target="_blank"
              rel="noreferrer"
            >
              {t("print")}
            </a>
            <button type="button" className="min-h-14 rounded-lg border-2 border-black p-3 font-bold" onClick={() => void copyRegister()}>
              {copied ? t("copied") : t("copy_register")}
            </button>
          </div>

          <pre className="whitespace-pre-wrap border-2 border-black p-2 text-sm">{claim.register_lines.join("\n")}</pre>
        </>
      )}
    </div>
  );
}
