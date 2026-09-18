"""Create (or update) a SUPER ADMIN user with NO client — can oversee all clients.

Run from the backend directory:
    python scripts/create_superadmin.py

Override the defaults via env vars:
    SUPERADMIN_EMAIL=boss@vbots.ai SUPERADMIN_PASSWORD=Strong#123 \
    SUPERADMIN_NAME="Platform Owner" python scripts/create_superadmin.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.models.user import User, UserRole
from app.db.session import AsyncSessionLocal


async def main() -> None:
    email = os.getenv("SUPERADMIN_EMAIL", "superadmin@vbots.ai").strip().lower()
    password = os.getenv("SUPERADMIN_PASSWORD", "ChangeMe#123")
    name = os.getenv("SUPERADMIN_NAME", "Super Admin")

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        user = existing.scalar_one_or_none()
        if user:
            # Promote / reset the existing user to a clientless super admin.
            user.role = UserRole.SUPER_ADMIN
            user.client_id = None
            user.is_active = True
            user.hashed_password = get_password_hash(password)
            user.full_name = name
            await db.commit()
            print(f"Updated existing user '{email}' → SUPER_ADMIN (client_id=NULL)")
        else:
            user = User(
                client_id=None,            # NULL = not tied to any client
                email=email,
                hashed_password=get_password_hash(password),
                full_name=name,
                role=UserRole.SUPER_ADMIN,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            print(f"Created SUPER_ADMIN '{email}' (client_id=NULL)")

    print(f"Login: {email} / {password}")
    print("⚠️  Change the password after first login.")


if __name__ == "__main__":
    asyncio.run(main())
