"""Accounts and sessions: passwords, login rules, guest data, transfer on login, hard limits."""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

from server import accounts, sessions, turtle
from server.accounts import AccountError, AccountStore
from server.sessions import Sessions

TAB_A = "00000000-0000-4000-8000-00000000000a"
TAB_B = "00000000-0000-4000-8000-00000000000b"
PASSWORD = "correct horse"


class Limits:
    """Patch module constants for one test (fast hashing, small limits)."""

    def __init__(self, test, **values):
        for name, value in values.items():
            module = accounts if hasattr(accounts, name) else sessions
            old = getattr(module, name)
            setattr(module, name, value)
            test.addCleanup(setattr, module, name, old)


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        turtle.install_test_handler()
        Limits(self, ITERATIONS=1000, FAILED_LOGIN_DELAY=0)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.folder = Path(self.dir.name) / "accounts"
        self.playing = set()
        self.sessions = Sessions(AccountStore(self.folder), is_playing=lambda c: c in self.playing)

    def turtles(self, text):
        """Context: the block must turtle with a reason containing `text`."""
        test = self

        class Check:
            def __enter__(self):
                self.before = len(turtle.triggered)

            def __exit__(self, kind, error, tb):
                if kind is None:
                    test.fail("expected a turtle")
                test.assertIs(kind, turtle.Turtled)
                test.assertIn(text.lower(), turtle.triggered[-1].lower())
                return True

        return Check()


class PasswordTests(unittest.TestCase):
    def test_hash_and_check(self):
        record = accounts.hash_password("secret pass", iterations=1000)
        self.assertTrue(accounts.check_password("secret pass", record))
        self.assertFalse(accounts.check_password("secret pasS", record))
        self.assertNotIn("secret", json.dumps(record))
        self.assertNotEqual(record["salt"], accounts.hash_password("secret pass", iterations=1000)["salt"])

    def test_bad_record(self):
        self.assertFalse(accounts.check_password("x", {}))
        self.assertFalse(accounts.check_password("x", {"salt": "zz", "hash": "00", "iterations": 1}))


class FolderTests(unittest.TestCase):
    def test_accounts_dir(self):
        from unittest import mock
        with mock.patch.dict("os.environ", {"STATE_DIRECTORY": "/state"}, clear=False):
            os.environ.pop("ACCOUNTS_DIRECTORY", None)
            self.assertEqual(accounts.accounts_dir(), Path("/state/accounts"))
            os.environ["ACCOUNTS_DIRECTORY"] = "/home/x/Dev/Accounts"
            self.assertEqual(accounts.accounts_dir(), Path("/home/x/Dev/Accounts"))


class LoginTests(Base):
    async def test_register_login_logout(self):
        s = self.sessions
        self.assertIsNone(s.account_name(TAB_A))
        await s.register(TAB_A, "Alice", PASSWORD)
        self.assertEqual(s.account_name(TAB_A), "Alice")
        s.logout(TAB_A)
        self.assertIsNone(s.account_name(TAB_A))
        await s.login(TAB_A, "alice", PASSWORD)  # names are case-insensitive
        self.assertEqual(s.account_name(TAB_A), "Alice")
        # Another tab may use the same account.
        await s.login(TAB_B, "ALICE", PASSWORD)
        self.assertEqual(s.account_name(TAB_B), "Alice")

    async def test_rejections(self):
        s = self.sessions
        for name, password, text in [("ab", PASSWORD, "3-20"), ("bad name", PASSWORD, "3-20"),
                                     ("x" * 21, PASSWORD, "3-20"), (None, PASSWORD, "3-20"),
                                     ("Alice", "x" * 129, "at most 128"), ("Alice", 12345678, "at most 128")]:
            with self.assertRaises(AccountError) as caught:
                await s.register(TAB_A, name, password)
            self.assertIn(text, str(caught.exception))
        await s.register(TAB_A, "Alice", PASSWORD)
        with self.assertRaisesRegex(AccountError, "taken"):
            await s.register(TAB_B, "aLiCe", PASSWORD)
        for name, password in [("Alice", "wrong password"), ("Nobody", PASSWORD), ("Alice", None), (5, PASSWORD)]:
            with self.assertRaisesRegex(AccountError, "Wrong name or password"):
                await s.login(TAB_B, name, password)
        self.assertIsNone(s.account_name(TAB_B))

    async def test_short_and_empty_passwords_are_allowed(self):
        await self.sessions.register(TAB_A, "Alice", "a")
        await self.sessions.register(TAB_B, "Bob", "")
        self.sessions.logout(TAB_B)
        await self.sessions.login(TAB_B, "bob", "")
        self.assertEqual(self.sessions.account_name(TAB_B), "Bob")
        with self.assertRaisesRegex(AccountError, "Wrong name or password"):
            await self.sessions.login(TAB_B, "alice", "")

    async def test_display_name_saved_to_account(self):
        s = self.sessions
        s.set_display_name(TAB_A, "Guest Name")  # guests: stays in the browser only
        self.assertIsNone(s.display_name(TAB_A))
        await s.register(TAB_A, "Alice", PASSWORD)
        self.assertIsNone(s.display_name(TAB_A))
        s.set_display_name(TAB_A, "  " + "x" * 40)  # cleaned and cut like lobby names
        self.assertEqual(s.display_name(TAB_A), "x" * accounts.MAX_DISPLAY_NAME)
        s.set_display_name(TAB_A, "   ")  # empty: ignored
        s.set_display_name(TAB_A, 42)
        self.assertEqual(s.display_name(TAB_A), "x" * accounts.MAX_DISPLAY_NAME)
        s.set_display_name(TAB_A, "Al")
        again = Sessions(AccountStore(self.folder))
        await again.login(TAB_B, "alice", PASSWORD)
        self.assertEqual(again.display_name(TAB_B), "Al")  # persisted
        s.logout(TAB_A)
        self.assertIsNone(s.display_name(TAB_A))

    def test_display_name_counts_as_a_save(self):
        Limits(self, MAX_SAVES_PER_SESSION=2)
        self.sessions.bind(TAB_A, "Alice")
        self.sessions.set_display_name(TAB_A, "a")
        self.sessions.set_display_name(TAB_A, "a")  # unchanged: not a save
        self.sessions.set_display_name(TAB_A, "b")
        with self.turtles("one session"):
            self.sessions.set_display_name(TAB_A, "c")

    def test_bad_display_name_in_file_is_dropped(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "bob.json").write_text(json.dumps({"name": "Bob", "games": {}, "displayName": ["x"]}))
        with self.assertLogs("accounts", "ERROR"):
            store = AccountStore(self.folder)
        self.assertIsNone(store.display_name("bob"))

    async def test_no_login_or_logout_while_playing(self):
        s = self.sessions
        await s.register(TAB_B, "Bob", PASSWORD)
        self.playing.add(TAB_A)
        with self.assertRaisesRegex(AccountError, "during a game"):
            await s.login(TAB_A, "Bob", PASSWORD)
        with self.assertRaisesRegex(AccountError, "during a game"):
            await s.register(TAB_A, "Carol", PASSWORD)
        self.assertIsNone(s.store.get("Carol"))
        self.playing = {TAB_B}
        with self.assertRaisesRegex(AccountError, "during a game"):
            s.logout(TAB_B)
        self.assertEqual(s.account_name(TAB_B), "Bob")

    async def test_accounts_persist(self):
        await self.sessions.register(TAB_A, "Alice", PASSWORD)
        self.sessions.save(TAB_A, "tanks", {"wins": 3})
        again = Sessions(AccountStore(self.folder))
        await again.login(TAB_B, "alice", PASSWORD)
        self.assertEqual(again.load(TAB_B, "tanks"), {"wins": 3})
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["alice.json"])

    async def test_unreadable_file_is_skipped_but_name_stays_taken(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "broken.json").write_text("{not json")
        with self.assertLogs("accounts", "ERROR"):
            store = AccountStore(self.folder)
        self.assertIsNone(store.get("broken"))
        self.assertEqual(store.count(), 1)
        with self.assertRaisesRegex(AccountError, "taken"):
            store.create("Broken", {})


class LoginTokenTests(Base):
    def make(self, name="Alice"):
        record = self.sessions.store.create(name, accounts.hash_password("", iterations=1))
        return record, self.sessions.store.login_token(name)

    def test_token_survives_a_restart(self):
        _, token = self.make()
        key_file = self.folder / accounts.LOGIN_KEY_FILE
        self.assertEqual(key_file.stat().st_mode & 0o777, 0o600)
        restarted = AccountStore(self.folder)  # same folder, new process: same key
        self.assertEqual(restarted.check_login_token(token), "alice")
        self.assertEqual(restarted.count(), 1)  # the key file isn't read as an account

    def test_bad_tokens(self):
        _, token = self.make()
        body, signature = token.split(".")
        for bad in [None, 5, "", "x" * 600, "a.b.c", f"{body}.{'0' * 64}", f"{body[:-2]}xx.{signature}"]:
            self.assertIsNone(self.sessions.store.check_login_token(bad), bad)
        self.assertIsNone(AccountStore(None).check_login_token(token))  # another key

    def test_expired_token(self):
        Limits(self, LOGIN_TOKEN_DAYS=-1)
        _, token = self.make()
        self.assertIsNone(self.sessions.store.check_login_token(token))

    def test_deleted_and_recreated_account_rejects_old_token(self):
        record, token = self.make()
        record["created"] -= 10  # stands in for a new account with the same name
        self.assertIsNone(self.sessions.store.check_login_token(token))

    async def test_resume(self):
        _, token = self.make()
        self.assertTrue(self.sessions.resume(TAB_A, token))
        self.assertEqual(self.sessions.account_name(TAB_A), "Alice")

    async def test_resume_moves_guest_data_like_a_login(self):
        _, token = self.make()
        self.sessions.save(TAB_A, "demo", {"wins": 2})
        self.sessions.resume(TAB_A, token)
        self.assertEqual(self.sessions.load(TAB_A, "demo"), {"wins": 2})
        self.assertTrue(self.sessions.store.has("alice", "demo"))

    async def test_resume_never_switches_or_interrupts(self):
        _, token = self.make()
        self.sessions.bind(TAB_A, "Bob")
        self.sessions.resume(TAB_A, token)
        self.assertEqual(self.sessions.account_name(TAB_A), "Bob")  # already logged in: ignored
        self.sessions.logout(TAB_A)
        self.playing.add(TAB_A)
        self.assertFalse(self.sessions.resume(TAB_A, token))
        self.assertIsNone(self.sessions.account_name(TAB_A))


class DataTests(Base):
    def test_guest_data_in_memory(self):
        s = self.sessions
        self.assertIsNone(s.load(TAB_A, "tanks"))
        s.save(TAB_A, "tanks", {"wins": 1})
        s.save(TAB_A, "arena", [1, 2])
        self.assertEqual(s.load(TAB_A, "tanks"), {"wins": 1})
        self.assertIsNone(s.load(TAB_B, "tanks"))
        self.assertFalse(self.folder.exists() and any(self.folder.iterdir()))

    def test_load_returns_a_copy(self):
        s = self.sessions
        s.save(TAB_A, "g", {"list": [1]})
        s.load(TAB_A, "g")["list"].append(2)
        self.assertEqual(s.load(TAB_A, "g"), {"list": [1]})

    def test_non_json_value_is_refused(self):
        with self.assertRaises(ValueError):
            self.sessions.save(TAB_A, "g", {"x": {1, 2}})
        with self.assertRaises(ValueError):
            self.sessions.save(TAB_A, "g", float("nan"))
        self.assertIsNone(self.sessions.load(TAB_A, "g"))

    async def test_login_moves_guest_data_unless_account_has_its_own(self):
        s = self.sessions
        await s.register(TAB_B, "Alice", PASSWORD)
        s.save(TAB_B, "tanks", {"account": True})
        s.logout(TAB_B)
        self.assertIsNone(s.load(TAB_B, "tanks"))  # logged out: a fresh guest

        s.save(TAB_A, "tanks", {"guest": True})
        s.save(TAB_A, "arena", {"guest": True})
        await s.login(TAB_A, "Alice", PASSWORD)
        self.assertEqual(s.load(TAB_A, "tanks"), {"account": True})  # account data wins
        self.assertEqual(s.load(TAB_A, "arena"), {"guest": True})  # moved over
        s.logout(TAB_A)
        self.assertIsNone(s.load(TAB_A, "tanks"))  # the guest copy is gone
        self.assertIsNone(s.load(TAB_A, "arena"))

    async def test_register_keeps_guest_data(self):
        s = self.sessions
        s.save(TAB_A, "tanks", {"wins": 2})
        await s.register(TAB_A, "Alice", PASSWORD)
        self.assertEqual(json.loads((self.folder / "alice.json").read_text())["games"], {"tanks": {"wins": 2}})

    async def test_guest_data_too_big_for_account_is_dropped(self):
        Limits(self, MAX_DATA_BYTES=300)
        s = self.sessions
        await s.register(TAB_B, "Alice", PASSWORD)
        s.save(TAB_B, "a", "x" * 150)
        s.logout(TAB_B)
        s.save(TAB_A, "b", "y" * 200)  # fits a guest, not next to the account's data
        await s.login(TAB_A, "Alice", PASSWORD)
        self.assertIsNone(s.load(TAB_A, "b"))
        self.assertEqual(s.load(TAB_A, "a"), "x" * 150)

    async def test_session_ends_after_grace(self):
        Limits(self, SESSION_GRACE=0.01)
        s = self.sessions
        await s.register(TAB_A, "Alice", PASSWORD)
        s.logout(TAB_A)
        s.attach(TAB_A)
        s.attach(TAB_A)  # e.g. a room seat and the account socket
        s.save(TAB_A, "g", 1)
        s.detach(TAB_A)
        await asyncio.sleep(0.05)
        self.assertEqual(s.load(TAB_A, "g"), 1)  # still connected once
        await s.login(TAB_A, "Alice", PASSWORD)
        s.detach(TAB_A)
        await asyncio.sleep(0.05)
        self.assertNotIn(TAB_A, s.sessions)
        self.assertIsNone(s.account_name(TAB_A))

    async def test_reconnect_within_grace_keeps_session(self):
        Limits(self, SESSION_GRACE=0.05)
        s = self.sessions
        s.attach(TAB_A)
        s.save(TAB_A, "g", 1)
        s.detach(TAB_A)
        s.attach(TAB_A)  # e.g. moving from the home page to a game page
        await asyncio.sleep(0.1)
        self.assertEqual(s.load(TAB_A, "g"), 1)


class HardLimitTests(Base):
    async def test_account_limit_turtles(self):
        Limits(self, MAX_ACCOUNTS=2)
        await self.sessions.register(TAB_A, "Alice", PASSWORD)
        await self.sessions.register(TAB_A, "Bob", PASSWORD)
        with self.turtles("account limit"):
            await self.sessions.register(TAB_B, "Carol", PASSWORD)
        self.assertIsNone(self.sessions.store.get("Carol"))

    def test_too_many_account_files_turtles(self):
        Limits(self, MAX_ACCOUNTS=1)
        store = AccountStore(self.folder)
        store.create("Alice", {})
        (self.folder / "bob.json").write_text(json.dumps({"name": "Bob", "games": {}}))
        with self.turtles("account files"):
            AccountStore(self.folder)

    def test_oversized_account_file_turtles(self):
        Limits(self, MAX_DATA_BYTES=100)
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "bob.json").write_text(json.dumps({"name": "Bob", "games": {"g": "x" * 200}}))
        with self.turtles("MAX_DATA_BYTES"):
            AccountStore(self.folder)

    def test_oversized_guest_save_turtles(self):
        Limits(self, MAX_DATA_BYTES=100)
        self.sessions.save(TAB_A, "a", "x" * 50)
        with self.turtles("MAX_DATA_BYTES"):
            self.sessions.save(TAB_A, "b", "x" * 50)
        self.assertIsNone(self.sessions.load(TAB_A, "b"))

    async def test_oversized_account_save_turtles(self):
        Limits(self, MAX_DATA_BYTES=100)
        await self.sessions.register(TAB_A, "Alice", PASSWORD)
        with self.turtles("MAX_DATA_BYTES"):
            self.sessions.save(TAB_A, "a", "x" * 101)
        self.assertIsNone(self.sessions.load(TAB_A, "a"))
        self.assertEqual(json.loads((self.folder / "alice.json").read_text())["games"], {})

    def test_save_rate_per_session_turtles(self):
        Limits(self, MAX_SAVES_PER_SESSION=3)
        for i in range(3):
            self.sessions.save(TAB_A, "g", i)
        self.sessions.save(TAB_B, "g", 0)  # another tab has its own count
        with self.turtles("one session"):
            self.sessions.save(TAB_A, "g", 3)

    def test_save_rate_site_wide_turtles(self):
        Limits(self, MAX_SAVES_TOTAL=4)
        tabs = [f"00000000-0000-4000-8000-{i:012d}" for i in range(5)]
        for tab in tabs[:4]:
            self.sessions.save(tab, "g", 1)
        with self.turtles("site-wide"):
            self.sessions.save(tabs[4], "g", 1)

    def test_old_saves_leave_the_window(self):
        Limits(self, MAX_SAVES_PER_SESSION=2, SAVE_WINDOW=0.05)
        import time
        self.sessions.save(TAB_A, "g", 1)
        self.sessions.save(TAB_A, "g", 2)
        time.sleep(0.08)
        self.sessions.save(TAB_A, "g", 3)  # the first two are older than the window
        self.assertEqual(self.sessions.load(TAB_A, "g"), 3)
