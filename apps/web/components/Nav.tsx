"use client";

import Link from "next/link";
import { useLang } from "@/lib/lang";

export function Nav() {
  const { lang, setLang, t } = useLang();
  return (
    <nav className="border-b-2 border-black">
      <div className="mx-auto flex max-w-xl items-center justify-between gap-2 p-2">
        <div className="flex gap-2">
          <Link className="rounded border-2 border-black px-3 py-2 font-bold" href="/">
            {t("nav_talk")}
          </Link>
          <Link className="rounded border-2 border-black px-3 py-2 font-bold" href="/diary">
            {t("nav_diary")}
          </Link>
          <Link className="rounded border-2 border-black px-3 py-2 font-bold" href="/claim">
            {t("nav_claim")}
          </Link>
        </div>
        <button
          type="button"
          className="rounded border-2 border-black px-3 py-2 font-bold"
          onClick={() => setLang(lang === "bn" ? "en" : "bn")}
        >
          {t("toggle")}
        </button>
      </div>
    </nav>
  );
}
