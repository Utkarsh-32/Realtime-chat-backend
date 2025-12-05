from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


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
    message = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String, default="pending")
    image_url = Column(String, nullable=True)

    author = relationship("User", foreign_keys=[author_id])
    recipient = relationship("User", foreign_keys=[recipient_id])


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(225))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id = Column(Integer, ForeignKey("groups.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role = Column(String(50))
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    last_read_message_id = Column(Integer, default=0)


class GroupMessage(Base):
    __tablename__ = "group_messages"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(20), default="pending")
    image_url = Column(String, nullable=True)

    author = relationship("User", foreign_keys=[author_id])
    group = relationship("Group", foreign_keys=[group_id])
