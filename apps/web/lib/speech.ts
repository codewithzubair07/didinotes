// Browser TTS fallback (Web Speech API). Used when the API returns use_browser_tts.
export function speakBrowser(text: string, lang: "bn-IN" | "en-IN"): void {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  window.speechSynthesis.speak(utterance);
}

// Plays audio returned by the API as base64.
// Returns a Promise that resolves to true on successful playback,
// or false if browser autoplay restrictions blocked playback.
export async function playBase64Audio(base64: string, mime = "audio/mpeg"): Promise<boolean> {
  if (typeof window === "undefined") return false;
  try {
    const audio = new Audio(`data:${mime};base64,${base64}`);
    await audio.play();
    return true;
  } catch {
    return false;
  }
}
