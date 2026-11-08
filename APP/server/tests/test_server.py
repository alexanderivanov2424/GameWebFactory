"""Site server: WebSocket protocol over a real local socket, game rooms (reconnects), the account
socket, game loading."""

import asyncio
import base64
import hashlib
import json
import os
import struct
import unittest

from server import accounts, rooms, sessions, turtle, websocket
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
        first = (0x80 if fin else 0) | opcode
        if len(payload) < 126:
            header = struct.pack("!BB", first, 0x80 | len(payload))
        else:
            header = struct.pack("!BBH", first, 0x80 | 126, len(payload))
        self.writer.write(header + mask + masked)

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


class AccountSocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        turtle.install_test_handler()
        for module, name, value in [(accounts, "ITERATIONS", 1000), (sessions, "FAILED_LOGIN_DELAY", 0)]:
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, value)
        self.rooms = Rooms({"rec": Recorder})
        self.sessions = self.rooms.sessions

        def route(path):
            if path == "/ws/account":
                return self.sessions.handle
            if path == "/ws/game/rec":
                return lambda ws: self.rooms.handle(ws, game_id="rec")
            return None

        self.server = await websocket.serve(route, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def status(self, client):
        """Next message, with an account status's login token checked and removed."""
        data = await client.recv_json()
        if data.get("type") == "account":
            token = data.pop("token")
            self.assertEqual(token is not None, data["user"] is not None)
            if token:
                self.assertEqual(self.sessions.store.check_login_token(token), data["user"].lower())
        return data

    async def test_register_logout_login(self):
        tab = await Client.connect(self.port, f"/ws/account?client={CLIENT_A}")
        other = await Client.connect(self.port, f"/ws/account?client={CLIENT_A}")  # same tab, another page
        self.assertEqual(await self.status(tab), {"type": "account", "user": None, "displayName": None})
        self.assertEqual(await self.status(other), {"type": "account", "user": None, "displayName": None})

        tab.send(json.dumps({"type": "register", "name": "Alice", "password": "password1"}))
        self.assertEqual(await self.status(tab), {"type": "account", "user": "Alice", "displayName": None})
        self.assertEqual(await self.status(other), {"type": "account", "user": "Alice", "displayName": None})

        tab.send(json.dumps({"type": "logout"}))
        self.assertEqual(await self.status(tab), {"type": "account", "user": None, "displayName": None})
        tab.send(json.dumps({"type": "login", "name": "alice", "password": "nope-nope"}))
        self.assertEqual(await self.status(tab), {"type": "error", "message": "Wrong name or password."})
        tab.send(json.dumps({"type": "login", "name": "alice", "password": "password1"}))
        self.assertEqual(await self.status(tab), {"type": "account", "user": "Alice", "displayName": None})
        self.assertEqual(self.sessions.account_name(CLIENT_A), "Alice")

        # The display name is saved to the account and comes back with the next login.
        tab.send(json.dumps({"type": "name", "name": "  Captain Al  "}))
        tab.send(json.dumps({"type": "logout"}))
        self.assertEqual(await self.status(tab), {"type": "account", "user": None, "displayName": None})
        tab.send(json.dumps({"type": "login", "name": "alice", "password": "password1"}))
        self.assertEqual(await self.status(tab), {"type": "account", "user": "Alice", "displayName": "Captain Al"})

    async def test_invalid_client_id_is_rejected(self):
        client = await Client.connect(self.port, "/ws/account?client=nope")
        opcode, payload = await client.recv()
        self.assertEqual((opcode, struct.unpack("!H", payload)[0]), (websocket.OP_CLOSE, sessions.CLOSE_INVALID))

    async def test_room_seat_keeps_the_session(self):
        old = sessions.SESSION_GRACE
        sessions.SESSION_GRACE = 0.02
        try:
            tab = await Client.connect(self.port, f"/ws/account?client={CLIENT_A}")
            await tab.recv_json()
            tab.send(json.dumps({"type": "register", "name": "Alice", "password": "password1"}))
            await tab.recv_json()
            seat = await Client.connect(self.port, f"/ws/game/rec?room=main&client={CLIENT_A}")
            await seat.recv_json()
            tab.writer.close()  # the account socket goes away (e.g. page change)...
            await asyncio.sleep(0.1)
            self.assertEqual(self.sessions.account_name(CLIENT_A), "Alice")  # ...the seat keeps it
        finally:
            sessions.SESSION_GRACE = old

    async def test_resume_logs_a_forgotten_session_back_in(self):
        tab = await Client.connect(self.port, f"/ws/account?client={CLIENT_A}")
        await tab.recv_json()
        tab.send(json.dumps({"type": "register", "name": "Alice", "password": "password1"}))
        token = (await tab.recv_json())["token"]
        tab.writer.close()
        await asyncio.sleep(0.05)
        self.sessions.end(CLIENT_A)  # forgotten, as after a restart or a long absence

        again = await Client.connect(self.port, f"/ws/account?client={CLIENT_A}")
        self.assertIsNone((await again.recv_json())["user"])
        again.send(json.dumps({"type": "resume", "token": token}))
        reply = await again.recv_json()
        self.assertEqual(reply["user"], "Alice")
        self.assertIsInstance(reply["token"], str)
        self.assertEqual(self.sessions.account_name(CLIENT_A), "Alice")

    async def test_bad_resume_token_stays_guest(self):
        tab = await Client.connect(self.port, f"/ws/account?client={CLIENT_A}")
        await tab.recv_json()
        tab.send(json.dumps({"type": "resume", "token": "bad.token"}))
        self.assertEqual(await tab.recv_json(), {"type": "account", "user": None, "displayName": None, "token": None})


class LoadGamesTests(unittest.TestCase):
    def test_every_game_folder_loads(self):
        from server.main import GAMES_DIR

        folders = {p.parent.name for p in GAMES_DIR.glob("*/server.py")}
        with self.assertNoLogs("main", level="ERROR"):
            games = load_games()
        self.assertEqual(set(games), folders)


if __name__ == "__main__":
    unittest.main()
