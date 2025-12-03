from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_image_upload(async_client):
    path = Path("tests") / "dummy.png"
    path.write_bytes(b"fakeimage")

    files = {"file": ("dummy.png", path.open("rb"), "image/png")}
    signup_payload = {"username": "john", "email": "john@example.com", "password": "password"}

    await async_client.post("/auth/signup", json=signup_payload)

    login_res = await async_client.post("/auth/login", data={"username": "john", "password": "password"})

    tokens = login_res.json()
    access = tokens["access_token"]

    headers = {"Authorization": f"Bearer {access}"}

    res = await async_client.post("/upload/image", files=files, headers=headers)
    assert res.status_code == 200

    data = res.json()

    assert "filename" in data
    assert "url" in data

    path.unlink()
