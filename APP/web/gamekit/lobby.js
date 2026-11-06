/*
 * Lobby client for games built on gamekit/lobby.py (server). Requires room.js (and uses settings.js if loaded).
 *
 *   const lobby = AppLobby.connect("my-game", {
 *     onState(state)       { ... },  // full room state after every change
 *     onError(message)     { ... },  // a request was rejected
 *     onConnection(status) { ... },  // "online" | "offline" | "replaced"
 *     onSnapshot(state, snap) { ... }, // optional, real-time games: state after each tick
 *   });
 *
 * state: { phase: "lobby" | "playing" | "finished", you, hostId, settings, settingsSpec, startBlocker,
 *          players: [{ id, name, connected, ready, options }], spectators: [{ id, name, connected }],
 *          game, private, result, gameNumber, minPlayers, maxPlayers }
 *
 * gameNumber counts games started in this room: key per-game client data (marks, which
 * animations already played) by it. settingsSpec describes the host settings for
 * AppLobbyUI.settingsForm. game is the game's public state (null in the lobby), private
 * is what only you may see.
 *
 * Actions: lobby.join(), leave(), setReady(bool), setOptions(obj), updateSettings(obj),
 *          start() (host only, once startBlocker is null), makeHost(playerId), backToLobby(),
 *          sendGame(obj)
 *
 * startBlocker is the reason the host can't start yet (null when they can).
 * Helpers: lobby.me() -> your entry plus { player: true/false }, lobby.isHost()
 *
 * State sync (see gamekit/sync.py; the game's SYNC decides): besides full "state" messages the
 * server may send "patch" (changes only) and, for real-time games, "snap" (once per tick).
 * Both are applied here, so `state` is always complete. A patch calls onState; a snap calls
 * onSnapshot if given (so a page can redraw a canvas without re-rendering its lobby UI every
 * tick), else onState. Each update builds new objects along the changed paths and shares the
 * rest, so an older `state` (or state.game) you kept stays as it was.
 *
 * More: lobby.on(type, fn) also calls fn(message) for every server message of that type
 * ("state", "snap", "pong", ...), lobby.send(obj) sends a raw message, and
 * lobby.sendInput(obj) sends a real-time input ({type: "input", seq, ...obj}) and returns its seq.
 *
 * Your display name is sent on connect and whenever it changes in settings. Whether you
 * joined is remembered for the tab, so a reload keeps your seat.
 */
(() => {
  function connect(gameId, handlers = {}) {
    const myName = () => window.AppSettings?.get("username") || "Anonymous";
    let state = null;
    let wantJoined = false;
    let resyncing = false;
    let inputSeq = 0;
    const listeners = {};

    // RFC 7386 merge patch; copies only the changed paths (see gamekit/sync.py).
    function mergeApply(doc, patch) {
      if (patch === null || typeof patch !== "object" || Array.isArray(patch)) return patch;
      const result = doc !== null && typeof doc === "object" && !Array.isArray(doc) ? { ...doc } : {};
      for (const [key, value] of Object.entries(patch)) {
        if (value === null) delete result[key];
        else result[key] = mergeApply(result[key], value);
      }
      return result;
    }

    function applyDelta(data) {
      if (!state) return false; // nothing to apply to yet; the full state is on its way
      if (data.base !== state.seq) {
        if (!resyncing) room.send({ type: "resync" });
        resyncing = true;
        return false;
      }
      const next = { ...state, seq: data.seq };
      if ("g" in data) next.game = mergeApply(state.game, data.g);
      if ("p" in data) next.private = mergeApply(state.private, data.p);
      state = next;
      return true;
    }

    const room = AppRoom.connect(gameId, {
      onOpen() {
        room.send({ type: "name", name: myName() });
        if (wantJoined) room.send({ type: "join" });
        handlers.onConnection?.("online");
      },
      onMessage(data) {
        if (data.type === "state") {
          state = data;
          resyncing = false;
          rememberJoined(Boolean(api.me()?.player));
          handlers.onState?.(data);
        } else if (data.type === "patch") {
          if (!applyDelta(data)) return;
          handlers.onState?.(state);
        } else if (data.type === "snap") {
          if (!applyDelta(data)) return;
          if (handlers.onSnapshot) handlers.onSnapshot(state, data);
          else handlers.onState?.(state);
        } else if (data.type === "error") {
          handlers.onError?.(data.message);
        }
        for (const fn of listeners[data.type] || []) fn(data);
      },
      onClose({ replaced }) {
        handlers.onConnection?.(replaced ? "replaced" : "offline");
      },
    });

    const storageKey = `lobby.${gameId}.${room.roomId}.joined`;
    try {
      wantJoined = sessionStorage.getItem(storageKey) === "1";
    } catch {}

    function rememberJoined(value) {
      wantJoined = value;
      try {
        sessionStorage.setItem(storageKey, value ? "1" : "");
      } catch {}
    }

    window.AppSettings?.onChange((key, value) => {
      if (key === "username") room.send({ type: "name", name: value });
    });

    const api = {
      roomId: room.roomId,
      get state() {
        return state;
      },
      me() {
        if (!state) return null;
        const player = state.players.find((p) => p.id === state.you);
        if (player) return { ...player, player: true };
        const spectator = state.spectators.find((s) => s.id === state.you);
        return spectator ? { ...spectator, player: false } : null;
      },
      isHost: () => Boolean(state) && state.hostId === state.you,
      join: () => room.send({ type: "join" }),
      leave: () => room.send({ type: "leave" }),
      setReady: (ready) => room.send({ type: "ready", ready }),
      setOptions: (options) => room.send({ type: "options", options }),
      updateSettings: (settings) => room.send({ type: "settings", settings }),
      start: () => room.send({ type: "start" }),
      makeHost: (playerId) => room.send({ type: "make_host", playerId }),
      backToLobby: () => room.send({ type: "back_to_lobby" }),
      sendGame: (data) => room.send({ ...data, type: "game" }),
      sendInput(data) {
        inputSeq++;
        room.send({ ...data, type: "input", seq: inputSeq });
        return inputSeq;
      },
      send: (data) => room.send(data),
      on(type, fn) {
        (listeners[type] ||= []).push(fn);
      },
    };
    return api;
  }

  window.AppLobby = { connect };
})();
