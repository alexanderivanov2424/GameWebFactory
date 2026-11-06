(() => {
  const { $ } = AppDom;
  let state = null;

  const lobby = AppLobby.connect("arena", {
    onState(newState) {
      state = newState;
      render();
    },
    onError: (message) => showError(message),
    onConnection(status) {
      $("connection").textContent = AppLobbyUI.connectionText(status, lobby.roomId);
    },
    onSnapshot() {}, // per-tick snapshots are drawn by the canvas loop, not the DOM
  });
  const showError = AppLobbyUI.errorBox($("error"));
  const rt = AppRealtime.attach(lobby);

  const renderButtons = AppLobbyUI.lobbyButtons(lobby, {
    join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back"),
  });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);

  rt.controls(
    {
      KeyW: "up", ArrowUp: "up", KeyS: "down", ArrowDown: "down",
      KeyA: "left", ArrowLeft: "left", KeyD: "right", ArrowRight: "right",
    },
    { enabled: () => state?.phase === "playing" && Boolean(lobby.me()?.player) },
  );

  $("end").addEventListener("click", () => lobby.sendGame({ action: "end" }));

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    renderButtons();
    if (inLobby) renderLobby();
    else renderGame();
  }

  function renderLobby() {
    AppLobbyUI.renderPlayers($("players"), lobby, { afterName: () => null });
    AppLobbyUI.renderStart($("start"), lobby);
    AppLobbyUI.renderSpectators($("spectators"), state);
    renderSettings();
  }

  function renderGame() {
    const finished = state.phase === "finished";
    $("result").hidden = !finished;
    $("result").textContent = finished ? (state.result?.reason || "Round over.") : "";
    $("end").hidden = finished || !lobby.isHost();
    updateStatus();
  }

  function updateStatus() {
    if (!state || state.phase === "lobby") return;
    const count = Object.keys(state.game?.dots || {}).length;
    const ping = rt.ping == null ? "…" : Math.round(rt.ping);
    const text = `Players: ${count} · your ping: ${ping} ms`;
    if ($("status").textContent !== text) $("status").textContent = text;
  }

  const canvas = $("arena");
  const ctx = canvas.getContext("2d");

  AppRealtime.loop(() => {
    if (!state || state.phase === "lobby" || $("game").hidden) return;
    const arena = state.game?.arena;
    if (!arena) return;
    updateStatus();
    if (canvas.width !== arena.w) canvas.width = arena.w;
    if (canvas.height !== arena.h) canvas.height = arena.h;
    ctx.fillStyle = "#1d2330";
    ctx.fillRect(0, 0, arena.w, arena.h);
    const dots = rt.sample((game) => game.dots) || {};
    ctx.textAlign = "center";
    ctx.textBaseline = "alphabetic";
    ctx.font = "13px sans-serif";
    ctx.lineJoin = "round";
    for (const [id, dot] of Object.entries(dots)) {
      const mine = id === state.you;
      ctx.beginPath();
      ctx.arc(dot.x, dot.y, arena.r, 0, Math.PI * 2);
      ctx.fillStyle = dot.color;
      ctx.fill();
      ctx.lineWidth = mine ? 4 : 1.5;
      ctx.strokeStyle = mine ? "#ffffff" : "rgba(0,0,0,0.6)";
      ctx.stroke();
      const label = `${dot.name} · ${dot.ping == null ? "…" : Math.round(dot.ping)} ms`;
      const ty = dot.y - arena.r - 8;
      ctx.lineWidth = 3;
      ctx.strokeStyle = "rgba(0,0,0,0.85)";
      ctx.strokeText(label, dot.x, ty);
      ctx.fillStyle = "#ffffff";
      ctx.fillText(label, dot.x, ty);
    }
  });
})();
