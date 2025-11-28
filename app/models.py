from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, func, Enum
from app.database import Base
from datetime import datetime, timezone
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(225), unique=True, index=True)
    password = Column(String, nullable=False)
    presence_status = Column(String, default="offline")
    last_seen = Column(DateTime(timezone=True))

class Messages(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(Enum("pending", "delivered", "read", name="message_status"), default="pending")

    author = relationship("User", foreign_keys=[author_id])
    recipient = relationship("User", foreign_keys=[recipient_id])