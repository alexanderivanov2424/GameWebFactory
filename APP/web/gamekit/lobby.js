/*
 * Lobby client for games built on gamekit/lobby.py (server). Requires room.js (and uses settings.js if loaded).
 *
 *   const lobby = AppLobby.connect("my-game", {
 *     onState(state)       { ... },  // full room state after every change
 *     onError(message)     { ... },  // a request was rejected
 *     onConnection(status) { ... },  // "online" | "offline" | "replaced"
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
 * Your display name is sent on connect and whenever it changes in settings. Whether you
 * joined is remembered for the tab, so a reload keeps your seat.
 */
(() => {
  function connect(gameId, handlers = {}) {
    const myName = () => window.AppSettings?.get("username") || "Anonymous";
    let state = null;
    let wantJoined = false;

    const room = AppRoom.connect(gameId, {
      onOpen() {
        room.send({ type: "name", name: myName() });
        if (wantJoined) room.send({ type: "join" });
        handlers.onConnection?.("online");
      },
      onMessage(data) {
        if (data.type === "state") {
          state = data;
          rememberJoined(Boolean(api.me()?.player));
          handlers.onState?.(data);
        } else if (data.type === "error") {
          handlers.onError?.(data.message);
        }
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
    };
    return api;
  }

  window.AppLobby = { connect };
})();
