"""Initialize database tables and seed initial data."""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.database.session import create_tables
from app.models.database.user import User, UserRole
from app.services.auth_service import hash_password
from app.utils.helpers import generate_uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_db():
    """Create tables and optionally seed admin user."""
    logger.info("Initializing database...")
    await create_tables()
    logger.info("Database tables created successfully")

    # Create default admin user
    from app.services.database.session import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "admin@academic-os.com"))
        if not result.scalar_one_or_none():
            admin = User(
                id=generate_uuid(),
                email="admin@academic-os.com",
                username="admin",
                hashed_password=hash_password("Admin@123456"),
                full_name="System Administrator",
                role=UserRole.ADMIN,
                is_active=True,
                is_verified=True,
            )
            db.add(admin)
            await db.commit()
            logger.info("Default admin user created: admin@academic-os.com / Admin@123456")
        else:
            logger.info("Admin user already exists")


if __name__ == "__main__":
    asyncio.run(init_db())