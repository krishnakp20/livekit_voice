"""Phone normalization for SIP dial and LiveKit participant identity."""

import re


def _normalize_digits(phone: str) -> str:
    """Extract digits, strip leading zeros, auto-prepend India country code for 10-digit numbers.

    The 10-digit rule only fires for numbers that actually look like Indian
    mobiles (leading 6-9) — a bare 10-digit foreign number (e.g. a UK number
    that happens to also be 10 digits) must NOT get "91" prepended, since that
    corrupts sip_participant_identity() and makes it mismatch the real SIP
    participant identity LiveKit-SIP assigns from the raw caller ID.
    """
    digits = re.sub(r"\D", "", phone or "")
    # Strip leading zeros (e.g. 09911362206 → 9911362206)
    stripped = digits.lstrip("0")
    digits = stripped if stripped else digits
    if len(digits) == 10 and digits[0] in "6789":
        digits = "91" + digits
    return digits


def format_phone_for_sip(phone: str) -> str:
    """Return E.164 format (+91XXXXXXXXXX) suitable for SIP INVITE."""
    digits = _normalize_digits(phone)
    return f"+{digits}" if digits else ""


def sip_participant_identity(phone: str) -> str:
    """LiveKit SIP participant identity — must match worker RoomInputOptions."""
    digits = _normalize_digits(phone)
    return f"sip_{digits}" if digits else "sip_callee"
