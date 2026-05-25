"""
Re-apply all VBots dispatch rules to LiveKit with agent_name=vbots.

Run from backend/:
  python scripts/repair_inbound_dispatch.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from sqlalchemy import select

from app.db.models.ai_agent import AIAgent
from app.db.models.dispatch_rule import DispatchRule
from app.db.session import AsyncSessionLocal
from app.services.livekit_service import livekit_service, livekit_worker_agent_name
from app.api.v1.routes.dispatch import _agent_metadata


async def main() -> None:
    agent_name = livekit_worker_agent_name()
    print(f"Repairing inbound dispatch (worker agent_name={agent_name!r})")

    rules_resp = await livekit_service.list_dispatch_rules()
    lk_rules = list(getattr(rules_resp, "items", None) or [])

    async with AsyncSessionLocal() as db:
        db_rules = (await db.execute(select(DispatchRule))).scalars().all()
        agents = {a.id: a for a in (await db.execute(select(AIAgent))).scalars().all()}

        for rule in db_rules:
            agent = agents.get(rule.agent_id)
            if not agent:
                print(f"  skip rule {rule.id}: agent {rule.agent_id} missing")
                continue
            lk = next(
                (r for r in lk_rules if getattr(r, "sip_dispatch_rule_id", None) == rule.livekit_rule_id),
                None,
            )
            if not lk:
                print(f"  skip rule {rule.id}: LiveKit rule {rule.livekit_rule_id} not found")
                continue
            meta = _agent_metadata(agent, rule.client_id, rule)
            await livekit_service.update_dispatch_rule_agent(lk, meta)
            print(f"  OK rule {rule.id} -> agent {agent.id} ({agent.name}) lk={rule.livekit_rule_id}")

    rules_resp = await livekit_service.list_dispatch_rules()
    for r in getattr(rules_resp, "items", []) or []:
        rc = getattr(r, "room_config", None)
        agents = list(getattr(rc, "agents", []) or []) if rc else []
        names = [getattr(a, "agent_name", "") for a in agents]
        print(f"Verify {getattr(r, 'sip_dispatch_rule_id', '')}: agent_names={names}")

    print("\nDone. Call your DID — worker should log 'received job request'.")


if __name__ == "__main__":
    asyncio.run(main())
