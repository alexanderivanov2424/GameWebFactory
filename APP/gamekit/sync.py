"""How a game's state reaches the clients. A game picks one with `SYNC = ...` (class attribute).

    FullState   (LobbyGame default) After every change, every member gets one "state"
                message with everything: the lobby, game_state() and their private_state().
                Simple and robust; right for turn-based games with small states.
    PatchState  Same events, fewer bytes: a full "state" (a keyframe) only on connect, on
                resync and when the lobby part changes (phase, players, names, connection,
                settings...); otherwise a "patch" with just what changed in game/private, and
                nothing when nothing changed. For turn-based games with big states.
    Snapshots   (RealtimeGame default, see realtime.py) Messages and timers don't send game
                changes; once per tick every client gets a "snap" with what changed since the
                last snap it got (sent even when empty: it carries the tick time). Keyframes as
                in PatchState. A client still busy receiving the previous message is skipped
                for that tick, so a slow connection never holds up the room.

The game code is the same whichever is used: game_state() and private_state(member).

Wire format (PatchState and Snapshots; FullState sends only "state" messages as always):
    {"type": "state", ..., "seq": n}                  full state (same shape as FullState's)
    {"type": "patch", "seq": n, "base": m, "g"?: ..., "p"?: ...}
    {"type": "snap", "seq": n, "base": m, "tick": k, "t": ms, "ack": i, "g"?: ..., "p"?: ...}
`g`/`p` are RFC 7386 merge patches of state.game/state.private against the message with seq
`base` (key absent = unchanged, null = deleted, lists and other values replaced whole). The
connection is TCP (ordered and reliable), so each delta is against the last message actually
sent to that client and no acks are needed. A client that sees base != its last seq sends
{"type": "resync"} and gets a keyframe. `t` is the server time (ms) of the tick, for
interpolation; `ack` is the last input seq the server applied for that member (realtime.py).

Rules for games using PatchState or Snapshots (deltas stay small and correct):
- Keep collections that change in dicts keyed by id ({"p1": {...}}), not lists: a changed
  list is resent whole.
- Don't rely on None inside dicts: a null in a patch means "delete the key". Leave the key out.
- Round floats (quantize) so values that didn't really change don't produce diffs.
State is compared as JSON (int dict keys become strings, tuples become lists), as clients see it.

Helpers: merge_diff(old, new), merge_apply(doc, patch), quantize(value, step).
Client side: web/gamekit/lobby.js applies patches and snaps (state, onState, onSnapshot).
"""

import asyncio
import json
import logging

log = logging.getLogger("sync")


# --- Merge patches (RFC 7386) ---------------------------------------------------------

def merge_diff(old, new):
    """Merge patch that turns `old` into `new` (both JSON values). Call only when old != new."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return new
    patch = {}
    for key, value in new.items():
        if key not in old:
            patch[key] = value
        elif old[key] != value:
            patch[key] = merge_diff(old[key], value)
    for key in old:
        if key not in new:
            patch[key] = None
    return patch


def merge_apply(doc, patch):
    """Return `doc` with `patch` applied (doc isn't modified)."""
    if not isinstance(patch, dict):
        return patch
    result = dict(doc) if isinstance(doc, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge_apply(result.get(key), value)
    return result


def quantize(value, step=0.1):
    """Round a number to a multiple of `step` (e.g. positions to 0.1), as an int when step is whole."""
    rounded = round(value / step) * step
    return int(rounded) if float(step).is_integer() else round(rounded, 6)


def as_json(value):
    """The value as clients will see it (fresh copy; int keys -> str, tuples -> lists)."""
    return json.loads(json.dumps(value))


# --- Strategies ------------------------------------------------------------------------

class FullState:
    """Everything to everyone after every change (the original behavior)."""

    def reset(self, client_id):
        pass

    async def send(self, game):
        state = game.state()
        await asyncio.gather(*(
            connection.send({**state, "you": member.id, "private": game.private_game(member)})
            for connection, member in game.recipients()
        ))


class _Sent:
    """What a client has: the last message's seq, and the lobby/game/private it was built from."""

    def __init__(self, seq, lobby, public, private):
        self.seq, self.lobby, self.public, self.private = seq, lobby, public, private


class PatchState:
    """Keyframes when the lobby part changes, merge patches of game/private otherwise."""

    def __init__(self):
        self.sent = {}  # client id -> _Sent
        self._seq = 0

    def reset(self, client_id):
        self.sent.pop(client_id, None)

    async def send(self, game):
        await asyncio.gather(*(connection.send(message) for connection, message in self._messages(game)))

    def _messages(self, game, kind="patch", extra=None, keyframes_only=False, skip=()):
        """(connection, message) for every client that needs one. Updates what each client has.

        keyframes_only: send only full states (to clients whose lobby part changed).
        skip: client ids that get no delta this time (they still get a keyframe if needed).
        kind: the delta message type ("patch", or "snap" for ticks).
        extra(member): fields added to each delta; with it, deltas are sent even when empty.

        `public` (game_state) is converted once and shared by every client's record: records
        are never modified, only replaced.
        """
        lobby = as_json(game.lobby_state())
        public = as_json(game.public_game())
        for connection, member in game.recipients():
            client_id = member.client_id
            private = as_json(game.private_game(member))
            before = self.sent.get(client_id)
            if before is None or before.lobby != lobby:
                message = {**lobby, "game": public, "you": member.id, "private": private}
                result = message.pop("result")
                message["result"] = result
            elif keyframes_only or client_id in skip:
                continue
            else:
                message = {"type": kind, "base": before.seq}
                if extra:
                    message.update(extra(member))
                if public != before.public:
                    message["g"] = merge_diff(before.public, public)
                if private != before.private:
                    message["p"] = merge_diff(before.private, private)
                if not extra and "g" not in message and "p" not in message:
                    continue
            self._seq += 1
            message["seq"] = self._seq
            self.sent[client_id] = _Sent(self._seq, lobby, public, private)
            yield connection, message


class Snapshots(PatchState):
    """One delta per tick per client (see the module docstring). Used by RealtimeGame."""

    def __init__(self):
        super().__init__()
        self._outbox = {}  # client id -> task sending that client's latest message

    async def send(self, game):
        """After a message or timer: keyframes only (lobby changes) while playing; game
        changes wait for the next tick. Outside play (no ticks) it behaves like PatchState
        (plain "patch" messages, which carry no tick time)."""
        playing = game.phase == "playing"
        tasks = [self._queue(connection, message) for connection, message
                 in self._messages(game, keyframes_only=playing)]
        if tasks:
            await asyncio.gather(*tasks)

    def send_tick(self, game, tick, time_ms):
        """Queue this tick's snaps without waiting for any client.

        A client whose previous message is still being sent is skipped (unless it needs a
        keyframe); what it has stays recorded, so its next snap is still a correct delta.
        """
        def extra(member):
            return {"tick": tick, "t": time_ms, "ack": member.input_seq}

        busy = {cid for cid, task in self._outbox.items() if not task.done()}
        for connection, message in self._messages(game, kind="snap", extra=extra, skip=busy):
            self._queue(connection, message)

    def reset(self, client_id):
        super().reset(client_id)
        task = self._outbox.get(client_id)
        if task is not None and task.done():
            del self._outbox[client_id]

    async def drain(self):
        """Wait until every queued message has been sent (tests)."""
        while any(not task.done() for task in self._outbox.values()):
            await asyncio.gather(*self._outbox.values(), return_exceptions=True)

    def _queue(self, connection, message):
        """Send after this client's previous message, so messages never overtake each other."""
        previous = self._outbox.get(connection.id)

        async def run():
            if previous is not None and not previous.done():
                await asyncio.gather(previous, return_exceptions=True)
            try:
                await connection.send(message)
            except Exception:
                log.exception("Sending a snapshot failed")

        task = asyncio.get_running_loop().create_task(run())
        self._outbox[connection.id] = task
        return task
