"""All Gnani calls live here. Stubs only: the API format is not confirmed yet.

docs.gnani.ai returned HTTP 403 when fetched, so no endpoint, header, or payload is assumed.
TODO for GnaniPrismaSTT and GnaniTimbreTTS, needed from the Gnani docs or account manager:
endpoint URL, auth header name and format, request fields, response fields,
supported languages (bn-IN, en-IN), accepted audio formats and max duration, and rate limits.
"""

from app.speech.base import Speech, Transcript

NOT_CONFIRMED = "Gnani API format not confirmed. See the module docstring for what is needed."


class GnaniPrismaSTT:
    name = "gnani"

    def transcribe(self, audio_bytes: bytes, mime: str, lang_hint: str) -> Transcript:
        raise NotImplementedError(f"TODO (Prisma STT): {NOT_CONFIRMED}")


class GnaniTimbreTTS:
    name = "gnani"

    def speak(self, text: str, lang: str) -> Speech:
        raise NotImplementedError(f"TODO (Timbre TTS): {NOT_CONFIRMED}")
