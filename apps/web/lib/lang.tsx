"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "bn" | "en";

const STRINGS = {
  nav_talk: { bn: "কথা বলুন", en: "Talk" },
  nav_diary: { bn: "ডায়েরি", en: "Diary" },
  nav_claim: { bn: "দাবি", en: "Claim" },
  toggle: { bn: "English", en: "বাংলা" },
  hold_to_talk: { bn: "ধরে রেখে বলুন", en: "Hold to talk" },
  recording: { bn: "শোনা হচ্ছে...", en: "Listening..." },
  recording_time: { bn: "রেকর্ডিং হচ্ছে...", en: "Recording..." },
  mic_unavailable: { bn: "মাইক্রোফোন ব্যবহার করা যাচ্ছে না। নিচে লিখুন।", en: "Microphone not available. Type below." },
  mic_denied: {
    bn: "মাইক্রোফোন ব্যবহারের অনুমতি দেওয়া হয়নি। অনুগ্রহ করে অনুমতি দিন অথবা নিচে লিখুন।",
    en: "Microphone access was denied. Please allow microphone access or type below.",
  },
  recording_too_long: {
    bn: "রেকর্ডিং ২৯ সেকেন্ডের বেশি হতে পারবে না।",
    en: "Recording cannot exceed 29 seconds.",
  },
  speech_busy: {
    bn: "স্পিচ সার্ভার এখন ব্যস্ত। একটু পরে আবার চেষ্টা করুন অথবা নিচে লিখুন।",
    en: "Speech service is busy. Please try again shortly or type below.",
  },
  no_credit: {
    bn: "স্পিচ ক্রেডিট শেষ হয়ে গেছে। অনুগ্রহ করে নিচে লিখুন।",
    en: "Speech credit exhausted. Please type below.",
  },
  service_error: {
    bn: "স্পিচ সার্ভারে সমস্যা হয়েছে। অনুগ্রহ করে নিচে লিখুন।",
    en: "Speech service error. Please type below.",
  },
  tap_to_hear: { bn: "শুনতে চাপুন", en: "Tap to hear" },
  type_placeholder: { bn: "এখানে লিখুন", en: "Type here" },
  send: { bn: "পাঠান", en: "Send" },
  yes: { bn: "হ্যাঁ", en: "YES" },
  no: { bn: "না", en: "NO" },
  edit: { bn: "সম্পাদনা", en: "EDIT" },
  loading: { bn: "লোড হচ্ছে...", en: "Loading..." },
  offline: { bn: "ইন্টারনেট সংযোগ নেই।", en: "You are offline." },
  error: { bn: "কিছু একটা ভুল হয়েছে।", en: "Something went wrong." },
  retry: { bn: "আবার চেষ্টা করুন", en: "Try again" },
  today_entries: { bn: "আজকের কাজ", en: "Today's work" },
  none_today: { bn: "আজ এখনও কোনো কাজ যোগ হয়নি।", en: "No work recorded today yet." },
  delete: { bn: "মুছুন", en: "Delete" },
  confirm_delete: { bn: "এই কাজটি কি মুছবেন?", en: "Delete this entry?" },
  save: { bn: "সংরক্ষণ", en: "Save" },
  cancel: { bn: "বাতিল", en: "Cancel" },
  date: { bn: "তারিখ", en: "Date" },
  task: { bn: "কাজ", en: "Task" },
  beneficiary: { bn: "উপকারভোগী", en: "Beneficiary" },
  count: { bn: "সংখ্যা", en: "Count" },
  missing_docs: { bn: "নথি বাকি", en: "Missing documents" },
  attention: { bn: "দেখা দরকার", en: "Needs attention" },
  export_csv: { bn: "CSV ডাউনলোড", en: "Download CSV" },
  print: { bn: "প্রিন্ট পাতা", en: "Print page" },
  copy_register: { bn: "রেজিস্টারের লাইন কপি", en: "Copy register lines" },
  copied: { bn: "কপি হয়েছে", en: "Copied" },
  month: { bn: "মাস (YYYY-MM)", en: "Month (YYYY-MM)" },
  total: { bn: "মোট (টাকা)", en: "Total (INR)" },
  not_configured: { bn: "পরিমাণ নির্ধারিত নয়", en: "amount not configured" },
  no_entries: { bn: "এই মাসে নিশ্চিত কাজ নেই।", en: "No confirmed entries this month." },
} as const;

export type StringKey = keyof typeof STRINGS;

const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({
  lang: "bn",
  setLang: () => {},
});

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("bn");

  useEffect(() => {
    const saved = window.localStorage.getItem("lang");
    if (saved === "bn" || saved === "en") setLang(saved);
  }, []);

  const change = (next: Lang) => {
    setLang(next);
    window.localStorage.setItem("lang", next);
  };

  return <LangContext.Provider value={{ lang, setLang: change }}>{children}</LangContext.Provider>;
}

export function useLang() {
  const { lang, setLang } = useContext(LangContext);
  const t = (key: StringKey): string => STRINGS[key][lang];
  return { lang, setLang, t };
}
