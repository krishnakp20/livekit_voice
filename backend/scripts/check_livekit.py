"""
Check LiveKit connectivity, SIP trunks, dispatch rules, and agent worker registration.

Run: python scripts/check_livekit.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.core.config import settings
from app.services.livekit_service import LiveKitService


async def main():
    print("=" * 60)
    print("VBots LiveKit diagnostics")
    print("=" * 60)
    print(f"LIVEKIT_URL:     {settings.LIVEKIT_URL}")
    print(f"LIVEKIT_API_KEY: {settings.LIVEKIT_API_KEY[:8]}..." if settings.LIVEKIT_API_KEY else "MISSING")
    print(f"Agent name:      {settings.LIVEKIT_AGENT_NAME or '(empty — any worker)'}")
    print()

    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        print("ERROR: Set LIVEKIT_API_KEY and LIVEKIT_API_SECRET in .env")
        return

    lk = LiveKitService()

    print("--- SIP Inbound Trunks ---")
    try:
        trunks = await lk.list_inbound_trunks()
        items = getattr(trunks, "items", None) or []
        if not items:
            print("  NONE — create inbound trunk in LiveKit or VBots UI + Sync")
        for t in items:
            tid = getattr(t, "sip_trunk_id", None) or getattr(t, "id", "?")
            name = getattr(t, "name", "?")
            nums = getattr(t, "numbers", [])
            print(f"  - {name} id={tid} numbers={list(nums)}")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n--- SIP Dispatch Rules ---")
    try:
        rules = await lk.list_dispatch_rules()
        items = getattr(rules, "items", None) or []
        if not items:
            print("  NONE — inbound calls will NOT create rooms")
        for r in items:
            rid = getattr(r, "sip_dispatch_rule_id", None) or getattr(r, "id", "?")
            print(f"  - rule_id={rid} trunk_ids={getattr(r, 'trunk_ids', [])}")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n--- Checklist if calls do not arrive ---")
    print("  1. SIP provider must send INVITE to LiveKit server IP (UDP 5060)")
    print(f"     Your LiveKit: {settings.LIVEKIT_URL}")
    print("  2. Firewall: open UDP 5060, TCP 7880, UDP 50000-60000")
    print("  3. LiveKit config: sip.enabled = true")
    print("  4. Inbound trunk + SIP dispatch rule in LiveKit")
    print("  5. Agent worker running: python worker/agent.py start")
    print(f"  6. Agent dispatch name must match LIVEKIT_AGENT_NAME if set")
    print("  7. Worker logs must show 'received job request' when you call")
    print("  8. SIP dispatch must include AI agent — run: python scripts/patch_sip_dispatch_agents.py")
    print()


if __name__ == "__main__":
    asyncio.run(main())
