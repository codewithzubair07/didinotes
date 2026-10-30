const IST = "Asia/Kolkata";

// Today's date in Asia/Kolkata as YYYY-MM-DD, independent of the browser's zone.
export function todayIso(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: IST,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export function currentMonthIso(now: Date = new Date()): string {
  return todayIso(now).slice(0, 7);
}
