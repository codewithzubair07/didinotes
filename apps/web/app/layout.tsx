import type { ReactNode } from "react";
import "./globals.css";
import { LangProvider } from "@/lib/lang";
import { Nav } from "@/components/Nav";

export const metadata = {
  title: "ASHA Diary",
  description: "Voice-first work diary for ASHA workers. Demo only.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="bn">
      <body className="bg-white text-black">
        <LangProvider>
          <div className="bg-black px-3 py-2 text-center text-sm font-bold text-white">
            Demo. Do not enter real patient data. / ডেমো। প্রকৃত রোগীর তথ্য লিখবেন না।
          </div>
          <Nav />
          <main className="mx-auto max-w-xl p-3">{children}</main>
        </LangProvider>
      </body>
    </html>
  );
}
