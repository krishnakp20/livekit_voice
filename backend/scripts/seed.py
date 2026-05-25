"""Seed database with demo client and admin user.

Run from backend directory:
    python scripts/seed.py
"""

import asyncio
import sys
from pathlib import Path

# Allow imports when run as: python scripts/seed.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.base import Base
from app.db.models.ai_agent import AIAgent, AIProvider, Language
from app.db.models.client import Client, ClientStatus
from app.db.models.user import User, UserRole
from app.db.session import engine, AsyncSessionLocal


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Client).where(Client.slug == "demo"))
        if existing.scalar_one_or_none():
            print("Demo data already exists")
            return

        client = Client(
            name="Demo Company",
            slug="demo",
            email="admin@demo.com",
            phone="+919876543210",
            status=ClientStatus.ACTIVE,
        )
        db.add(client)
        await db.flush()

        admin = User(
            client_id=client.id,
            email="admin@demo.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Demo Admin",
            role=UserRole.CLIENT_ADMIN,
        )
        db.add(admin)

        agent = AIAgent(
            client_id=client.id,
            name="Priya Sales Agent",
            slug="priya-sales-agent",
            language=Language.HINGLISH,
            voice="simran",
            provider=AIProvider.SARVAM,
            model="gpt-4o-mini",
            prompt="You are a friendly Indian sales agent for Demo Company. Be helpful and concise.",
            greeting="Namaste! Kaise madad kar sakti hoon?",
            fallback_message="Maaf kijiye, dobara batayenge?",
            temperature=0.6,
            max_tokens=120,
        )
        db.add(agent)
        await db.commit()
        print("Seeded: admin@demo.com / admin123")


if __name__ == "__main__":
    asyncio.run(seed())
