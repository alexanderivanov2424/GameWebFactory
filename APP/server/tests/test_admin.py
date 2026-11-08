"""Admin view (server/admin.py): the password gate and each read-only listing."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from server import admin
from server.accounts import AccountStore
from server.admin import Admin, AdminError
from server.rooms import BaseGame, Player, Room, Rooms
from server.sessions import Sessions

A = "aaaaaaaa-1111-4111-8111-111111111111"
B = "bbbbbbbb-2222-4222-8222-222222222222"


class FakeSocket:
    def __init__(self, client, incoming):
        self.query = {"client": client}
        self.incoming = [json.dumps(m) for m in incoming]
        self.sent = []
        self.closed = None

    async def recv(self):
        return self.incoming.pop(0) if self.incoming else None

    async def send(self, text):
        self.sent.append(json.loads(text))

    async def close(self, code=1000):
        self.closed = code


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = AccountStore(None)
        self.sessions = Sessions(self.store)
        self.rooms = Rooms({"demo": BaseGame}, self.sessions)
        self.folder = Path(self.tmp.name)
        self.admin = Admin(self.store, self.sessions, self.rooms, self.folder)
        self.sessions.attach(A)
        self.sessions.attach(B)
        self.sessions.bind(A, "Alice")
        self.store.save("alice", "demo", {"wins": 3})
        self.sessions.save(B, "demo", {"wins": 1})
        room = self.rooms.rooms[("demo", "main")] = Room("demo", "main", BaseGame, self.sessions)
        room.players[B] = Player(B)

    def test_accounts_never_include_passwords(self):
        listing = self.admin.get({"what": "accounts"})
        self.assertEqual([a["name"] for a in listing], ["Alice"])
        self.assertEqual(listing[0]["sessions"], 1)
        self.assertEqual(listing[0]["games"], ["demo"])
        record = self.admin.get({"what": "account", "name": "ALICE"})
        self.assertEqual(record["games"], {"demo": {"wins": 3}})
        self.assertNotIn("password", record)
        self.assertNotIn("password", json.dumps(listing))
        with self.assertRaises(AdminError):
            self.admin.get({"what": "account", "name": "nobody"})

    def test_sessions_use_short_ids_only(self):
        listing = self.admin.get({"what": "sessions"})
        text = json.dumps(listing)
        self.assertNotIn(A, text)
        self.assertNotIn(B, text)
        by_id = {s["id"]: s for s in listing}
        self.assertEqual(by_id["aaaaaaaa"]["account"], "Alice")
        self.assertEqual(by_id["bbbbbbbb"]["rooms"], ["demo/main"])
        self.assertEqual(by_id["bbbbbbbb"]["guestGames"], ["demo"])
        detail = self.admin.get({"what": "session", "id": "bbbbbbbb"})
        self.assertEqual(detail["guestData"], {"demo": {"wins": 1}})
        with self.assertRaises(AdminError):
            self.admin.get({"what": "session", "id": A})

    def test_rooms_without_a_lobby_list_raw_seats(self):
        [room] = self.admin.get({"what": "rooms"})
        self.assertEqual((room["game"], room["room"]), ("demo", "main"))
        self.assertEqual(room["members"], [{"session": "bbbbbbbb", "online": False, "account": None}])

    def test_feedback_grouped_and_readable(self):
        (self.folder / "site").mkdir()
        (self.folder / "site" / f"{A}_Alice.txt").write_text("--- 2026-01-01 10:00:00\nhi\n\n--- x\nmore\n\n")
        (self.folder / "site" / "notes.md").write_text("ignored")
        groups = self.admin.get({"what": "feedback"})
        [entry] = groups["site"]
        self.assertEqual((entry["name"], entry["client"], entry["entries"]), ("Alice", "aaaaaaaa", 2))
        text = self.admin.get({"what": "feedbackFile", "game": "site", "file": f"{A}_Alice.txt"})
        self.assertIn("more", text)

    def test_feedback_file_rejects_paths(self):
        for game, file in [("..", f"{A}_x.txt"), ("site", "../../etc/passwd"), ("site", f"{B}_missing.txt")]:
            with self.assertRaises(AdminError):
                self.admin.get({"what": "feedbackFile", "game": game, "file": file})

    def run_socket(self, messages, client=A):
        ws = FakeSocket(client, messages)
        old_delay = admin.WRONG_PASSWORD_DELAY
        admin.WRONG_PASSWORD_DELAY = 0
        try:
            asyncio.run(self.admin.handle(ws))
        finally:
            admin.WRONG_PASSWORD_DELAY = old_delay
        return ws

    def test_socket_needs_the_password(self):
        ws = self.run_socket([
            {"type": "get", "what": "accounts"},
            {"type": "auth", "password": "nope"},
            {"type": "get", "what": "accounts"},
            {"type": "auth", "password": admin.ADMIN_PASSWORD},
            {"type": "get", "what": "accounts"},
        ])
        kinds = [(m["type"], m.get("ok")) for m in ws.sent]
        self.assertEqual(kinds, [("error", None), ("auth", False), ("error", None), ("auth", True), ("data", None)])
        self.assertEqual(ws.sent[0]["what"], "accounts")
        self.assertEqual(ws.sent[-1]["data"][0]["name"], "Alice")

    def test_socket_rejects_bad_client_id(self):
        ws = self.run_socket([], client="nope")
        self.assertEqual(ws.closed, admin.CLOSE_INVALID)


if __name__ == "__main__":
    unittest.main()
