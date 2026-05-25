"""Load AI agent configuration from MySQL for the LiveKit worker."""

import json
import os
import re
from typing import Any, Optional

from sqlalchemy import or_, select

from app.db.models.ai_agent import AIAgent, Language
from app.db.models.dispatch_rule import DispatchRule, DispatchType
from app.db.session import AsyncSessionLocal

# agent-2-abc123 (VBots dispatch)
_AGENT_ROOM_RE = re.compile(r"^agent-(\d+)", re.I)
# LiveKit SIP: call-_+917290093903_xxx — number is usually the CALLER (customer), not your DID
_CALL_ROOM_PHONE_RE = re.compile(r"call[-_]*\+?(\d{10,15})", re.I)
# Campaign / API outbound: outbound-{agent_id}-{phone}
_OUTBOUND_ROOM_RE = re.compile(r"^outbound-(\d+)-(\d{10,15})", re.I)
_PHONE_IN_STRING_RE = re.compile(r"\+?(\d{10,15})")


def agent_id_from_room_name(room_name: str) -> Optional[int]:
    name = room_name or ""
    match = _AGENT_ROOM_RE.match(name)
    if match:
        return int(match.group(1))
    ob = _OUTBOUND_ROOM_RE.match(name)
    if ob:
        return int(ob.group(1))
    return None


def extract_callee_from_outbound_room(room_name: str) -> Optional[str]:
    ob = _OUTBOUND_ROOM_RE.match(room_name or "")
    if ob:
        return normalize_phone(ob.group(2))
    return None


def extract_caller_from_room_name(room_name: str) -> Optional[str]:
    """
    Customer phone from room name (who is calling).
    Example: call-_+917290093903_xxx → 917290093903 (customer 7290093903 with country code 91).
    Do NOT use this for DID → agent routing.
    """
    if not room_name:
        return None
    m = _CALL_ROOM_PHONE_RE.search(room_name)
    if m:
        return normalize_phone(m.group(1))
    for m in _PHONE_IN_STRING_RE.finditer(room_name):
        digits = m.group(1)
        if len(digits) >= 10:
            return normalize_phone(digits)
    return None


# Backward-compatible alias
extract_phone_from_room_name = extract_caller_from_room_name


def normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def phone_match_variants(phone: str) -> list[str]:
    n = normalize_phone(phone)
    if not n:
        return []
    variants = {n, f"+{n}"}
    if len(n) > 10:
        variants.add(n[-10:])
        variants.add(f"+91{n[-10:]}")
    return list(variants)


def parse_metadata(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def extract_did_from_metadata(*metas: Any) -> Optional[str]:
    """Business number that was called (your DID), from SIP/LiveKit metadata only."""
    for raw in metas:
        meta = parse_metadata(raw)
        for key in ("did", "called_number", "to", "destination", "trunk_phone", "inbound_did"):
            val = meta.get(key)
            if val:
                return normalize_phone(str(val))
    return None


async def lookup_agent_by_did(
    did_number: str,
    client_id: Optional[int] = None,
) -> Optional[int]:
    """Match dispatch rule where match_value = YOUR DID (number customers dial)."""
    variants = phone_match_variants(did_number)
    if not variants:
        return None

    async with AsyncSessionLocal() as db:
        query = select(DispatchRule).where(
            DispatchRule.rule_type == DispatchType.DID,
            DispatchRule.is_active == True,
            or_(*[DispatchRule.match_value == v for v in variants]),
        )
        if client_id:
            query = query.where(DispatchRule.client_id == client_id)

        result = await db.execute(query.order_by(DispatchRule.priority.desc()).limit(1))
        rule = result.scalar_one_or_none()
        if rule:
            return rule.agent_id

        all_rules = await db.execute(
            select(DispatchRule).where(
                DispatchRule.rule_type == DispatchType.DID,
                DispatchRule.is_active == True,
                *([DispatchRule.client_id == client_id] if client_id else []),
            )
        )
        n = normalize_phone(did_number)
        for rule in all_rules.scalars().all():
            mv = normalize_phone(rule.match_value)
            if mv and (mv == n or n.endswith(mv) or mv.endswith(n[-10:] if len(n) >= 10 else n)):
                return rule.agent_id

    return None


async def lookup_agent_by_trunk(
    trunk_ref: str,
    client_id: Optional[int] = None,
) -> Optional[int]:
    """Match dispatch rule by LiveKit trunk id (ST_xxx), rule id, or linked sip_trunks row."""
    ref = (trunk_ref or "").strip()
    if not ref:
        return None

    async with AsyncSessionLocal() as db:
        from app.db.models.sip_trunk import SIPTrunk

        trunk_db_id: Optional[int] = None
        if ref.startswith("ST_"):
            trunk_row = await db.execute(
                select(SIPTrunk).where(SIPTrunk.livekit_trunk_id == ref).limit(1)
            )
            trunk = trunk_row.scalar_one_or_none()
            if trunk:
                trunk_db_id = trunk.id
                did_rule = await lookup_agent_by_did(trunk.did_numbers or "", client_id)
                if did_rule:
                    return did_rule

        query = select(DispatchRule).where(
            DispatchRule.is_active == True,
            or_(
                DispatchRule.match_value == ref,
                DispatchRule.livekit_rule_id == ref,
                *([DispatchRule.sip_trunk_id == trunk_db_id] if trunk_db_id else []),
            ),
        )
        if client_id:
            query = query.where(DispatchRule.client_id == client_id)
        result = await db.execute(query.order_by(DispatchRule.priority.desc()).limit(1))
        rule = result.scalar_one_or_none()
        if rule:
            return rule.agent_id

        if trunk_db_id and client_id:
            result = await db.execute(
                select(DispatchRule)
                .where(
                    DispatchRule.client_id == client_id,
                    DispatchRule.sip_trunk_id == trunk_db_id,
                    DispatchRule.is_active == True,
                )
                .order_by(DispatchRule.priority.desc())
                .limit(1)
            )
            rule = result.scalar_one_or_none()
            if rule:
                return rule.agent_id

    return None


async def get_default_agent_id(client_id: Optional[int] = None) -> Optional[int]:
    env_id = os.getenv("DEFAULT_AGENT_ID", "").strip()
    if env_id.isdigit():
        return int(env_id)

    async with AsyncSessionLocal() as db:
        query = select(AIAgent).where(AIAgent.is_active == True)
        if client_id:
            query = query.where(AIAgent.client_id == client_id)
        result = await db.execute(query.order_by(AIAgent.id.asc()).limit(1))
        agent = result.scalar_one_or_none()
        return agent.id if agent else None


async def resolve_agent_id(
    *,
    room_name: str,
    room_metadata: Any = None,
    job_metadata: Any = None,
    caller_number: Optional[str] = None,
    did_number: Optional[str] = None,
    trunk_id: Optional[str] = None,
    client_id: Optional[int] = None,
    use_default_fallback: bool = True,
) -> Optional[int]:
    """
    Resolve which ai_agents.id handles the call.

    Important:
    - caller_number (7290093903, 9911362206) = customer who called — used for logs only
    - did_number = YOUR business DID that received the call — used for DID dispatch rules
    - Room name phone is treated as CALLER, not DID
    """
    for source in (job_metadata, room_metadata):
        meta = parse_metadata(source)
        if meta.get("agent_id"):
            return int(meta["agent_id"])
        if client_id is None and meta.get("client_id"):
            client_id = int(meta["client_id"])

    from_room = agent_id_from_room_name(room_name)
    if from_room:
        return from_room

    # DID from metadata only (not from room name)
    did = did_number or extract_did_from_metadata(job_metadata, room_metadata)
    if did:
        agent_id = await lookup_agent_by_did(did, client_id)
        if agent_id:
            return agent_id

    trunk_ref = trunk_id or parse_metadata(job_metadata).get("trunk_id") or parse_metadata(room_metadata).get(
        "trunk_id"
    )
    if trunk_ref:
        agent_id = await lookup_agent_by_trunk(str(trunk_ref), client_id)
        if agent_id:
            return agent_id

    if use_default_fallback:
        return await get_default_agent_id(client_id)

    return None


async def load_agent_config(agent_id: int) -> Optional[AIAgent]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AIAgent).where(AIAgent.id == agent_id, AIAgent.is_active == True)
        )
        return result.scalar_one_or_none()


def language_to_sarvam_code(language: Language) -> str:
    mapping = {
        Language.HINDI: "hi-IN",
        Language.ENGLISH: "en-IN",
        Language.HINGLISH: "hi-IN",
    }
    return mapping.get(language, "hi-IN")


_BULBUL_V2_SPEAKERS = {
    "anushka",
    "manisha",
    "vidya",
    "arya",
    "abhilash",
    "karun",
    "hitesh",
}
_BULBUL_V3_SPEAKERS = {
    "simran",
    "priya",
    "kavya",
    "ritu",
    "pooja",
    "ishita",
    "shreya",
    "neha",
    "suhani",
    "rupali",
    "tanya",
    "shruti",
    "kavitha",
    "shubh",
    "rahul",
    "amit",
}
# UI names → speaker id per TTS model
_VOICE_ALIASES_V2 = {"simran": "anushka", "priya": "manisha", "kavya": "vidya", "meera": "arya"}
_VOICE_ALIASES_V3 = {"meera": "ishita"}


def voice_to_sarvam_speaker(voice: str | None, *, tts_model: str = "bulbul:v2") -> str:
    raw = (voice or "simran").strip().lower()
    use_v3 = "bulbul:v3" in (tts_model or "")
    if use_v3:
        if raw in _BULBUL_V3_SPEAKERS:
            return raw
        return _VOICE_ALIASES_V3.get(raw, "simran")
    if raw in _BULBUL_V2_SPEAKERS:
        return raw
    return _VOICE_ALIASES_V2.get(raw, "anushka")
