"""Turtle: the site's emergency shutdown. Any safety check that sees something that shouldn't
happen (a hard limit broken, possible abuse) calls turtle(reason), and the whole site goes down
and stays down until the owner looks at it.

    from server.turtle import turtle      # games: `from gamekit import turtle`
    turtle("Account limit reached")       # never returns

What happens:
1. The reason is logged (CRITICAL) and written to the marker file TURTLE in the state folder.
2. The process exits at once with EXIT_CODE (os._exit: no cleanup code runs), which closes the
   game server's port and every connection.
3. On the host, systemd sees the marker or the exit code (units written by deploy.sh) and stops
   and disables nginx and the game server, so port 8080 closes too and a reboot stays down.
4. While the marker exists the server refuses to start (check_startup) and deploy.sh refuses to
   deploy. `./deploy.sh --unturtle` shows the reason, removes the marker and deploys again.

State folder (state_dir()): $STATE_DIRECTORY, which systemd sets from StateDirectory=
(/var/lib/app-server on the host), else APP/.data/ when the server is started by hand.
Accounts live there too (server/accounts.py).

Tests: install_test_handler() (tools/run_tests.py and gamekit.sim.Sim call it) makes turtle()
record the reason in `triggered` and raise Turtled instead of exiting. Turtled is a
BaseException, so a game's `except Exception` can't swallow it.
"""

import logging
import os
import sys
import time
from pathlib import Path

log = logging.getLogger("turtle")

EXIT_CODE = 77  # deploy.sh's unit: RestartPreventExitStatus=77, so systemd doesn't restart it
MARKER = "TURTLE"
APP_DIR = Path(__file__).resolve().parent.parent

triggered = []  # reasons, in test mode
_test_mode = False


class Turtled(BaseException):
    """Raised by turtle() in test mode instead of exiting."""


def state_dir():
    """Folder for data that outlives deploys: the turtle marker and accounts."""
    return Path(os.environ.get("STATE_DIRECTORY") or APP_DIR / ".data")


def marker_path():
    return state_dir() / MARKER


def turtle(reason):
    """Shut the whole site down now because of `reason` (a short text). Never returns."""
    reason = str(reason)[:500]
    if _test_mode:
        triggered.append(reason)
        raise Turtled(reason)
    try:
        log.critical("TURTLE: %s. Shutting the site down.", reason)
        for handler in logging.getLogger().handlers:
            handler.flush()
    except Exception:  # noqa: BLE001 - nothing may stop the shutdown
        pass
    try:
        path = marker_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {reason}\n", encoding="utf-8")
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 - the exit code still tells systemd
        pass
    try:
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass
    os._exit(EXIT_CODE)


def check_startup():
    """Exit with EXIT_CODE if the site was turtled and nobody cleared it yet."""
    path = marker_path()
    if path.exists():
        try:
            reason = path.read_text(encoding="utf-8", errors="replace").strip()[:500]
        except OSError:
            reason = "(unreadable)"
        log.critical("Turtled: %s. Not starting. Clear it with ./deploy.sh --unturtle.", reason)
        sys.exit(EXIT_CODE)


def install_test_handler():
    """Tests only: turtle() records the reason and raises Turtled instead of exiting."""
    global _test_mode
    _test_mode = True
