"""User database model."""

from sqlalchemy import Column, String, Boolean, DateTime, Enum as SAEnum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.services.database.session import Base
from app.utils.helpers import generate_uuid


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    FACULTY = "faculty"
    HOD = "hod"
    STUDENT = "student"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.FACULTY, nullable=False)
    institution_id = Column(String(36), nullable=True, index=True)
    department = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    avatar_url = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    courses = relationship("Course", back_populates="creator", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"