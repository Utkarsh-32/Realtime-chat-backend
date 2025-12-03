import logging
import os
from typing import AsyncIterator

import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

logger = logging.getLogger(__name__)
redis_client: aioredis.Redis | None = None

host = os.getenv("REDIS_HOST", "localhost")
port = int(os.getenv("REDIS_PORT", 6379))
db = int(os.getenv("REDIS_DB", 0))


async def init_redis(app: FastAPI):
    global redis_client

    redis_client = aioredis.Redis(host=host, port=port, db=db)
    try:
        redis_client.ping()
    except Exception:
        logger.error("Redis unavailable during startup", exc_info=True)
        raise RuntimeError("Redis is unavailable during startup")

    app.state.redis = redis_client


async def close_redis(app: FastAPI):
    global redis_client
    if redis_client:
        try:
            await redis_client.close()
            await redis_client.connection_pool.disconnect()
        except Exception:
            logger.error("Redis error during shutdown", exc_info=True)
            pass
        redis_client = None
        app.state.redis = None


async def get_redis() -> AsyncIterator[aioredis.Redis]:
    yield redis_client  # type: ignore
