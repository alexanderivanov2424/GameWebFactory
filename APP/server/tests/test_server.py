"""Site server: WebSocket protocol over a real local socket, game rooms (reconnects), game loading."""

import asyncio
import base64
import hashlib
import json
import os
import struct
import unittest

from server import rooms, websocket
from server.main import load_games
from server.rooms import BaseGame, Rooms

CLIENT_A = "00000000-0000-4000-8000-00000000000a"


class Client:
    """Minimal browser-side WebSocket client: handshake, masked text frames, reads server frames."""

    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer

    @classmethod
    async def connect(cls, port, path):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        key = base64.b64encode(os.urandom(16)).decode()
        writer.write(
            f"GET {path} HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        head = (await reader.readuntil(b"\r\n\r\n")).decode()
        client = cls(reader, writer)
        client.status = head.split(" ", 2)[1]
        expected = base64.b64encode(hashlib.sha1((key + websocket.GUID).encode()).digest()).decode()
        client.accepted = f"Sec-WebSocket-Accept: {expected}" in head
        return client

    def send(self, text, fin=True, opcode=websocket.OP_TEXT):
        payload = text.encode()
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.writer.write(struct.pack("!BB", (0x80 if fin else 0) | opcode, 0x80 | len(payload)) + mask + masked)

    async def recv(self):
        """Next (opcode, payload) from the server, skipping pings."""
        while True:
            b1, b2 = await asyncio.wait_for(self.reader.readexactly(2), 2)
            length = b2 & 0x7F
            if length == 126:
                (length,) = struct.unpack("!H", await self.reader.readexactly(2))
            payload = await self.reader.readexactly(length)
            if b1 & 0x0F != websocket.OP_PING:
                return b1 & 0x0F, payload

    async def recv_json(self):
        opcode, payload = await self.recv()
        assert opcode == websocket.OP_TEXT, opcode
        return json.loads(payload)


async def echo(ws):
    while (text := await ws.recv()) is not None:
        await ws.send(text.upper())


class Recorder(BaseGame):
    """Records room callbacks and echoes messages to their sender."""

    events = []

    async def on_connect(self, player):
        self.events.append("connect")
        await player.send({"hello": True})

    async def on_reconnect(self, player):
        self.events.append("reconnect")
        await player.send({"hello": "again"})

    async def on_message(self, player, data):
        await player.send({"echo": data})

    async def on_connection_lost(self, player):
        self.events.append("lost")

    async def on_disconnect(self, player):
        self.events.append("gone")


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        Recorder.events = []
        self.rooms = Rooms({"rec": Recorder})

        def route(path):
            if path == "/echo":
                return echo
            if path == "/ws/game/rec":
                return lambda ws: self.rooms.handle(ws, game_id="rec")
            return None

        self.server = await websocket.serve(route, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def test_handshake_and_text(self):
        client = await Client.connect(self.port, "/echo")
        self.assertEqual(client.status, "101")
        self.assertTrue(client.accepted)
        client.send("hello")
        self.assertEqual(await client.recv(), (websocket.OP_TEXT, b"HELLO"))

    async def test_fragmented_message(self):
        client = await Client.connect(self.port, "/echo")
        client.send("ab", fin=False)
        client.send("cd", fin=True, opcode=websocket.OP_CONT)
        self.assertEqual(await client.recv(), (websocket.OP_TEXT, b"ABCD"))

    async def test_unknown_path_is_404(self):
        client = await Client.connect(self.port, "/nope")
        self.assertEqual(client.status, "404")

    async def test_invalid_client_id_is_rejected(self):
        client = await Client.connect(self.port, "/ws/game/rec?room=main&client=not-a-uuid")
        opcode, payload = await client.recv()
        self.assertEqual(opcode, websocket.OP_CLOSE)
        self.assertEqual(struct.unpack("!H", payload)[0], rooms.CLOSE_INVALID)

    async def test_reconnect_within_grace_keeps_player(self):
        path = f"/ws/game/rec?room=main&client={CLIENT_A}"
        first = await Client.connect(self.port, path)
        self.assertEqual(await first.recv_json(), {"hello": True})
        first.send(json.dumps({"n": 1}))
        self.assertEqual(await first.recv_json(), {"echo": {"n": 1}})

        # Same client id again (a duplicated tab): the old connection is replaced.
        second = await Client.connect(self.port, path)
        self.assertEqual(await second.recv_json(), {"hello": "again"})
        opcode, payload = await first.recv()
        self.assertEqual((opcode, struct.unpack("!H", payload)[0]), (websocket.OP_CLOSE, rooms.CLOSE_REPLACED))
        self.assertEqual(Recorder.events, ["connect", "reconnect"])

    async def test_player_removed_after_grace(self):
        old = rooms.RECONNECT_GRACE
        rooms.RECONNECT_GRACE = 0.05
        try:
            client = await Client.connect(self.port, f"/ws/game/rec?room=r1&client={CLIENT_A}")
            await client.recv_json()
            client.writer.close()
            for _ in range(50):
                await asyncio.sleep(0.02)
                if "gone" in Recorder.events:
                    break
            self.assertEqual(Recorder.events, ["connect", "lost", "gone"])
            self.assertNotIn(("rec", "r1"), self.rooms.rooms)
        finally:
            rooms.RECONNECT_GRACE = old


class LoadGamesTests(unittest.TestCase):
    def test_every_game_folder_loads(self):
        from server.main import GAMES_DIR

        folders = {p.parent.name for p in GAMES_DIR.glob("*/server.py")}
        with self.assertNoLogs("main", level="ERROR"):
            games = load_games()
        self.assertEqual(set(games), folders)


if __name__ == "__main__":
    unittest.main()
