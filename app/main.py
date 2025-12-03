import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app.redis_client import close_redis, get_redis, init_redis
from app.redis_subscriber import start_redis_listener
from app.routers import auth, groups, messages, uploads, users, ws
from app.routers.ws import CHAT_CHANNEL, PRESENCE_CHANNEL, READ_CHANNEL
from app.logging_config import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis(app)  # type: ignore
    logger.info("Redis initialized")
    redis = app.state.redis
    app.state.redis_task = await start_redis_listener(redis, channels=(CHAT_CHANNEL, PRESENCE_CHANNEL, READ_CHANNEL))
    logger.info("Fastapi lifespan startup complete")
    try:
        yield
    finally:
        logger.info("Fastapi shutting down")
        task = getattr(app.state, "redis_task", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await close_redis(app)  # type: ignore

logger = logging.getLogger(__name__)
setup_logging()
app = FastAPI(lifespan=lifespan)

app.mount("/media", StaticFiles(directory="media"), name="media")

app.include_router(users.router)
app.include_router(auth.router)
app.include_router(messages.router)
app.include_router(ws.router)
app.include_router(uploads.router)
app.include_router(groups.router)


@app.get("/redis-test")
async def redis_test(redis=Depends(get_redis)):
    await redis.set("greet", "Hello from redis!")
    value = await redis.get("greet")
    return {"stored_value": value.decode()}


@app.get("/")
def root():
    return {"message": "Chat app backend is running"}
