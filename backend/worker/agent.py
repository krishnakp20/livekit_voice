"""
VBots LiveKit Agent Worker (dynamic, per-DID via dispatch rules)

Run from backend/:
    python worker/agent.py dev

Requires .env with LIVEKIT_*, OPENAI_API_KEY, SARVAM_API_KEY, DATABASE_URL.

How routing works:
1. Inbound SIP hits a trunk/DID
2. LiveKit dispatch rule creates room agent-{agent_id}-xxx with metadata {"agent_id": N}
3. This worker receives the job, loads agent N from MySQL, runs STT/LLM/TTS
4. Different DIDs → different dispatch rules → different agent_id in metadata
"""

import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path

# backend/ on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)

try:
    from livekit.agents import (
        Agent,
        AgentSession,
        JobContext,
        JobProcess,
        WorkerOptions,
        cli,
    )
    from livekit.agents.voice import room_io
    from livekit.agents.voice.turn import TurnHandlingOptions  # v1.5+ non-deprecated API
except ModuleNotFoundError:
    print(
        "\n[VBots] livekit-agents not installed in this venv.\n"
        "Run:\n"
        "  pip install livekit-agents==1.2.8 livekit-plugins-openai==1.2.8 "
        "livekit-plugins-sarvam==1.2.8 livekit-plugins-silero==1.2.8\n"
    )
    raise SystemExit(1)
# StopResponse moved across versions — import defensively so the worker never
# crashes on a missing path. Falls back to a local sentinel exception.
try:
    from livekit.agents.llm import StopResponse
except ImportError:
    try:
        from livekit.agents import StopResponse
    except ImportError:
        class StopResponse(Exception):  # type: ignore
            """Fallback if the SDK doesn't expose StopResponse."""

from livekit.plugins import openai, sarvam, silero
try:
    from livekit.plugins import groq as groq_plugin
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

try:
    from livekit.plugins import deepgram as deepgram_plugin
    _DEEPGRAM_AVAILABLE = True
except ImportError:
    _DEEPGRAM_AVAILABLE = False

try:
    from livekit.plugins import cartesia as cartesia_plugin
    _CARTESIA_AVAILABLE = True
except ImportError:
    _CARTESIA_AVAILABLE = False

try:
    from livekit.plugins import elevenlabs as elevenlabs_plugin
    _ELEVENLABS_AVAILABLE = True
except ImportError:
    _ELEVENLABS_AVAILABLE = False

try:
    from livekit.plugins.openai.realtime.realtime_model import (
        InputAudioTranscription,
        NoiseReduction,
        TurnDetection,
    )
except ImportError:
    InputAudioTranscription = None
    NoiseReduction = None
    TurnDetection = None


from app.core.config import settings
from app.services.recording_service import recording_path_for_room
from worker.config_loader import (
    extract_caller_from_room_name,
    extract_did_from_metadata,
    load_agent_config,
    parse_metadata,
    resolve_agent_id,
)
from worker.call_tracking import attach_call_listeners
from worker.recordings import (
    persist_session_artifacts,
    session_record_options,
    should_record_call,
)

logging.basicConfig(level=logging.DEBUG, force=True)
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger("livekit").setLevel(logging.DEBUG)
logging.getLogger("livekit.agents").setLevel(logging.DEBUG)
logging.getLogger("livekit.plugins.openai").setLevel(logging.DEBUG)
logging.getLogger("openai").setLevel(logging.DEBUG)
logging.getLogger("websockets").setLevel(logging.DEBUG)
logging.getLogger("websockets.client").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)
logging.getLogger("httpcore").setLevel(logging.DEBUG)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("vbots.agent")

# Deterministic transfer triggers — matched against the customer's transcript.
# Covers English + Hindi/Hinglish ways of asking for a human agent.
_TRANSFER_KEYWORDS = (
    # English
    "transfer",
    "human",
    "agent",
    "representative",
    "executive",
    "senior",
    "supervisor",
    "manager",
    "customer care",
    "real person",
    "someone else",
    "talk to someone",
    "speak to someone",
    "connect me",
    "connect my call",
    # Hindi / Hinglish
    "insaan",
    "aadmi",
    "vyakti",
    "kisi se baat",
    "baat karni",
    "baat karwa",
    "baat kara",
    "transfer kar",
    "connect kar",
    "senior se",
    "bade officer",
)

# OpenAI Realtime only accepts these voice names — NOT Cartesia/ElevenLabs voice
# ids/UUIDs. If an agent's `voice` field still holds a leftover value from a
# different TTS provider, silently fall back to "marin" rather than 400ing.
_REALTIME_VOICES = {
    "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse", "marin", "cedar",
}


def prewarm(proc: JobProcess) -> None:
    # VAD detects SPEECH START/END boundaries (audio gating); EOU is decided by the LLM
    # semantic turn_detection when AGENT_TURN_DETECTION="semantic".
    # min_silence_duration=0.15 is the audio gate — a brief pause suspends audio to STT.
    # With semantic mode the LLM then decides whether it's a genuine end-of-turn, so
    # SIP background noise that causes a 0.15 s VAD gap will NOT trigger a false EOU.
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.15,
        prefix_padding_duration=0.15,
    )


_TOKEN_RE = re.compile(r"\{([a-zA-Z0-9_ ]+)\}")


def _personalize(text: str, fields: dict) -> str:
    """Replace {key} tokens with the lead's field values (case-insensitive).

    Unknown or empty keys collapse to '' so the prompt's own 'if field is empty →
    fallback' rules fire naturally. Schema-agnostic: works for any client's fields."""
    if not text or not fields:
        return text or ""
    low = {str(k).strip().lower(): ("" if v is None else str(v)) for k, v in fields.items()}
    return _TOKEN_RE.sub(lambda m: low.get(m.group(1).strip().lower(), ""), text)


def _call_data_block(fields: dict) -> str:
    """Render a 'CALL DATA' block of key: value pairs to append to the prompt, so
    [square-bracket] script lines also get filled from real data (no guessing)."""
    items = [f"- {k}: {v}" for k, v in (fields or {}).items() if str(v).strip()]
    if not items:
        return ""
    return (
        "\n\n━━━ CALL DATA (use these EXACT values for this customer; "
        "NEVER invent or guess any value not listed here) ━━━\n" + "\n".join(items)
    )


def _provider_lang(config) -> str:
    """Deepgram/Cartesia language code from the agent's `language` field.
    English (en-*) → 'en' (works for UK/US/Indian English — the accent comes from
    the chosen voice); Hindi/Hinglish → 'hi'. Lets each client run its own language."""
    val = getattr(config.language, "value", str(config.language))
    return "en" if str(val).lower().startswith("en") else "hi"


def _cartesia_voice_for(config) -> str:
    """Per-agent Cartesia voice. If the agent's `voice` field holds a Cartesia voice
    ID (a UUID — e.g. a British-English voice for the UK client), use it; otherwise
    fall back to the global CARTESIA_VOICE_ID. This is how each client gets its own
    voice/tone without a schema change — just set `voice` to a Cartesia voice UUID."""
    v = (getattr(config, "voice", "") or "").strip()
    if len(v) >= 32 and v.count("-") >= 4:  # looks like a Cartesia voice UUID
        return v
    return settings.CARTESIA_VOICE_ID or os.getenv("CARTESIA_VOICE_ID", "")


class DynamicVoiceAgent(Agent):
    """Agent built from ai_agents row (prompt, voice, language, provider)."""

    def __init__(self, config, greeting: str, lead_name: str = "", lead_fields: dict | None = None):
        from app.db.models.ai_agent import AIProvider, Language
        from worker.config_loader import language_to_sarvam_code, voice_to_sarvam_speaker

        # Transfer settings from the agent row. Filled with room/identity at runtime.
        self._transfer_enabled = bool(getattr(config, "transfer_enabled", False))
        self._transfer_number = (getattr(config, "transfer_number", "") or "").strip()
        self._ctx = None          # JobContext — set in entrypoint after creation
        self._sip_identity = None  # SIP participant to transfer — set in entrypoint
        self._transfer_done = False     # True once a REFER was accepted
        self._transfer_to = None        # destination URI of a successful transfer

        lang_code = language_to_sarvam_code(config.language)
        use_sarvam = config.provider == AIProvider.SARVAM
        # Deepgram/Cartesia language for THIS agent (en for a UK/English client, hi otherwise)
        provider_lang = _provider_lang(config)

        from app.core.crypto import decrypt_secret

        # Explicit per-agent provider selection (UI). None/unset on any of these
        # falls through to the ORIGINAL priority-chain behaviour below, UNCHANGED —
        # existing agents (no provider explicitly set) are byte-for-byte unaffected.
        explicit_stt = (getattr(config, "stt_provider", None) or "").strip().lower()
        stt_key_override = decrypt_secret(getattr(config, "stt_api_key", None))
        explicit_llm = (getattr(config, "llm_provider", None) or "").strip().lower()
        llm_key_override = decrypt_secret(getattr(config, "llm_api_key", None))
        # OpenAI Realtime (speech-to-speech) replaces STT+LLM+TTS with one model —
        # it takes the caller's audio directly and speaks back, so the STT/TTS
        # provider selection below is irrelevant and skipped entirely.
        use_realtime = explicit_llm == "openai_realtime"

        if use_realtime:
            stt = None
            logger.info("STT: skipped — OpenAI Realtime (STS) handles audio directly [explicit]")
        elif explicit_stt == "deepgram" and _DEEPGRAM_AVAILABLE:
            stt = deepgram_plugin.STT(
                model="nova-2",
                language=provider_lang,
                smart_format=False,
                punctuate=False,
                sample_rate=8000,
                endpointing_ms=50,
                no_delay=True,
                **({"api_key": stt_key_override} if stt_key_override else {}),
            )
            logger.info("STT: Deepgram nova-2 (%s, 8kHz, endpointing=50ms) [explicit]", provider_lang)
        elif explicit_stt == "sarvam":
            stt = sarvam.STT(
                language=lang_code,
                model=settings.AGENT_STT_MODEL,
                mode="transcribe",
                high_vad_sensitivity=False,
                sample_rate=settings.AGENT_AUDIO_SAMPLE_RATE,
                prompt=settings.AGENT_STT_PROMPT,
                **({"api_key": stt_key_override} if stt_key_override else {}),
            )
            logger.info("STT: Sarvam %s (batch) [explicit]", settings.AGENT_STT_MODEL)
        else:
            # === Original fallback chain (unchanged) ===
            deepgram_key = os.getenv("DEEPGRAM_API_KEY", "")
            if _DEEPGRAM_AVAILABLE and deepgram_key:
                # nova-2 + language="hi" is the correct code for Hindi/Hinglish on Deepgram.
                # "hi-Latn" (Romanised Hindi) does NOT exist in Deepgram's API → always 400.
                # With language="hi" Deepgram transcribes Hindi words in Devanagari and
                # English words in Latin script; the LLM understands both fine.
                # sample_rate=8000: MUST stay 8000 — SIP PSTN narrowband.
                stt = deepgram_plugin.STT(
                    model="nova-2",
                    language=provider_lang,
                    smart_format=False,
                    punctuate=False,
                    sample_rate=8000,
                    endpointing_ms=50,
                    no_delay=True,
                )
                logger.info("STT: Deepgram nova-2 (%s, 8kHz, endpointing=50ms)", provider_lang)
            elif use_sarvam:
                stt = sarvam.STT(
                    language=lang_code,
                    model=settings.AGENT_STT_MODEL,
                    mode="transcribe",
                    high_vad_sensitivity=False,
                    sample_rate=settings.AGENT_AUDIO_SAMPLE_RATE,
                    prompt=settings.AGENT_STT_PROMPT,
                )
                logger.info("STT: Sarvam %s (batch)", settings.AGENT_STT_MODEL)
            else:
                stt = openai.STT()
                logger.info("STT: OpenAI Whisper")

        reply_tokens = min(int(config.max_tokens), settings.AGENT_REPLY_MAX_TOKENS)

        # Inject customer name — but strictly limit where it is used (clients
        # complained the bot repeated the name in every sentence).
        name_context = (
            f"\n\nThe customer's name is {lead_name}. "
            "Use their name ONLY once — in your first greeting OR your closing line. "
            "Do NOT use their name in any other sentence during the conversation."
            if lead_name else ""
        )

        gender = (getattr(config, "gender", "female") or "female").lower()
        if gender == "male":
            gender_rule = (
                "2. GENDER: You are a MALE agent. This ONLY applies when you are "
                "replying in Hindi or Hinglish — in that case use masculine Hindi verb "
                "forms about yourself ('kar sakta hoon', 'karunga', 'bataaunga', 'samajh "
                "gaya', 'rahunga'), never feminine forms. When replying in English, this "
                "rule does not apply — speak natural English ('I can', 'I will'); do NOT "
                "insert Hindi words into an English reply just to satisfy this rule.\n"
            )
        else:
            gender_rule = (
                "2. GENDER: You are a FEMALE agent. This ONLY applies when you are "
                "replying in Hindi or Hinglish — in that case use feminine Hindi verb "
                "forms about yourself ('kar sakti hoon', 'karungi', 'bataaungi', 'samajh "
                "gayi', 'rahungi'), never masculine forms. When replying in English, this "
                "rule does not apply — speak natural English ('I can', 'I will'); do NOT "
                "insert Hindi words into an English reply just to satisfy this rule.\n"
            )

        # Inject per-lead dynamic fields into the prompt body ({customer_name},
        # {current_plan_name}, {whatsapp_link}, …) and append a CALL DATA block.
        base_prompt = _personalize(config.prompt, lead_fields or {})
        data_block = _call_data_block(lead_fields or {})

        phone_prompt = (
            f"{base_prompt}{name_context}{data_block}\n\n"
            "PHONE CALL RULES (follow strictly):\n"
            "1. LENGTH: Reply in 1 short sentence (10-15 words). Ask only ONE question "
            "at a time. No lists or long explanations.\n"
            f"{gender_rule}"
            "3. LANGUAGE: Reply in the SAME language the customer is mostly using.\n"
            "   • Mostly Hindi or Hinglish → reply in natural Hinglish.\n"
            "   • Full English sentences → reply in English.\n"
            "   • English technical/loan words inside a Hindi sentence (inverter, "
            "battery, solar, price, hello) are NORMAL Hinglish — do NOT treat them as "
            "a language switch.\n"
            "   • Match the customer turn by turn; moving between Hindi and English as "
            "they do is fine. Never announce or ask which language they prefer.\n"
            "   • If the customer EXPLICITLY asks you to switch language ('can you "
            "speak in English', 'Hindi mein baat karein', 'English please'), IMMEDIATELY "
            "switch and continue fully in that language. This is a NORMAL request — "
            "always honor it, NEVER refuse it or call it out of scope.\n"
            "4. NEVER MAKE THINGS UP: Do not invent or generate complaint numbers, "
            "ticket IDs, order numbers, reference numbers, serial numbers, prices, "
            "dates, or any fact not given to you. If you don't have it, say a team "
            "member will share it.\n"
            "5. UNDERSTANDING: If you understand the general intent (e.g. the customer "
            "wants to buy or ask about an inverter), respond helpfully — do NOT ask "
            "them to repeat a clear request. Only ask to repeat if the message is "
            "truly empty or unintelligible:\n"
            "   • Hinglish: 'Maaf kijiye, thoda dobara bata sakte hain?'\n"
            "   • English: 'Sorry, could you please repeat that?'\n"
            "6. SCOPE: Stay within your role above. A request to change language, repeat, "
            "speak slower/louder, or hold on is NEVER out of scope — always comply. "
            "Only for a genuinely unrelated topic, say:\n"
            "   • Hinglish: 'Iske baare mein main aapki madad nahi kar sakti, hamari "
            "team aapse baat karegi.'\n"
            "   • English: 'That's outside my area — our team will help you with that.'\n"
            "7. NAME: Do NOT address the customer by name. Never start a reply with "
            "their name or a vocative. Wrong: 'Krishna ji, aapka phone number kya hai?' "
            "Right: 'Aapka phone number kya hai?'. Just answer directly without the "
            "name, even if you know it.\n"
            "8. Sound natural, warm, and human. Never mention you are an AI or a bot.\n\n"
            "CRITICAL REMINDER: Never put the customer's name in your reply. "
            "Do not write 'naam ji' or 'Krishna ji' or any name at the start of a "
            "sentence. Answer the question directly."
        )

        # NOTE: Transfer is handled deterministically in on_user_turn_completed via
        # keyword detection — NOT via an LLM tool call. Groq's 8b model emits tool
        # calls as plain text (<function=...>), which leaks into TTS and never fires.
        # So we intentionally do NOT instruct the LLM to transfer here.
        # LLM selection with automatic fallback:
        #   primary = Groq (fast/cheap) — but free tier hits 429 token-rate limits.
        #   fallback = OpenAI — kicks in automatically when Groq errors (429/5xx),
        #   so the bot NEVER goes silent mid-call due to a Groq rate limit.
        if explicit_llm in ("openai", "groq"):
            # Explicit provider chosen in the UI: use ONLY that provider, no automatic
            # fallback to the other (the client picked this one deliberately). Falls
            # back to the global key for that provider if no per-agent key is set.
            if explicit_llm == "openai":
                llm = openai.LLM(
                    model=config.model or settings.DEFAULT_LLM_MODEL,
                    temperature=float(config.temperature),
                    max_completion_tokens=reply_tokens,
                    **({"api_key": llm_key_override} if llm_key_override else {}),
                )
                logger.info(
                    "LLM: OpenAI %s (max_tokens=%d) [explicit]",
                    config.model or settings.DEFAULT_LLM_MODEL, reply_tokens,
                )
            else:
                llm = groq_plugin.LLM(
                    model=config.model or settings.GROQ_MODEL,
                    temperature=float(config.temperature),
                    max_completion_tokens=reply_tokens,
                    **({"api_key": llm_key_override} if llm_key_override else {}),
                )
                logger.info(
                    "LLM: Groq %s (max_tokens=%d) [explicit]",
                    config.model or settings.GROQ_MODEL, reply_tokens,
                )
        elif use_realtime:
            # Speech-to-speech: one model handles listening + thinking + speaking.
            # `voice` is repurposed here to hold the Realtime voice name (e.g. "marin",
            # "alloy", "cedar") instead of a Cartesia/Sarvam voice id — fall back to
            # "marin" if it still holds a leftover value from a different provider.
            raw_voice = (config.voice or "").strip().lower()
            if raw_voice in _REALTIME_VOICES:
                realtime_voice = raw_voice
            else:
                if raw_voice:
                    logger.warning(
                        "Voice %r is not a valid OpenAI Realtime voice (valid: %s) — "
                        "falling back to 'marin'", config.voice, sorted(_REALTIME_VOICES),
                    )
                realtime_voice = "marin"
            realtime_model = (config.model or "").strip() or "gpt-realtime"
            # Without input_audio_transcription, the caller's speech is never turned
            # into text — transfer keyword detection, transcript logging, and CRM
            # data extraction all silently stop working (they all read the
            # transcribed text, not raw audio, and are independent of what the
            # model itself understood to generate its spoken reply).
            # language="en" is a documented accuracy aid — short/quiet utterances
            # (a lone "yes", a brief ack) were otherwise being hallucinated as
            # random foreign-script text instead of English.
            transcription_kwargs = (
                {
                    "input_audio_transcription": InputAudioTranscription(
                        model="gpt-4o-mini-transcribe", language="en",
                    )
                }
                if InputAudioTranscription is not None
                else {}
            )
            # SIP/PSTN phone lines are noisy — without this, static/line noise gets
            # misread as speech and the model hallucinates unrelated foreign-script
            # text for it, then reacts to that hallucination as if it were real.
            # near_field suits a handset held to the ear (vs far_field for a room
            # mic); raising the VAD threshold above the 0.5 default requires louder,
            # clearer audio before a turn is triggered at all.
            noise_kwargs = (
                {"input_audio_noise_reduction": NoiseReduction(type="near_field")}
                if NoiseReduction is not None
                else {}
            )
            turn_detection_kwargs = (
                {"turn_detection": TurnDetection(type="server_vad", threshold=0.6)}
                if TurnDetection is not None
                else {}
            )
            llm = openai.realtime.RealtimeModel(
                model=realtime_model,
                voice=realtime_voice,
                **transcription_kwargs,
                **noise_kwargs,
                **turn_detection_kwargs,
                **({"api_key": llm_key_override} if llm_key_override else {}),
            )
            logger.info(
                "LLM: OpenAI Realtime (STS) model=%s voice=%s [explicit]",
                realtime_model, realtime_voice,
            )
        else:
            # === Original fallback chain (unchanged) ===
            groq_key = os.getenv("GROQ_API_KEY", "")
            openai_key = os.getenv("OPENAI_API_KEY", "")
            groq_llm = None
            openai_llm = None
            groq_model = settings.GROQ_MODEL
            if _GROQ_AVAILABLE and groq_key:
                groq_llm = groq_plugin.LLM(
                    model=groq_model,
                    temperature=float(config.temperature),
                    max_completion_tokens=reply_tokens,
                )
            if openai_key:
                openai_llm = openai.LLM(
                    model=config.model or settings.DEFAULT_LLM_MODEL,
                    temperature=float(config.temperature),
                    max_completion_tokens=reply_tokens,
                )

            # LLM_PRIMARY chooses which provider runs first:
            #   "openai" (default) — reliable, good quality, no rate-limit storm. Use this
            #                        on Groq FREE tier (6000 TPM is too small for calls).
            #   "groq"   — fast/cheap; only sensible on Groq DEV tier (paid, high limits).
            # The other provider becomes the automatic fallback.
            llm_primary = os.getenv("LLM_PRIMARY", "openai").strip().lower()
            from livekit.agents import llm as _lk_llm

            if groq_llm and openai_llm:
                if llm_primary == "groq":
                    llm = _lk_llm.FallbackAdapter([groq_llm, openai_llm])
                    logger.info("LLM: Groq (primary) → OpenAI fallback (max_tokens=%d)", reply_tokens)
                else:
                    llm = _lk_llm.FallbackAdapter([openai_llm, groq_llm])
                    logger.info("LLM: OpenAI (primary) → Groq fallback (max_tokens=%d)", reply_tokens)
            elif openai_llm:
                llm = openai_llm
                logger.info("LLM: OpenAI %s (max_tokens=%d)", config.model or settings.DEFAULT_LLM_MODEL, reply_tokens)
            elif groq_llm:
                llm = groq_llm
                logger.info(
                    "LLM: Groq %s (max_tokens=%d) — NO OpenAI fallback "
                    "(set OPENAI_API_KEY to avoid silence on 429)",
                    groq_model,
                    reply_tokens,
                )
            else:
                raise RuntimeError("No LLM configured: set GROQ_API_KEY and/or OPENAI_API_KEY")

        explicit_tts = (getattr(config, "tts_provider", None) or "").strip().lower()
        tts_key_override = decrypt_secret(getattr(config, "tts_api_key", None))
        cartesia_voice = _cartesia_voice_for(config)

        if use_realtime:
            tts = None
            logger.info("TTS: skipped — OpenAI Realtime (STS) handles audio directly [explicit]")
        elif explicit_tts == "cartesia" and _CARTESIA_AVAILABLE:
            tts = cartesia_plugin.TTS(
                model="sonic-3.5",
                voice=cartesia_voice,
                language=provider_lang,
                sample_rate=settings.AGENT_AUDIO_SAMPLE_RATE,
                **({"api_key": tts_key_override} if tts_key_override else {}),
            )
            logger.info("TTS: Cartesia sonic-3.5 voice=%s (%s) [explicit]", cartesia_voice, provider_lang)
        elif explicit_tts == "sarvam":
            tts = sarvam.TTS(
                model=settings.AGENT_TTS_MODEL,
                speaker=voice_to_sarvam_speaker(config.voice, tts_model=settings.AGENT_TTS_MODEL),
                target_language_code=lang_code,
                speech_sample_rate=settings.AGENT_TTS_SAMPLE_RATE,
                enable_preprocessing=True,
                pace=1.05,
                temperature=0.45,
                pitch=0.04,
                loudness=1.02,
                max_chunk_length=120,
                **({"api_key": tts_key_override} if tts_key_override else {}),
            )
            logger.info("TTS: Sarvam %s (explicit)", settings.AGENT_TTS_MODEL)
        elif explicit_tts == "elevenlabs" and _ELEVENLABS_AVAILABLE:
            # New provider, no legacy fallback equivalent — voice field holds the
            # ElevenLabs voice_id (from elevenlabs.io/app/voice-library).
            tts = elevenlabs_plugin.TTS(
                voice_id=(config.voice or "").strip() or None,
                **({"api_key": tts_key_override} if tts_key_override else {}),
            )
            logger.info("TTS: ElevenLabs voice_id=%s [explicit]", config.voice)
        else:
            # === Original fallback chain (unchanged) ===
            cartesia_key = os.getenv("CARTESIA_API_KEY", "")
            # Per-agent voice + language → each client can have its own tone (e.g. a
            # British-English voice for the UK client). Set the agent's `voice` field to a
            # Cartesia voice UUID and its `language` to English/Hindi/Hinglish in the UI.
            if _CARTESIA_AVAILABLE and cartesia_key and cartesia_voice:
                # Cartesia sonic-3.5: ~50-100ms TTFB. Supports en (UK/US) and hi.
                # Pick voices at cartesia.ai/voices; put the UUID in the agent's `voice` field.
                tts = cartesia_plugin.TTS(
                    model="sonic-3.5",
                    voice=cartesia_voice,
                    language=provider_lang,
                    sample_rate=settings.AGENT_AUDIO_SAMPLE_RATE,
                )
                logger.info("TTS: Cartesia sonic-3.5 voice=%s (%s)", cartesia_voice, provider_lang)
            elif use_sarvam:
                tts = sarvam.TTS(
                    model=settings.AGENT_TTS_MODEL,
                    speaker=voice_to_sarvam_speaker(
                        config.voice, tts_model=settings.AGENT_TTS_MODEL
                    ),
                    target_language_code=lang_code,
                    # Generate at TTS native rate (22050 Hz); LiveKit resamples to 8 kHz for SIP.
                    speech_sample_rate=settings.AGENT_TTS_SAMPLE_RATE,
                    enable_preprocessing=True,
                    pace=1.05,
                    temperature=0.45,
                    pitch=0.04,
                    loudness=1.02,
                    max_chunk_length=120,
                )
                logger.info("TTS: Sarvam %s (fallback)", settings.AGENT_TTS_MODEL)
            else:
                tts = openai.TTS()
                logger.info("TTS: OpenAI (fallback)")

        super().__init__(instructions=phone_prompt, stt=stt, llm=llm, tts=tts)
        self._greeting = greeting
        self._interruptions = config.interruptions_enabled
        self._is_realtime = use_realtime

    async def on_enter(self):
        logger.info("on_enter: called, is_realtime=%s", self._is_realtime)
        if self._is_realtime:
            # OpenAI's Realtime model has no TTS to .say() a fixed line with — ask
            # it to open the call by speaking this line itself instead.
            logger.info("on_enter: calling generate_reply for realtime greeting")
            t0 = time.monotonic()
            try:
                await self.session.generate_reply(
                    instructions=(
                        f"Start the call now by greeting the caller with this exact line, "
                        f"word for word: {self._greeting!r}"
                    )
                )
                logger.info(
                    "on_enter: generate_reply returned successfully after %.2fs",
                    time.monotonic() - t0,
                )
            except Exception:
                logger.exception(
                    "on_enter: generate_reply raised an exception after %.2fs",
                    time.monotonic() - t0,
                )
                raise
        else:
            await self.session.say(self._greeting)
        logger.info("on_enter: finished")

    async def _perform_transfer(self) -> bool:
        """Execute the SIP REFER transfer. Returns True on success."""
        if not (self._transfer_enabled and self._transfer_number):
            return False
        if self._transfer_done:
            return True
        if not self._ctx or not self._sip_identity:
            logger.warning("Transfer requested but ctx/sip_identity missing")
            return False

        self._transfer_done = True
        try:
            from livekit import api

            # LiveKit API uses http(s); convert the ws(s) URL from settings.
            http_url = settings.LIVEKIT_URL.replace("wss://", "https://").replace(
                "ws://", "http://"
            )

            # Build the transfer destination URI.
            # Your trunk rejected tel: with "603 Declined (Non sip: uri)" — it wants
            # a sip: URI. Priority:
            #   1. If the configured number is already a sip:/tel: URI → use as-is.
            #   2. If it contains "@" → prefix sip:.
            #   3. Else build sip:<number>@<host>, where host comes from
            #      SIP_TRANSFER_HOST (.env) or the caller's trunk (sip.hostname).
            raw = self._transfer_number.strip()
            if raw.startswith(("sip:", "tel:")):
                transfer_to = raw
            elif "@" in raw:
                transfer_to = f"sip:{raw}"
            else:
                digits = "".join(c for c in raw if c.isdigit() or c == "+")
                number = digits if digits.startswith("+") else "+" + digits
                host = (getattr(settings, "SIP_TRANSFER_HOST", "") or "").strip()
                if not host:
                    # Fall back to the trunk host of the current SIP caller.
                    try:
                        p = self._ctx.room.remote_participants.get(self._sip_identity)
                        if p and p.attributes:
                            host = p.attributes.get("sip.hostname", "") or ""
                    except Exception:
                        host = ""
                transfer_to = f"sip:{number}@{host}" if host else f"tel:{number}"
            logger.info("Transfer destination URI: %s", transfer_to)

            lkapi = api.LiveKitAPI(
                url=http_url,
                api_key=settings.LIVEKIT_API_KEY,
                api_secret=settings.LIVEKIT_API_SECRET,
            )
            try:
                await lkapi.sip.transfer_sip_participant(
                    api.TransferSIPParticipantRequest(
                        room_name=self._ctx.room.name,
                        participant_identity=self._sip_identity,
                        transfer_to=transfer_to,
                        play_dialtone=True,
                    )
                )
            finally:
                await lkapi.aclose()

            self._transfer_to = transfer_to
            logger.info(
                "Call transferred: room=%s identity=%s → %s",
                self._ctx.room.name,
                self._sip_identity,
                transfer_to,
            )
            return True
        except Exception as e:
            self._transfer_done = False
            logger.error("Transfer failed: %s", e)
            return False

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """Deterministic transfer trigger — runs BEFORE the LLM.

        Groq's 8b model emits tool calls unreliably (as text), so we detect a
        clear human/transfer request by keyword and transfer directly. Raising
        StopResponse prevents the LLM from generating a reply for this turn.
        """
        if not (self._transfer_enabled and self._transfer_number) or self._transfer_done:
            return
        text = (getattr(new_message, "text_content", "") or "").lower()
        if not text:
            return
        if any(kw in text for kw in _TRANSFER_KEYWORDS):
            logger.info("Transfer keyword detected in: %r", text[:80])
            await self.session.say(
                "Sure, please hold while I connect you to our team."
            )
            ok = await self._perform_transfer()
            if not ok:
                await self.session.say(
                    "Sorry, I could not connect the call. Please share your number "
                    "and our team will call you back."
                )
            raise StopResponse()


def _meta_int(meta: dict, key: str) -> int | None:
    val = meta.get(key)
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


async def create_call_log(
    ctx: JobContext,
    agent_id: int,
    caller: str | None,
    did_number: str | None = None,
    *,
    direction: str = "inbound",
    callee: str | None = None,
    campaign_id: int | None = None,
    lead_id: int | None = None,
) -> int | None:
    """Insert call_logs row and notify dashboard via WebSocket."""
    try:
        from datetime import datetime, timezone

        from app.db.models.call_log import CallDirection, CallLog, CallStatus
        from app.db.session import AsyncSessionLocal
        from app.websocket.manager import socket_manager
        from worker.config_loader import load_agent_config

        config = await load_agent_config(agent_id)
        if not config:
            return None
        is_outbound = direction == "outbound" or ctx.room.name.startswith("outbound-")
        call_direction = CallDirection.OUTBOUND if is_outbound else CallDirection.INBOUND

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            existing = await db.execute(
                select(CallLog)
                .where(CallLog.room_name == ctx.room.name)
                .order_by(CallLog.id.desc())
                .limit(1)
            )
            call = existing.scalar_one_or_none()
            if call:
                call.status = CallStatus.ACTIVE
                if campaign_id and not call.campaign_id:
                    call.campaign_id = campaign_id
                if lead_id and not call.lead_id:
                    call.lead_id = lead_id
                await db.commit()
                await db.refresh(call)
            else:
                call = CallLog(
                    client_id=config.client_id,
                    agent_id=agent_id,
                    campaign_id=campaign_id,
                    lead_id=lead_id,
                    room_name=ctx.room.name,
                    direction=call_direction,
                    status=CallStatus.ACTIVE,
                    caller_number=caller if not is_outbound else None,
                    callee_number=callee if is_outbound else None,
                    did_number=did_number,
                    started_at=datetime.now(timezone.utc),
                )
                db.add(call)
                await db.commit()
                await db.refresh(call)
            await socket_manager.emit_call_update(
                config.client_id,
                {
                    "call_id": call.id,
                    "room_name": call.room_name,
                    "status": call.status.value,
                    "caller_number": caller,
                },
            )
            return call.id
    except Exception as e:
        logger.warning("Could not create call_log: %s", e)
        return None


async def finalize_call_log(
    room_name: str,
    *,
    failed: bool = False,
    callee_answered: bool = True,
    transferred: bool = False,
    transfer_to: str | None = None,
) -> None:
    """Mark call completed/failed/transferred when LiveKit room ends."""
    try:
        from datetime import datetime, timezone

        from sqlalchemy import select

        from app.db.models.call_log import CallLog, CallStatus
        from app.db.models.campaign import Campaign, Lead, LeadStatus
        from app.db.session import AsyncSessionLocal
        from app.websocket.manager import socket_manager
        from worker.call_tracking import refresh_call_sentiment_from_db

        call_id: int | None = None
        client_id: int | None = None
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CallLog)
                .where(CallLog.room_name == room_name)
                .order_by(CallLog.id.desc())
                .limit(1)
            )
            call = result.scalar_one_or_none()
            if not call or call.status not in (CallStatus.ACTIVE, CallStatus.RINGING):
                return

            now = datetime.now(timezone.utc)
            # Capture whether callee actually answered BEFORE changing status
            was_active = call.status == CallStatus.ACTIVE
            if transferred:
                call.status = CallStatus.TRANSFERRED
                if transfer_to:
                    call.disposition = f"Transferred to {transfer_to}"
            else:
                call.status = CallStatus.FAILED if failed else CallStatus.COMPLETED
            call.ended_at = now
            started = call.started_at
            if started:
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                call.duration_seconds = max(0, int((now - started).total_seconds()))

            # ── Update lead status if this call was part of a campaign ──────────
            if call.lead_id:
                lead_result = await db.execute(select(Lead).where(Lead.id == call.lead_id))
                lead = lead_result.scalar_one_or_none()
                if lead and lead.status == LeadStatus.DIALING:
                    lead.last_called_at = now
                    # callee_answered=True only when wait_for_participant() succeeded (outbound)
                    # or always True for inbound (caller was already in room)
                    call_answered = callee_answered and not failed

                    if call_answered:
                        lead.status = LeadStatus.CONNECTED
                        logger.info("Lead %s → CONNECTED (call_id=%s duration=%ss)", lead.id, call.id, call.duration_seconds)
                    else:
                        lead.retry_count += 1
                        max_retries = 3
                        if lead.campaign_id:
                            camp_result = await db.execute(select(Campaign).where(Campaign.id == lead.campaign_id))
                            camp = camp_result.scalar_one_or_none()
                            if camp:
                                max_retries = camp.max_retries

                        if lead.retry_count >= max_retries:
                            lead.status = LeadStatus.NO_ANSWER if not failed else LeadStatus.FAILED
                            logger.info("Lead %s → %s (retries=%s/%s)", lead.id, lead.status, lead.retry_count, max_retries)
                        else:
                            lead.status = LeadStatus.NEW  # back to NEW for retry
                            logger.info("Lead %s → NEW for retry (attempt %s/%s)", lead.id, lead.retry_count, max_retries)

            await db.commit()

            call_id = call.id
            client_id = call.client_id

            await socket_manager.emit_call_update(
                client_id,
                {"call_id": call_id, "room_name": room_name, "status": call.status.value},
            )

        if call_id:
            await refresh_call_sentiment_from_db(call_id, client_id)
    except Exception as e:
        logger.warning("Could not finalize call_log for %s: %s", room_name, e)


async def entrypoint(ctx: JobContext):
    room_name = ctx.room.name
    logger.info(
        "Job started: room=%s | connecting to LiveKit %s (WebRTC UDP 50000-60000 must reach server)",
        room_name,
        settings.LIVEKIT_URL,
    )
    try:
        await ctx.connect()
    except Exception as e:
        logger.error(
            "Failed to connect to room %s: %s. "
            "Fix: set rtc.node_ip in LiveKit config to server LAN IP, open UDP 50000-60000, "
            "or run worker on LiveKit host with LIVEKIT_URL=ws://127.0.0.1:7880",
            room_name,
            e,
        )
        return
    logger.info("Connected to LiveKit room %s", room_name)

    room_meta = parse_metadata(getattr(ctx.room, "metadata", None))
    job_meta = parse_metadata(getattr(ctx.job, "metadata", None))

    from worker.config_loader import extract_callee_from_outbound_room

    is_outbound_room = room_name.startswith("outbound-")
    caller_number = (
        extract_callee_from_outbound_room(room_name)
        if is_outbound_room
        else extract_caller_from_room_name(room_name)
    )
    # Your business DID (number customers dial) — from metadata when LiveKit provides it
    did_number = extract_did_from_metadata(job_meta, room_meta)

    client_id = room_meta.get("client_id") or job_meta.get("client_id")
    trunk_id = job_meta.get("trunk_id") or room_meta.get("trunk_id") or job_meta.get("sip_trunk_id")

    agent_id = await resolve_agent_id(
        room_name=room_name,
        room_metadata=room_meta,
        job_metadata=job_meta,
        caller_number=caller_number,
        did_number=did_number,
        trunk_id=str(trunk_id) if trunk_id else None,
        client_id=int(client_id) if client_id else None,
        use_default_fallback=True,
    )

    if not agent_id:
        logger.error(
            "No agent_id for room=%s caller=%s did=%s — add AI agent or Dispatch rule (DID=your number, not customer)",
            room_name,
            caller_number,
            did_number,
        )
        return

    logger.info(
        "Call routing: agent_id=%s | caller(customer)=%s | did(your number)=%s | room=%s",
        agent_id,
        caller_number or "unknown",
        did_number or "not in metadata — using default/trunk agent",
        room_name,
    )

    call_id = await create_call_log(
        ctx,
        agent_id,
        caller_number,
        did_number,
        direction="outbound" if is_outbound_room else "inbound",
        callee=caller_number if is_outbound_room else None,
        campaign_id=_meta_int(room_meta, "campaign_id") or _meta_int(job_meta, "campaign_id"),
        lead_id=_meta_int(room_meta, "lead_id") or _meta_int(job_meta, "lead_id"),
    )

    session_failed = {"value": False}
    # Inbound: caller is already in room → always answered
    # Outbound: only True after wait_for_participant() succeeds (callee picks up)
    callee_answered = {"value": not is_outbound_room}
    # Holds the agent so the shutdown callback can read transfer state.
    agent_holder = {"agent": None}

    async def _on_call_end(_: str = "") -> None:
        agent = agent_holder["agent"]
        transferred = bool(getattr(agent, "_transfer_done", False)) if agent else False
        transfer_to = getattr(agent, "_transfer_to", None) if agent else None
        await finalize_call_log(
            ctx.room.name,
            failed=session_failed["value"],
            callee_answered=callee_answered["value"],
            transferred=transferred,
            transfer_to=transfer_to,
        )
        # Compute + store STT/LLM/TTS cost from accumulated usage
        if call_id:
            from worker.call_tracking import extract_and_store_call_data, persist_call_costs

            await persist_call_costs(call_id)
            # Extract structured details (name, phone, etc.) from the transcript.
            try:
                await extract_and_store_call_data(call_id)
            except Exception as e:
                logger.warning("Data extraction failed call_id=%s: %s", call_id, e)

    ctx.add_shutdown_callback(_on_call_end)

    config = await load_agent_config(agent_id)
    if not config:
        logger.error("Agent %s not found or inactive in database", agent_id)
        return

    # Lead name from campaign metadata — used for personalised greeting + LLM context
    lead_name = (room_meta.get("lead_name") or job_meta.get("lead_name") or "").strip()

    # Per-lead dynamic fields for prompt personalisation. Fetched from the lead's
    # metadata_json (populated from the uploaded CSV's extra columns).
    lead_fields: dict = {}
    _lead_id = _meta_int(room_meta, "lead_id") or _meta_int(job_meta, "lead_id")
    if _lead_id:
        try:
            import json as _json

            from sqlalchemy import select as _select

            from app.db.models.campaign import Lead
            from app.db.session import AsyncSessionLocal

            async with AsyncSessionLocal() as _db:
                _lead = (
                    await _db.execute(_select(Lead).where(Lead.id == _lead_id))
                ).scalar_one_or_none()
                if _lead:
                    if _lead.metadata_json:
                        try:
                            lead_fields = _json.loads(_lead.metadata_json) or {}
                        except (ValueError, TypeError):
                            lead_fields = {}
                    if not lead_name:
                        lead_name = (_lead.name or "").strip()
        except Exception as e:
            logger.warning("Could not load lead %s metadata: %s", _lead_id, e)

    # Normalise keys + sensible name aliases so {name}/{customer_name} always resolve.
    lead_fields = {str(k).strip().lower(): v for k, v in (lead_fields or {}).items()}
    if lead_name:
        lead_fields.setdefault("name", lead_name)
        lead_fields.setdefault("customer_name", lead_name)

    logger.info(
        "Starting agent id=%s name=%s room=%s language=%s voice=%s lead_name=%r",
        config.id,
        config.name,
        ctx.room.name,
        config.language.value,
        config.voice,
        lead_name or "(unknown)",
    )

    vad = ctx.proc.userdata.get("vad") or silero.VAD.load(
        min_silence_duration=0.42,
        prefix_padding_duration=0.35,
    )

    # ── Turn detection ────────────────────────────────────────────────────────
    # Uses TurnHandlingOptions (v1.5+ non-deprecated API) to avoid the
    # deprecation-warning bundle and gain finer control.
    #
    # AGENT_TURN_DETECTION="stt"  (default / recommended for SIP):
    #   Deepgram sends is_final after endpointing_ms=100 ms of silence.
    #   That STT final triggers EOU — completely bypasses Silero VAD for
    #   end-of-turn decisions, so SIP background noise has no effect.
    #   Timeline: speech ends → Deepgram final (100 ms) → min_delay (300 ms)
    #             → agent responds.  Total: ~400 ms from last syllable.
    #
    # AGENT_TURN_DETECTION="vad":
    #   Falls back to Silero silence-threshold approach (sensitive to noise).
    #
    # VAD is still passed so it can gate audio-to-STT and handle interruptions.
    _turn_opts = TurnHandlingOptions(
        turn_detection=settings.AGENT_TURN_DETECTION,
        endpointing={
            "mode": "fixed",
            "min_delay": settings.AGENT_MIN_ENDPOINTING_DELAY,   # 0.30 s floor
            "max_delay": settings.AGENT_MAX_ENDPOINTING_DELAY,   # 1.5 s safety net
        },
        interruption={
            "enabled": config.interruptions_enabled,
            "min_duration": 0.35,
            "resume_false_interruption": True,
        },
        preemptive_generation={
            "enabled": settings.AGENT_PREEMPTIVE_GENERATION,
        },
    )
    session = AgentSession(
        vad=vad,
        turn_handling=_turn_opts,
    )

    @session.on("error")
    def _on_session_error(_ev) -> None:
        session_failed["value"] = True

    @session.on("close")
    def _on_session_close(ev) -> None:
        # Do NOT mark failed on normal participant-disconnect close.
        # livekit-agents sets ev.error when close_on_disconnect fires (caller hangs up)
        # — that is a successful call end, not a failure.
        # Only mark failed when the session crashed (error not related to disconnect).
        error = getattr(ev, "error", None)
        if error:
            err_str = str(error).lower()
            if "disconnect" not in err_str and "participant" not in err_str:
                session_failed["value"] = True

    if call_id:
        attach_call_listeners(session, call_id, config.client_id)

    # Build personalised greeting. Substitute {tokens} from the lead's fields first;
    # if the greeting has NO tokens but we know the lead's name, prepend a friendly
    # first-name hello (backwards-compatible with greetings that don't use tokens).
    greeting = config.greeting or ""
    had_token = "{" in greeting
    greeting = _personalize(greeting, lead_fields)
    if is_outbound_room and lead_name and not had_token:
        first_name = lead_name.split()[0]
        greeting = f"Hi {first_name}! {greeting}"
    if lead_fields:
        logger.info("Personalised greeting for lead=%r: %r", lead_name, greeting)

    voice_agent = DynamicVoiceAgent(config, greeting, lead_name=lead_name, lead_fields=lead_fields)
    agent_holder["agent"] = voice_agent  # let _on_call_end read transfer state

    from app.services.phone_utils import sip_participant_identity

    sip_identity = None
    if is_outbound_room:
        expected = sip_participant_identity(caller_number) if caller_number else None
        logger.info(
            "Outbound: waiting for SIP participant to join room (expected_identity=%s, timeout=60s)",
            expected,
        )
        try:
            participant = await asyncio.wait_for(
                ctx.wait_for_participant(identity=expected) if expected else ctx.wait_for_participant(),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Outbound: callee did not join within 60s room=%s — phone may not have rung or was declined",
                room_name,
            )
            return

        sip_identity = participant.identity
        logger.info(
            "Outbound: SIP participant joined room identity=%s (checking answer status...)",
            sip_identity,
        )

        # ── Detect actual callee answer via sip.callStatus attribute ──────────────
        # LiveKit adds the SIP participant to the room the moment the outbound dial
        # is initiated (ringing phase), NOT when the callee picks up.
        # wait_for_participant() therefore returns immediately for every outbound room.
        # We must wait for participant attribute sip.callStatus == "active" which
        # LiveKit sets only after SIP 200 OK (callee answered).
        #
        # Fallback: if sip.callStatus is absent (older LiveKit), we assume answered
        # to preserve backward compatibility.
        # call_resolved fires on sip.callStatus == "active" (answered) OR "bye" (rejected/ended)
        # This lets us exit immediately instead of waiting the full 55 s timeout.
        call_resolved_event = asyncio.Event()
        sip_call_answered = {"value": False}

        def _check_sip_status(attrs: dict) -> None:
            status = attrs.get("sip.callStatus", "")
            if status:
                logger.info("Outbound: sip.callStatus=%r identity=%s", status, sip_identity)
            if status == "active":
                sip_call_answered["value"] = True
                call_resolved_event.set()
            elif status in ("bye", "disconnected"):
                call_resolved_event.set()  # ended without answer — exit immediately

        def _on_sip_attrs(changed_attrs: dict, p) -> None:
            if p.identity == sip_identity:
                merged = {**(dict(p.attributes) if p.attributes else {}), **changed_attrs}
                _check_sip_status(merged)

        # Register listener BEFORE reading current attrs (avoids race condition)
        ctx.room.on("participant_attributes_changed", _on_sip_attrs)

        current_attrs: dict = {}
        try:
            if hasattr(participant, "attributes") and participant.attributes:
                current_attrs = dict(participant.attributes)
        except Exception:
            pass
        logger.info("Outbound: initial participant attributes=%s", current_attrs)

        if "sip.callStatus" not in current_attrs:
            # Attributes may arrive asynchronously — wait up to 3 s for first delivery
            try:
                await asyncio.wait_for(call_resolved_event.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pass  # no attributes yet; will re-check below

            if not call_resolved_event.is_set():
                # Re-fetch after brief wait
                try:
                    if hasattr(participant, "attributes") and participant.attributes:
                        current_attrs = dict(participant.attributes)
                except Exception:
                    pass

            if "sip.callStatus" not in current_attrs and not call_resolved_event.is_set():
                # Old LiveKit without SIP attribute support — fall back to original behavior
                logger.warning(
                    "Outbound: sip.callStatus attribute not present — assuming answered "
                    "(upgrade LiveKit SIP >= 1.7 for accurate answered detection)"
                )
                callee_answered["value"] = True
        else:
            _check_sip_status(current_attrs)

        if not call_resolved_event.is_set() and not callee_answered["value"]:
            # Wait for "active" or "bye" — exit as soon as either fires (max 55 s)
            try:
                await asyncio.wait_for(call_resolved_event.wait(), timeout=55.0)
            except asyncio.TimeoutError:
                logger.info(
                    "Outbound: callee did not answer (timeout, no sip.callStatus change) room=%s",
                    room_name,
                )
            finally:
                try:
                    ctx.room.off("participant_attributes_changed", _on_sip_attrs)
                except Exception:
                    pass

            if not sip_call_answered["value"]:
                # Not answered — shutdown callback will mark lead NO_ANSWER / retry
                return
        else:
            try:
                ctx.room.off("participant_attributes_changed", _on_sip_attrs)
            except Exception:
                pass

        if sip_call_answered["value"]:
            callee_answered["value"] = True
            logger.info(
                "Outbound: callee answered (sip.callStatus=active) identity=%s",
                sip_identity,
            )

    elif caller_number:
        sip_identity = sip_participant_identity(caller_number)
    telephony_hz = settings.AGENT_AUDIO_SAMPLE_RATE
    room_input = room_io.RoomInputOptions(
        participant_identity=sip_identity,
        close_on_disconnect=True,
        audio_sample_rate=telephony_hz,
        audio_num_channels=1,
    )
    room_output = room_io.RoomOutputOptions(
        sync_transcription=False,
        audio_sample_rate=telephony_hz,
        audio_num_channels=1,
    )

    record = session_record_options() if should_record_call(config.record_calls) else False

    # Give the agent what it needs to perform a SIP transfer if the LLM calls the tool.
    voice_agent._ctx = ctx
    voice_agent._sip_identity = sip_identity

    await session.start(
        voice_agent,
        room=ctx.room,
        room_input_options=room_input,
        room_output_options=room_output,
        record=record,
    )

    if should_record_call(config.record_calls):

        async def _save_recording_on_shutdown(_: str = "") -> None:
            await persist_session_artifacts(ctx, session, call_id=call_id)

        ctx.add_shutdown_callback(_save_recording_on_shutdown)
        logger.info(
            "Session recording enabled; files saved under %s after each call",
            recording_path_for_room(ctx.room.name).parent,
        )


def _resolve_livekit_agent_name() -> str:
    """Read after load_dotenv; export to os.environ so dev watcher child processes inherit it."""
    name = (os.getenv("LIVEKIT_AGENT_NAME") or settings.LIVEKIT_AGENT_NAME or "vbots").strip()
    if not name:
        name = "vbots"
    os.environ["LIVEKIT_AGENT_NAME"] = name
    return name


if __name__ == "__main__":
    agent_name = _resolve_livekit_agent_name()
    logger.info(
        "VBots worker | LiveKit=%s | agent_name=%r | env_file=%s",
        settings.LIVEKIT_URL,
        agent_name,
        _ENV_PATH,
    )
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            ws_url=settings.LIVEKIT_URL,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
            agent_name=agent_name,
            # Windows: prefer start over dev (dev file-watcher is unstable)
            num_idle_processes=1,
        )
    )
