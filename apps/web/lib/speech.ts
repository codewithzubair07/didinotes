// Browser TTS fallback (Web Speech API). Used when the API returns use_browser_tts.
export function speakBrowser(text: string, lang: "bn-IN" | "en-IN"): void {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  window.speechSynthesis.speak(utterance);
}

// Plays audio returned by the API as base64.
export function playBase64Audio(base64: string, mime = "audio/mpeg"): void {
  const audio = new Audio(`data:${mime};base64,${base64}`);
  void audio.play();
}
