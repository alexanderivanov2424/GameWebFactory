(() => {
  const { $, el, debounce, setInput } = AppDom;
  let state = null;

  const lobby = AppLobby.connect("tictactoe", {
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

  // --- Small helpers -------------------------------------------------------------

  function piece(color) {
    const dot = el("span", { className: "piece" });
    dot.style.background = color;
    return dot;
  }

  const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const rgbToHex = (rgb) => "#" + rgb.map((n) => n.toString(16).padStart(2, "0")).join("");

  // --- Lobby controls ------------------------------------------------------------

  const renderButtons = AppLobbyUI.lobbyButtons(lobby, {
    join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back"),
  });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);

  function readRgb() {
    const values = ["r", "g", "b"].map((id) => Number($(id).value));
    const valid = ["r", "g", "b"].every((id) => $(id).value !== "") &&
      values.every((n) => Number.isInteger(n) && n >= 0 && n <= 255);
    return valid ? values : null;
  }

  const sendColor = debounce(() => {
    const rgb = readRgb();
    if (rgb) lobby.setOptions({ color: rgbToHex(rgb) });
  }, 300);

  ["r", "g", "b"].forEach((id) =>
    $(id).addEventListener("input", () => {
      const rgb = readRgb();
      if (rgb) $("color-preview").style.background = rgbToHex(rgb);
      sendColor();
    })
  );

  // --- Rendering -----------------------------------------------------------------

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    renderButtons();
    if (inLobby) renderLobby();
    else renderGame();
  }

  function renderLobby() {
    const me = lobby.me();

    // Players: [check] name (you) (piece) [Host] [Offline] ... [Make host]
    AppLobbyUI.renderPlayers($("players"), lobby, {
      afterName: (player) => piece(player.options.color || "transparent"),
    });
    AppLobbyUI.renderStart($("start"), lobby);
    AppLobbyUI.renderSpectators($("spectators"), state);

    // Your piece and ready button.
    $("my-controls").hidden = !me?.player;
    if (me?.player) {
      const color = me.options.color || "#000000";
      const [r, g, b] = hexToRgb(color);
      const editing = ["r", "g", "b"].some((id) => document.activeElement === $(id));
      if (!editing) {
        setInput($("r"), r);
        setInput($("g"), g);
        setInput($("b"), b);
        $("color-preview").style.background = color;
      }
    }

    // Settings (from SETTINGS in server.py): everyone sees them, only the host can change them.
    renderSettings();
  }

  function renderGame() {
    const game = state.game;
    const finished = state.phase === "finished";
    const result = state.result || {};
    const winCells = new Set((result.line || []).map(([r, c]) => `${r},${c}`));
    const myTurn = !finished && game.turn === state.you;

    // Result or whose turn it is.
    $("result").hidden = !finished;
    $("turn").hidden = finished;
    if (finished) {
      const winner = result.winner && game.pieces[result.winner];
      $("result").replaceChildren(
        ...(winner
          ? [piece(winner.color), `${result.winner === state.you ? "You win" : `${winner.name} wins`}!`]
          : ["It's a draw!"]),
        result.reason ? el("span", { className: "muted" }, ` ${result.reason}`) : ""
      );
    } else {
      const current = game.pieces[game.turn];
      $("turn").replaceChildren(
        current ? piece(current.color) : "",
        myTurn ? "Your turn!" : current ? `${current.name}'s turn` : ""
      );
    }

    // Board.
    const board = $("board");
    board.style.gridTemplateColumns = `repeat(${game.size}, var(--cell))`;
    board.style.gridTemplateRows = `repeat(${game.size}, var(--cell))`;
    const cells = [];
    for (let row = 0; row < game.size; row++) {
      for (let col = 0; col < game.size; col++) {
        const owner = game.board[row][col];
        const cell = el("button", { className: "cell" });
        cell.setAttribute("aria-label", owner ? `Row ${row + 1}, column ${col + 1}: ${game.pieces[owner].name}` : `Row ${row + 1}, column ${col + 1}: empty`);
        if (owner) cell.append(piece(game.pieces[owner].color));
        if (winCells.has(`${row},${col}`)) cell.classList.add("win");
        if (game.lastMove && game.lastMove[0] === row && game.lastMove[1] === col) cell.classList.add("last");
        cell.disabled = !myTurn || owner !== null;
        cell.addEventListener("click", () => lobby.sendGame({ action: "place", row, col }));
        cells.push(cell);
      }
    }
    board.replaceChildren(...cells);

    // Turn order.
    $("order").replaceChildren(
      ...game.turnOrder.map((id) => {
        const info = game.pieces[id];
        const item = el("li", {}, piece(info.color), info.name + (id === state.you ? " (you)" : ""));
        if (id === game.turn && !finished) item.classList.add("current");
        return item;
      })
    );

    const isHost = lobby.isHost();
    $("game-note").textContent = finished
      ? isHost ? "" : "Waiting for the host to return to the lobby."
      : `Get ${game.winLength} in a row to win.`;
  }
})();
