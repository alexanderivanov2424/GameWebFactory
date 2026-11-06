"""Site-wide chat: relays messages between everyone connected to /ws/chat."""

import asyncio
import json
import time
from collections import deque

from server.utils import clean_text

MAX_NAME = 32
MAX_TEXT = 500
HISTORY_SIZE = 50

clients = set()
history = deque(maxlen=HISTORY_SIZE)


async def handle(ws):
    clients.add(ws)
    try:
        await ws.send(json.dumps({"type": "history", "messages": list(history)}))
        while (raw := await ws.recv()) is not None:
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(data, dict) or data.get("type") != "chat":
                continue
            text = clean_text(data.get("text"), MAX_TEXT)
            if not text:
                continue
            message = {
                "type": "chat",
                "name": clean_text(data.get("name"), MAX_NAME) or "Anonymous",
                "text": text,
                "time": int(time.time() * 1000),
            }
            history.append(message)
            payload = json.dumps(message)
            await asyncio.gather(*(client.send(payload) for client in list(clients)))
    finally:
        clients.discard(ws)
