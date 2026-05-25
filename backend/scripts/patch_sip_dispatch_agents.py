"""
Patch LiveKit SIP dispatch rules to dispatch the AI agent worker.

Run: python scripts/patch_sip_dispatch_agents.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from livekit import api

from app.services.livekit_service import LiveKitService

# Trunk ST_eW8z8rKnrNuY -> +911204646549
TARGET_DID = "+911204646549"


async def main():
    lk = LiveKitService()
    rules = await lk.list_dispatch_rules()
    items = list(getattr(rules, "items", None) or [])
    if not items:
        print("No SIP dispatch rules found.")
        return

    trunks = await lk.list_inbound_trunks()
    trunk_by_id = {
        getattr(t, "sip_trunk_id", ""): list(getattr(t, "numbers", []) or [])
        for t in (getattr(trunks, "items", None) or [])
    }

    meta = {"agent_id": 1, "source": "vbots-patch"}

    # Remove catch-all rules (empty trunk_ids) — they block per-trunk updates
    for r in items[:]:
        rid = getattr(r, "sip_dispatch_rule_id", "")
        tids = list(getattr(r, "trunk_ids", []) or [])
        if not tids:
            print(f"Deleting catch-all rule {rid} (no trunk_ids)...")
            try:
                await lk.delete_dispatch_rule(rid)
                items.remove(r)
                print("  OK")
            except Exception as e:
                print(f"  ERROR: {e}")

    for r in items:
        rid = getattr(r, "sip_dispatch_rule_id", "")
        tids = list(getattr(r, "trunk_ids", []) or [])
        nums = []
        for tid in tids:
            nums.extend(trunk_by_id.get(tid, []))
        label = f"{rid} trunks={tids} numbers={nums}"
        print(f"Patching {label} ...")
        try:
            await lk.update_dispatch_rule_agent(r, meta)
            print("  OK — agent dispatch attached")
            if TARGET_DID in nums:
                print(f"  >>> This rule handles {TARGET_DID}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\nDone. Call +911204646549 — worker should log 'received job request'")
    print("Worker: python worker/agent.py start  (use start, not dev, on Windows)")


if __name__ == "__main__":
    asyncio.run(main())
