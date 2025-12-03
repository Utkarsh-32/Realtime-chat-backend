import pytest


@pytest.mark.asyncio
async def test_signup_and_login(async_client):
    signup_payload = {"username": "john", "email": "john@example.com", "password": "password"}

    res_signup = await async_client.post("/auth/signup", json=signup_payload)
    assert res_signup.status_code == 201

    login_payload = {"username": "john", "password": "password"}

    res_login = await async_client.post("/auth/login", data=login_payload)
    assert res_login.status_code == 200

    data = res_login.json()

    assert "access_token" in data
    assert "refresh_token" in data
