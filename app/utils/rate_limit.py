
async def check_rate_limit(redis, key: str, limit: int, window_seconds: int) -> bool:
    count = await redis.incr(key)
    
    if count == 1:
        await redis.expire(key, window_seconds)
    
    return count <= limit