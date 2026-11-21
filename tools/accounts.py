"""Manage player accounts on the host: find, select, show and delete them. SiteManagement/accounts.sh
(kept outside the Dev folder, next to startup.sh and shutdown.sh) runs this.

    ./accounts.sh                     interactive prompt (type `help`)
    ./accounts.sh list [TEXT]         list accounts, or only those whose name/display name has TEXT
    ./accounts.sh show NAME...        details of accounts
    ./accounts.sh delete NAME...      delete accounts (asks first; only while the site is stopped)
    ./accounts.sh --dir PATH ...      use another accounts folder (e.g. APP/.data/accounts for a
                                      hand-started server); the site isn't checked then

The default folder is ExternalWrite/Accounts/ in the Dev folder, where the running site keeps them
(the startup script). Its files belong to the gwf user; an ACL (set once by hand) gives the Dev
folder's owner read/write, so run this as that user.

Interactive commands: list/find [TEXT], select ITEMS, unselect ITEMS, clear, selected,
show [ITEMS], delete [ITEMS], help, quit. ITEMS are names or numbers from the last list
(`3`, `2-5`, `all` = every account in the last list); show/delete with no ITEMS use the selection.

Accounts are the files <folder>/<lowercase name>.json written by APP/server/accounts.py (see its
header for the format). Files that can't be read are listed as "(unreadable)" and can be deleted.

Deleting: the running server keeps every account in memory and rewrites an account's file when
it saves, so deleting a file under a running server does nothing (or gets undone). With the
default folder, delete therefore refuses while the site answers on port SITE_PORT: stop it
(shutdown.sh), delete, then start it again (startup.sh). This tool can't stop the site itself: the
scripts that do live outside the Dev folder. Deleted files are gone for good: there is no backup.

Nothing here imports the server: loading accounts through AccountStore could turtle the site.
"""

import json
import os
import socket
import sys
import time
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "ExternalWrite" / "Accounts"
SITE_PORT = 8080  # the site's published port on the host

HELP = """Commands:
  list [TEXT]       list accounts (only those whose name or display name contains TEXT)
  find TEXT         same as list TEXT
  select ITEMS      add accounts to the selection
  unselect ITEMS    remove accounts from the selection
  clear             empty the selection
  selected          list the selected accounts
  show [ITEMS]      details of ITEMS, or of the selection
  delete [ITEMS]    delete ITEMS, or the selection (asks first)
  help              this text
  quit              leave (also: exit, q, Ctrl-D)
ITEMS: account names or numbers from the last list, e.g. `alice 3 5-7`, or `all` for the whole
last list."""


class Site:
    """The running site (the gwf pod), seen from the host: something answers on SITE_PORT."""

    def __init__(self, port=SITE_PORT):
        self.port = port

    def is_running(self):
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                return True
        except OSError:
            return False


class Account:
    def __init__(self, path):
        self.path = path
        self.key = path.stem
        self.error = None
        self.record = {}
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or not isinstance(record.get("games"), dict):
                raise ValueError("not an account record")
            self.record = record
        except (OSError, ValueError) as error:
            self.error = str(error)

    @property
    def name(self):
        name = self.record.get("name")
        return name if isinstance(name, str) else self.key

    @property
    def display(self):
        text = self.record.get("displayName")
        return text if isinstance(text, str) else ""

    @property
    def created(self):
        stamp = self.record.get("created")
        if isinstance(stamp, (int, float)):
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))
        return "?"

    @property
    def games(self):
        return self.record.get("games", {})

    def data_bytes(self):
        return len(json.dumps(self.games, separators=(",", ":")).encode())

    def matches(self, text):
        text = text.lower()
        return text in self.name.lower() or text in self.display.lower()


def size_text(count):
    return f"{count} B" if count < 1024 else f"{count / 1024:.1f} KB"


class Manager:
    def __init__(self, folder, site=None, out=print, ask=input):
        self.folder = Path(folder)
        self.site = site  # Site, or None when the folder isn't the running site's
        self.out = out
        self.ask = ask
        self.last = []  # keys of the last list, in order (numbers refer to it)
        self.selected = []  # keys, in selection order

    # --- reading ---------------------------------------------------------------

    def accounts(self):
        """Every account file, by lowercase name."""
        if not self.folder.is_dir():
            return {}
        return {p.stem: Account(p) for p in sorted(self.folder.glob("*.json"))}

    def resolve(self, items, accounts):
        """Keys for ITEMS (names, numbers, ranges, `all`); unknown items are reported and skipped."""
        keys = []
        for item in items:
            found = self._resolve_one(item, accounts)
            if found is None:
                self.out(f"  No account '{item}'.")
            keys += [k for k in found or [] if k not in keys]
        return keys

    def _resolve_one(self, item, accounts):
        if item.lower() == "all":
            return [k for k in self.last if k in accounts]
        numbers = item.split("-", 1)
        if all(n.isdigit() for n in numbers):
            low, high = int(numbers[0]), int(numbers[-1])
            if 1 <= low <= high <= len(self.last):
                return [k for k in self.last[low - 1:high] if k in accounts]
        key = item.lower()
        return [key] if key in accounts else None

    # --- commands --------------------------------------------------------------

    def cmd_list(self, args):
        accounts = self.accounts()
        text = " ".join(args)
        shown = [a for a in accounts.values() if not text or a.matches(text)]
        self.last = [a.key for a in shown]
        where = f" matching '{text}'" if text else ""
        self.out(f"{len(shown)} of {len(accounts)} accounts{where} ({self.folder})")
        if shown:
            self._table(shown)

    def _table(self, shown):
        self.out(f"  {'#':>3}  {'Name':<20}  {'Display name':<24}  {'Created':<16}  Games  Data")
        for number, a in enumerate(shown, 1):
            mark = "*" if a.key in self.selected else " "
            if a.error:
                self.out(f"{mark} {number:>3}  {a.key:<20}  (unreadable: {a.error})")
                continue
            self.out(f"{mark} {number:>3}  {a.name:<20}  {a.display[:24]:<24}  {a.created:<16}  "
                     f"{len(a.games):>5}  {size_text(a.data_bytes())}")
        if any(a.key in self.selected for a in shown):
            self.out("  (* = selected)")

    def cmd_find(self, args):
        if not args:
            self.out("  Usage: find TEXT")
            return
        self.cmd_list(args)

    def cmd_select(self, args):
        if not args:
            self.out("  Usage: select ITEMS (names or numbers from the last list)")
            return
        for key in self.resolve(args, self.accounts()):
            if key not in self.selected:
                self.selected.append(key)
        self.cmd_selected([])

    def cmd_unselect(self, args):
        if not args:
            self.out("  Usage: unselect ITEMS")
            return
        accounts = {k: None for k in self.selected} | self.accounts()
        for key in self.resolve(args, accounts):
            if key in self.selected:
                self.selected.remove(key)
        self.cmd_selected([])

    def cmd_clear(self, args):
        self.selected = []
        self.out("  Selection cleared.")

    def cmd_selected(self, args):
        accounts = self.accounts()
        self.selected = [k for k in self.selected if k in accounts]  # drop deleted ones
        if not self.selected:
            self.out("  Nothing selected.")
            return
        self.out(f"  Selected ({len(self.selected)}): " + ", ".join(accounts[k].name for k in self.selected))

    def _targets(self, args, accounts):
        if args:
            return self.resolve(args, accounts)
        keys = [k for k in self.selected if k in accounts]
        if not keys:
            self.out("  Nothing selected: give names or numbers, or select some first.")
        return keys

    def cmd_show(self, args):
        accounts = self.accounts()
        for key in self._targets(args, accounts):
            a = accounts[key]
            self.out(f"  {a.name}")
            self.out(f"    File:          {a.path}")
            if a.error:
                self.out(f"    Unreadable:    {a.error}")
                continue
            self.out(f"    Display name:  {a.display or '(none)'}")
            self.out(f"    Created:       {a.created}")
            self.out(f"    Saved data:    {size_text(a.data_bytes())}")
            for game_id, value in sorted(a.games.items()):
                size = len(json.dumps(value, separators=(",", ":")).encode())
                self.out(f"      {game_id:<20}  {size_text(size)}")

    def cmd_delete(self, args):
        accounts = self.accounts()
        keys = self._targets(args, accounts)
        if not keys:
            return
        names = ", ".join(accounts[k].name for k in keys)
        if self.site is not None and self.site.is_running():
            self.out("  The site is running and keeps accounts in memory, so deleting now would be")
            self.out("  undone. Stop it (sudo ./shutdown.sh), delete, then start it (sudo ./startup.sh).")
            self.out("  Nothing deleted.")
            return
        self.out(f"  Delete {len(keys)} account(s): {names}  (this can't be undone)")
        try:
            answer = self.ask("  Type yes to delete: ")
        except EOFError:
            answer = ""
        if answer.strip().lower() != "yes":
            self.out("  Cancelled.")
            return
        for key in keys:
            accounts[key].path.unlink(missing_ok=True)
            self.out(f"  Deleted {accounts[key].name}")
            if key in self.selected:
                self.selected.remove(key)

    def cmd_help(self, args):
        self.out(HELP)

    COMMANDS = {"list": cmd_list, "ls": cmd_list, "find": cmd_find, "select": cmd_select,
                "sel": cmd_select, "unselect": cmd_unselect, "clear": cmd_clear,
                "selected": cmd_selected, "show": cmd_show, "delete": cmd_delete,
                "del": cmd_delete, "rm": cmd_delete, "help": cmd_help, "?": cmd_help}

    def run_command(self, line):
        """Run one command line; returns False to quit."""
        words = line.split()
        if not words:
            return True
        command, args = words[0].lower(), words[1:]
        if command in ("quit", "exit", "q"):
            return False
        handler = self.COMMANDS.get(command)
        if handler is None:
            self.out(f"  Unknown command '{command}'. Type help for the list.")
        else:
            handler(self, args)
        return True

    def prompt(self):
        return f"accounts ({len(self.selected)} selected)> " if self.selected else "accounts> "

    def interactive(self):
        self.out("Account manager. Type help for commands, quit to leave.")
        self.cmd_list([])
        while True:
            try:
                line = self.ask(self.prompt())
            except (EOFError, KeyboardInterrupt):
                self.out("")
                return
            if not self.run_command(line):
                return


USAGE = """Usage: accounts.sh [--dir PATH] [list [TEXT] | find TEXT | show NAME... | delete NAME...]
With no command it starts an interactive prompt."""


def main(argv):
    folder = None
    if argv[:1] == ["--dir"]:
        if len(argv) < 2:
            print(USAGE)
            return 2
        folder, argv = Path(argv[1]), argv[2:]
    if argv[:1] in (["-h"], ["--help"]):
        print(USAGE)
        print(HELP)
        return 0
    site = None if folder else Site()
    folder = folder or DEFAULT_DIR
    if not folder.is_dir():
        print(f"No accounts folder at {folder} (the startup script creates it, or wrong --dir).")
        return 1
    try:
        os.listdir(folder)
    except PermissionError:
        print(f"Can't read {folder}: run this as the Dev folder's owner (the ACL on ExternalWrite/ gives them access).")
        return 1
    manager = Manager(folder, site)
    if not argv:
        try:
            import readline  # noqa: F401 - line editing and history for input()
        except ImportError:
            pass
        manager.interactive()
        return 0
    if argv[0] not in ("list", "ls", "find", "show", "delete", "del", "rm"):
        print(USAGE)
        return 2
    manager.run_command(" ".join(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
