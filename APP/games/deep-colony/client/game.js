(() => {
  const { $, el, debounce, setInput } = AppDom;
  let state = null;

  const lobby = AppLobby.connect("deep-colony", {
    onState(newState) {
      state = newState;
      render();
    },
    onError: (message) => showError(message),
    onConnection(status) {
      $("connection").textContent = AppLobbyUI.connectionText(status, lobby.roomId);
    },
  });
  const showError = AppLobbyUI.errorBox($("error"));

  // Join / Leave / Ready / Back to lobby buttons, and the host settings (from SETTINGS in server.py).
  const renderButtons = AppLobbyUI.lobbyButtons(lobby, {
    join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back"),
  });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);
  // For turn-based games: makes the board pulse when your turn starts.
  const updateTurnAlert = AppLobbyUI.turnAlert($("board"));

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    renderButtons();
    if (inLobby) renderLobby();
    else renderGame();
  }

  function renderLobby() {
    updateTurnAlert(null);
    // afterName adds game-specific info next to each name (e.g. a color swatch).
    AppLobbyUI.renderPlayers($("players"), lobby, { afterName: (player) => null });
    AppLobbyUI.renderStart($("start"), lobby);
    AppLobbyUI.renderSpectators($("spectators"), state);
    renderSettings();
    // TODO player options (lobby.setOptions, debounced; use setInput so typing isn't overwritten)
  }

  function renderGame() {
    const game = state.game;
    const finished = state.phase === "finished";
    const myTurn = !finished && game.turn === state.you;
    updateTurnAlert(myTurn ? `${state.gameNumber}:${game.turnOrder.join()}` : null); // TODO a real step id
    $("result").hidden = !finished;
    $("result").textContent = finished ? "TODO describe state.result" : "";
    $("board").replaceChildren(el("p", { className: "muted" }, "TODO"));
    // TODO render state.game (public) and state.private (only yours).
    // Send moves with lobby.sendGame({ action: "...", ... }).
  }
})();
