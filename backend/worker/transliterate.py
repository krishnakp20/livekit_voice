"""Devanagari -> Roman script normalisation for STT output.

Deepgram (nova-2) transcribes Hindi words in Devanagari and English words in
Latin script within the same line (e.g. "i know about a पूरा product"). A lone
Devanagari word inside an otherwise-English sentence visually dominates the
LLM's language judgment, causing it to reply in Hindi even when English is the
actual majority. Converting any Devanagari substrings to Roman script before
the text reaches the LLM removes that script-based bias while leaving nova-2's
transcription (and its accuracy) completely unchanged — this only touches how
the text is PRESENTED to the LLM, not how it was transcribed.

Pure local/offline transformation (indic_transliteration, no network call) —
negligible latency (~1-5ms on a single turn's transcript).
"""

import re

from indic_transliteration import sanscript

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def romanize(text: str) -> str:
    """Convert any Devanagari script in `text` to Roman (ITRANS) script.
    Latin-script portions of a mixed-script string are left untouched.
    No-op (and no library call) if the text has no Devanagari characters."""
    if not text or not _DEVANAGARI_RE.search(text):
        return text
    try:
        return sanscript.transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS)
    except Exception:
        return text
