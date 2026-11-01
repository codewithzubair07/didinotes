export type ApiErrorKind = "offline" | "server";

export class ApiError extends Error {
  constructor(
    public kind: ApiErrorKind,
    public detail: { bn: string; en: string } | null = null,
  ) {
    super(kind);
  }
}

export type Entry = {
  id: number;
  task_type: string;
  beneficiary_ref: string | null;
  count: number;
  event_date: string;
  notes: string | null;
  documents: string[];
  status: "draft" | "confirmed" | "corrected";
  confidence: number | null;
  created_at: string;
};

export type TurnResponse = {
  transcript: string;
  entries: Array<{ task_type: string; count: number; event_date: string; beneficiary_ref: string | null }>;
  response_text: string;
  response_audio: string | null;
  ui_hint: string;
  timings_ms: { stt: number; nlu: number; tts: number; llm?: number };
  providers: { stt: string; tts: string; nlu?: string };
  tts_fallback?: boolean | string;
  dev?: {
    stt_model: string;
    stt_format: string;
    stt_request_id: string | null;
    tts_model: string;
    tts_voice: string;
    tts_cached: boolean;
    tts_request_id: string | null;
    tts_fallback: boolean | string;
  };
};

export type ClaimRow = {
  task_type: string;
  task_label_bn: string;
  task_label_en: string;
  entry_count: number;
  total_count: number;
  amount_inr: number | null;
  amount_status: string;
};

export type ClaimEntry = Entry & {
  task_label_en: string;
  task_label_bn: string;
  missing_documents: string[];
  attention_reasons: string[];
  amount_inr: number | string;
  event_date: string;
};

export type Claim = {
  month: string;
  rows: ClaimRow[];
  total_inr: number | null;
  entries: ClaimEntry[];
  attention: ClaimEntry[];
  register_lines: string[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    throw new ApiError("offline");
  }
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("offline");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: { bn: string; en: string } } | null;
    throw new ApiError("server", body?.detail ?? null);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  turnText: (sessionId: string, text: string, lang: string) =>
    request<TurnResponse>("/api/turn", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, text, lang }),
    }),
  entriesOn: (date: string) => request<Entry[]>(`/api/entries?date=${encodeURIComponent(date)}`),
  patchEntry: (id: number, changes: Partial<Pick<Entry, "count" | "event_date" | "beneficiary_ref">>) =>
    request<Entry>(`/api/entries/${id}`, { method: "PATCH", body: JSON.stringify(changes) }),
  confirmEntry: (id: number) => request<Entry>(`/api/entries/${id}/confirm`, { method: "POST" }),
  deleteEntry: (id: number) => request<void>(`/api/entries/${id}`, { method: "DELETE" }),
  claim: (month: string) => request<Claim>(`/api/claims/${month}`),
};

export function errorText(error: unknown, lang: "bn" | "en", offlineText: string, genericText: string): string {
  if (error instanceof ApiError) {
    if (error.kind === "offline") return offlineText;
    if (error.detail) return error.detail[lang];
  }
  return genericText;
}
