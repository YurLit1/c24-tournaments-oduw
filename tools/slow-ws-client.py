# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "websockets>=17.3",
#     "httpx>=0.28.1",
# ]
# ///
"""Slow WebSocket client for D5.6: connects and never reads.

The socket buffers fill up, the gateway can no longer send, its bounded buffer for this
connection overflows and the gateway should close it with 1013. Gateway memory stays flat.

Run from the project root (uv installs the two dependencies itself):

  uv run tools/slow-ws-client.py user1 user1-pass
  # then create many notifications for user1 (the client, workload/, a loop of curl)

Watch: docker compose logs -f gateway-a gateway-b
       docker stats   (memory of the gateways)

Expects the routes of the guide: POST /v1/auth/login {login, password} -> {"access_token"},
POST /v1/ws-tickets -> {"ticket"}, GET /v1/ws?ticket=. With a cookie session or other field
names change login() below. Environment: API (http://localhost:8080), ORIGIN (http://localhost:8081).
"""

import asyncio
import os
import sys

import httpx
import websockets

API = os.environ.get("API", "http://localhost:8080")
ORIGIN = os.environ.get("ORIGIN", "http://localhost:8081")


async def login(client: httpx.AsyncClient, user: str, password: str) -> dict[str, str]:
    reply = await client.post("/v1/auth/login", json={"login": user, "password": password})
    reply.raise_for_status()
    return {"Authorization": f"Bearer {reply.json()['access_token']}"}


async def main(user: str, password: str) -> None:
    async with httpx.AsyncClient(base_url=API, headers={"Origin": ORIGIN}) as client:
        headers = await login(client, user, password)
        ticket = (await client.post("/v1/ws-tickets", headers=headers)).json()["ticket"]

    ws_url = API.replace("http", "ws", 1) + f"/v1/ws?ticket={ticket}"

    async with websockets.connect(ws_url, origin=ORIGIN, max_queue=1, max_size=2**10, ping_interval=None) as ws:
        print("connected; not reading anything. Waiting for the gateway to give up...")
        try:
            await ws.wait_closed()
        finally:
            print(f"closed by the gateway: code={ws.close_code} reason={ws.close_reason!r}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: uv run tools/slow-ws-client.py <login> <password>")
    asyncio.run(main(sys.argv[1], sys.argv[2]))
