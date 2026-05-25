"""Phone normalization for SIP dial and LiveKit participant identity."""

import re


def _normalize_digits(phone: str) -> str:
    """Extract digits, strip leading zeros, auto-prepend India country code for 10-digit numbers."""
    digits = re.sub(r"\D", "", phone or "")
    # Strip leading zeros (e.g. 09911362206 → 9911362206)
    stripped = digits.lstrip("0")
    digits = stripped if stripped else digits
    if len(digits) == 10:
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
