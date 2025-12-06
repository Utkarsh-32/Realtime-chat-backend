# Realtime Chat Backend (FastAPI + WebSockets + Redis)
*A fully asynchronous realtime chat backend built with FastAPI, WebSockets, Redis Pub/Sub, and PostgreSQL*
*designed to behave like a miniature production messaging system.*

*Includes authentication, presence-tracking, group chats, image uploads, rate-limiting, and offline*
*message delivery*

**Backend URL: 👉 [Realtime Chat Backend](https://realtime-chat-backend-ds2b.onrender.com)**

---

## 🚀 Features
- Async FastAPI backend
- JWT Authentication (access tokens)
- Realtime messaging (1-1 + groups)
- Redis Pub/Sub broadcasting accross processes/servers
- Presence indicators (online/offline + last seen)
- Read receipts (both direct and group messaging)
- Offline delivery (pending messages stored and sent when user reconnects)
- Group Chats
- Image uploads (stored locally)
- Rate limiting (redis based)
- PostgreSQL + SQLAlchemy ORM
- Dockerized Backend + Postgres + Redis
- CI/CD via GitHub Actions
- Deployed Backend (Render)

---

## 🧰 Tech Stack

**Layer** | **Tech**
--------- | --------
Backend | FastAPI, WebSockets, SQLAlchemy, Alembic

Database | PostgreSQL

Cache/Realtime | Redis (Pub/Sub)

Auth | JWT (PyJWT)

Deployment | Docker, Render


## 🏗️ Architecture Overview
The system uses:
- WebSockets for persistent client connections
- Redis Pub/Sub to fan-out messages to any 
  connected server instance
- PostgreSQL to store users, messages, groups
  and read states
- Async event loop for concurrency
- Connection manager for tracking online users
- Background subscriber task for receiving pub/
  sub events

### High level flow:
Client -> Access Token -> WebSocket -> Send Message
-> Redis -> Broadcast -> Connection Manager ->
Recipient -> DB(pending/offline messages)

### Group chat flow: 
Client -> WS -> group_message -> Redis("group:<id>")
-> Subscriber -> Fetch group members -> Fan-out to 
all online members -> Stored in DB for offline users


## 🏞️ Image Uploads
**Upload endpoint:**
``` bash
    POST upload/image
```

**Returns:**
```json
    {
        "filename": "uuid.png",
        "url": "/media/uuid.png"
    }
```

**Messages may contain:**
- Message text
- image_url
- or both


## 👬 Group chat support
**Endpoints include:**
``` bash
    POST /groups/create-group
    POST /groups/{group_id}/add-member?user_id=
    GET /groups/all
    GET /groups/{group_id}/messages
```
**WebSocket Message Format:**
```json
    {
        "type": "group_message",
        "group_id": 1,
        "message": "Hello everyone"
    }
```

**Unread Syncing:**
- Server queries unread GroupMessage.id > last_read_message_id
- Sends them to user at login
- Updates GroupMember.last_read_message_id automatically


## 🔒 Rate Limiting
**Redis-based per-user limits:**
- 20 messages/min(direct)
- 30 messages/min(group)

**Returns structured error:**
```json
{"type": "error", "reason": "rate limit exceeded"}
```

## 🔌 WebSocket Protocol
**Messages may include:**
```bash
- type: "message"
- type: "group_message"
- type: "read"
- type: "presence"
- type: "read_receipt"
```

## 🚞 Deployment
- **Backend**: Render(Docker)
- **URL**: [Realtime Chat Backend](https://realtime-chat-backend-ds2b.onrender.com)


**🧹 Code Quality & CI**
- flake8 for linting and style checks
- Pytest for automated testing
- GitHub Actions run tests + lint checks
  on every push
- Dockerfile is production ready
- Structured logging using pythons logging module