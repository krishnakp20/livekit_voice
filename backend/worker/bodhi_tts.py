"""Bodhi (Navana) TTS for LiveKit agents.

Bodhi's HTTP endpoint returns a whole clip in one response (~0.2-0.3s for a short
sentence over a warm connection), so it is used sentence-by-sentence: a StreamAdapter
splits the LLM output into sentences and each one is a keep-alive POST. The first sentence
therefore starts playing without waiting for the rest of the reply.

Dependency-free beyond aiohttp (already a livekit-agents dependency) — the vendor SDK is
not needed. Endpoint/headers were taken from bodhi-api-sdk 1.2.0.

Notes:
- Bodhi cannot cancel a synthesis in flight; on barge-in the LiveKit stream is closed and
  any audio still arriving is dropped.
- Voices: "default_female" / "default_male", or a cloned "cv_..." voice (language-specific).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

import aiohttp
from livekit.agents import APIConnectionError, APIStatusError, APITimeoutError, tokenize, tts, utils
from livekit.agents.tokenize import token_stream
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = logging.getLogger("vbots.bodhi_tts")

BODHI_TTS_URL = os.getenv("BODHI_TTS_URL", "https://tts.navana.ai/tts/bytes")
_SAMPLE_RATES = (8000, 16000, 24000)


def resolve_api_key(explicit: str | None = None) -> str:
    """Per-agent key, else BODHI_API_KEY, else the hyphenated `bodhi-api-key` some .env files use."""
    return (
        (explicit or "").strip()
        or os.getenv("BODHI_API_KEY", "").strip()
        or os.getenv("bodhi-api-key", "").strip()
    )


_ABBREVIATIONS = {"rs", "mr", "mrs", "ms", "dr", "st", "no", "vs"}


def _word_before(text: str, i: int) -> str:
    j = i
    while j > 0 and text[j - 1].isalpha():
        j -= 1
    return text[j:i].lower()


def _split_sentences(text: str) -> list[tuple[str, int, int]]:
    """Sentence splitter that also breaks on the Devanagari danda (।), which the stock
    blingfire/basic tokenizers ignore — without it a two-sentence Hindi reply would be
    synthesized as one clip and the first words would wait for the whole thing.

    A '.' only ends a sentence when followed by whitespace, so '102.5' is left intact.
    """
    out: list[tuple[str, int, int]] = []
    n = len(text)
    start = 0
    i = 0
    while i < n:
        ch = text[i]
        if ch in "।!?" or (
            ch == "."
            and (i + 1 >= n or text[i + 1].isspace())
            and _word_before(text, i) not in _ABBREVIATIONS
        ):
            j = i + 1
            while j < n and text[j] in "।!?.\"”'":
                j += 1
            if j >= n or text[j].isspace():
                k = j
                while k < n and text[k].isspace():
                    k += 1
                seg = text[start:k].strip()
                if seg:
                    out.append((seg, start, k))
                start = k
                i = k
                continue
        i += 1
    tail = text[start:].strip()
    if tail:
        out.append((tail, start, n))
    return out


class IndianSentenceTokenizer(tokenize.SentenceTokenizer):
    """Sentence tokenizer that understands '।' as well as . ! ?"""

    def __init__(self, *, min_sentence_len: int = 8, stream_context_len: int = 6) -> None:
        self._min_len = min_sentence_len
        self._ctx_len = stream_context_len

    def tokenize(self, text: str, *, language: str | None = None) -> list[str]:
        return [s for s, _, _ in _split_sentences(text)]

    def stream(self, *, language: str | None = None) -> tokenize.SentenceStream:
        return token_stream.BufferedSentenceStream(
            tokenizer=_split_sentences,
            min_token_len=self._min_len,
            min_ctx_len=self._ctx_len,
        )


class BodhiTTS(tts.TTS):
    """Non-streaming Bodhi TTS (one POST per text). Use build_bodhi_tts() for the streaming wrapper."""

    def __init__(
        self,
        *,
        api_key: str,
        voice: str = "default_female",
        lang: str = "hi",
        sample_rate: int = 8000,
        use_fast: bool = False,
        url: str = BODHI_TTS_URL,
    ) -> None:
        if sample_rate not in _SAMPLE_RATES:
            raise ValueError(f"Bodhi sample_rate must be one of {_SAMPLE_RATES}, got {sample_rate}")
        if not api_key:
            raise ValueError("Bodhi API key is required")
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sample_rate,
            num_channels=1,
        )
        self._api_key = api_key
        self._voice = voice
        self._lang = lang
        self._use_fast = use_fast
        self._url = url
        self._session: aiohttp.ClientSession | None = None

    @property
    def model(self) -> str:
        return "bodhi-fast" if self._use_fast else "bodhi"

    @property
    def provider(self) -> str:
        return "Bodhi"

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Keep idle connections alive across the pauses between turns so replies do not
            # pay a fresh TLS handshake each time.
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(keepalive_timeout=120, limit=8)
            )
        return self._session

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key, "Authorization": f"Bearer {self._api_key}"}

    def prewarm(self) -> None:
        """Open the TLS connection now (free GET to the host) so the first reply is not slow."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        asyncio.ensure_future(self._warm())

    async def _warm(self) -> None:
        try:
            origin = "/".join(self._url.split("/", 3)[:3])
            async with self._ensure_session().get(
                origin, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                await resp.read()
        except Exception as e:  # warm-up is best effort
            logger.debug("Bodhi prewarm skipped: %s", e)

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> "BodhiChunkedStream":
        return BodhiChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    async def aclose(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None


class BodhiChunkedStream(tts.ChunkedStream):
    def __init__(
        self, *, tts: BodhiTTS, input_text: str, conn_options: APIConnectOptions
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._bodhi = tts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        b = self._bodhi
        body: dict = {
            "text": self._input_text,
            "lang": b._lang,
            "voice": b._voice,
            "output_format": f"{b.sample_rate}:pcm16",
        }
        if b._use_fast:
            body["use_fast"] = True
        try:
            async with b._ensure_session().post(
                b._url,
                json=body,
                headers=b._headers(),
                timeout=aiohttp.ClientTimeout(total=30, sock_connect=self._conn_options.timeout),
            ) as resp:
                if resp.status != 200:
                    detail = (await resp.text())[:200]
                    raise APIStatusError(
                        message=f"Bodhi TTS {resp.status}: {detail}",
                        status_code=resp.status,
                        request_id=None,
                        body=detail,
                    )
                # The server's own rate wins over the one requested.
                rate = int(resp.headers.get("X-Sample-Rate", b.sample_rate))
                output_emitter.initialize(
                    request_id=utils.shortuuid(),
                    sample_rate=rate,
                    num_channels=1,
                    mime_type="audio/pcm",
                )
                async for chunk in resp.content.iter_chunked(4096):
                    output_emitter.push(chunk)
                output_emitter.flush()
        except asyncio.TimeoutError:
            raise APITimeoutError() from None
        except APIStatusError:
            raise
        except Exception as e:
            raise APIConnectionError() from e


class _BodhiStreamAdapter(tts.StreamAdapter):
    """StreamAdapter that also closes the wrapped Bodhi HTTP session (the stock one does not)."""

    async def aclose(self) -> None:
        await super().aclose()
        await self._wrapped_tts.aclose()


def build_bodhi_tts(
    *,
    api_key: str,
    voice: str = "default_female",
    lang: str = "hi",
    sample_rate: int = 8000,
    use_fast: bool = False,
) -> tts.TTS:
    """BodhiTTS wrapped so LLM text is synthesized sentence-by-sentence as it streams in."""
    inner = BodhiTTS(
        api_key=api_key, voice=voice, lang=lang, sample_rate=sample_rate, use_fast=use_fast
    )
    return _BodhiStreamAdapter(tts=inner, sentence_tokenizer=IndianSentenceTokenizer())
