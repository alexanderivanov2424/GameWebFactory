/*
 * Snowbound page wiring: connects to the lobby, switches between the lobby page and the full-screen
 * game (body.sb-playing), and starts the other modules: SB.grid (grid.js), SB.view (view.js, the
 * canvas), SB.input (input.js, controls) and SB.hud (hud.js, refreshed 5 times a second).
 */
(() => {
  const SB = (window.SB = window.SB || {});
  const { $ } = AppDom;
  let state = null;
  let lastGameNumber = null;

  const lobby = AppLobby.connect("snowbound", {
    onState(newState) { state = newState; SB.view.snap(state); render(); },
    onSnapshot(newState) { state = newState; SB.view.snap(state); },
    onError: (message) => showError(message),
    onConnection(status) { $("connection").textContent = AppLobbyUI.connectionText(status, lobby.roomId); },
  });
  const showError = AppLobbyUI.errorBox($("error"));
  const rt = AppRealtime.attach(lobby);
  const renderButtons = AppLobbyUI.lobbyButtons(lobby, { join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back") });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);
  SB.view.init(lobby, rt);
  SB.input.init(lobby);
  SB.hud.init(lobby);

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    document.body.classList.toggle("sb-playing", !inLobby);
    renderButtons();
    if (inLobby) {
      AppLobbyUI.renderPlayers($("players"), lobby, {});
      AppLobbyUI.renderStart($("start"), lobby);
      AppLobbyUI.renderSpectators($("spectators"), state);
      renderSettings();
      return;
    }
    if (state.gameNumber !== lastGameNumber) {
      lastGameNumber = state.gameNumber;
      SB.grid.reset();
      SB.view.reset();
      SB.input.reset();
      SB.hud.reset();
    }
    SB.hud.refresh(state);
  }

  setInterval(() => { if (state && state.phase !== "lobby") SB.hud.refresh(state); }, 200);
})();
