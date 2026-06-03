import httpx


async def verify_cap_token(
    verify_url: str,
    secret_key: str,
    token: str,
) -> bool:
    if not verify_url or not secret_key or not token:
        return False

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            verify_url,
            json={
                "secret": secret_key,
                "response": token,
            },
        )

    if response.status_code >= 400:
        return False

    data = response.json()
    return bool(data.get("success"))