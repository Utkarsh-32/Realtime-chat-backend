import pytest


@pytest.mark.asyncio
async def test_health(async_client):
    res = await async_client.get("/")
    assert res.status_code == 200
