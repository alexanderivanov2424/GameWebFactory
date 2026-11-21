/*
 * Metro Lanes page wiring: connects to the lobby, switches between the lobby page and the
 * full-screen game (body.ml-playing), and starts the other modules: ML.city (city.js, lookups),
 * ML.view (view.js, the canvas), ML.input (input.js, controls) and ML.hud (hud.js, refreshed on
 * each state and 5 times a second so snapshots don't rebuild the DOM every tick).
 */
(() => {
  const ML = (window.ML = window.ML || {});
  const { $ } = AppDom;
  let state = null;
  let lastGameNumber = null;

  const lobby = AppLobby.connect("motorways", {
    onState(newState) { state = newState; ML.city.update(state.game); render(); },
    onSnapshot(newState) { state = newState; ML.city.update(state.game); },
    onError: (message) => showError(message),
    onConnection(status) { $("connection").textContent = AppLobbyUI.connectionText(status, lobby.roomId); },
  });
  const showError = AppLobbyUI.errorBox($("error"));
  const rt = AppRealtime.attach(lobby);
  const renderButtons = AppLobbyUI.lobbyButtons(lobby, { join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back") });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);
  ML.view.init(lobby, rt);
  ML.input.init(lobby, showError);
  ML.hud.init(lobby);

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    document.body.classList.toggle("ml-playing", !inLobby);
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
      ML.view.reset();
      ML.input.reset();
      ML.hud.reset();
    }
    ML.hud.refresh(state);
  }

  setInterval(() => { if (state && state.phase !== "lobby" && state.game) ML.hud.refresh(state); }, 200);
})();
