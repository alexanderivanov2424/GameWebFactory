/*
 * Deep Colony page wiring: connects to the lobby, switches the lobby/game sections, and drives
 * the other modules (DC.grid, DC.render, DC.tools, DC.panels). Panels refresh from a timer
 * (~4 Hz) while playing; per-tick snapshots only feed the canvas loop.
 */
(() => {
  const DC = (window.DC = window.DC || {});
  const { $ } = AppDom;
  let state = null;
  let lastGameNumber = null;

  const lobby = AppLobby.connect("deep-colony", {
    onState(newState) {
      state = newState;
      render();
    },
    onError: (message) => showError(message),
    onConnection(status) {
      $("connection").textContent = AppLobbyUI.connectionText(status, lobby.roomId);
    },
    onSnapshot() {},
  });
  const showError = AppLobbyUI.errorBox($("error"));
  DC.lobby = lobby;
  DC.rt = AppRealtime.attach(lobby);

  const renderButtons = AppLobbyUI.lobbyButtons(lobby, {
    join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back"),
  });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);

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
    if (state.gameNumber !== lastGameNumber) {
      lastGameNumber = state.gameNumber;
      DC.view.drag = null;
      DC.view.last = null;
      DC.tools.resetInput();
      DC.tools.setTool("inspect");
    }
    DC.panels.refresh();
  }

  setInterval(() => {
    if (state && state.phase !== "lobby" && !$("game").hidden) DC.panels.refresh();
  }, 250);
})();
