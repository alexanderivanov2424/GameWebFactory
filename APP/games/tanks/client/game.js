(() => {
  const { $, el } = AppDom;
  let state = null;

  const lobby = AppLobby.connect("tanks", {
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

  // --- Helpers -----------------------------------------------------------------------

  const colName = (c) => String.fromCharCode(65 + c);
  const rowName = (r) => String(r + 1);
  const coord = (r, c) => colName(c) + rowName(r);
  const key = (r, c) => `${r},${c}`;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  const names = () => Object.fromEntries((state.game?.players || []).map((p) => [p.id, p.name]));
  const myGamePlayer = () => state.game?.players.find((p) => p.id === state.you) || null;
  const myLocation = () => state.private?.location || null;
  const inGame = () => state && state.phase !== "lobby";
  const isMyTurn = () =>
    inGame() && state.phase === "playing" && state.game.stage === "action" &&
    state.game.current === state.you && Boolean(myGamePlayer()?.alive);
  const isPlacing = () => {
    const me = myGamePlayer();
    return inGame() && state.phase === "playing" && state.game.stage === "placing" && me?.alive && !me.placed;
  };

  // --- Lobby ---------------------------------------------------------------------------

  const renderButtons = AppLobbyUI.lobbyButtons(lobby, {
    join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back"),
  });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);

  function renderLobby() {
    AppLobbyUI.renderPlayers($("players"), lobby);
    AppLobbyUI.renderStart($("start"), lobby);
    AppLobbyUI.renderSpectators($("spectators"), state);
    // Settings (from SETTINGS in server.py): everyone sees them, only the host can change them.
    renderSettings();
  }

  // --- Personal marks (only in this tab, never sent) -------------------------------------------

  const NEXT_MARK = { none: "suspect", suspect: "clear", clear: "none" };
  let marks = {};
  let marksKey = "";

  // Marks are set only by clicking squares; nothing is marked automatically.
  function loadMarks(storageKey) {
    if (storageKey === marksKey) return;
    marksKey = storageKey;
    try {
      marks = (JSON.parse(sessionStorage.getItem(storageKey)) || {}).marks || {};
    } catch {
      marks = {};
    }
  }

  function saveMarks() {
    try {
      sessionStorage.setItem(marksKey, JSON.stringify({ marks }));
    } catch {}
  }

  $("clear-marks").addEventListener("click", () => {
    marks = {};
    saveMarks();
    updateBoard();
  });

  // --- Action state -----------------------------------------------------------------------------

  // null | "scan" | "spray" | "artillery" | "blast" | "move" | "mine" | "wall" | "unwall"
  let targeting = null;
  let hover = null; // [row, col] under the pointer
  let hoverEdge = null; // [[r1, c1], [r2, c2]] nearest inner edge while building/removing walls
  let scanSel = null; // {axis: "row" | "col", anchor, end} chosen on the board's labels
  let scanHover = null; // {axis, index} label under the pointer
  let scanDragging = false;
  let placing = { tank: null, mines: [], mode: "tank" }; // placing stage, before confirming
  let lastGameNumber = null;

  function startTargeting(mode) {
    if (!isMyTurn()) return;
    targeting = mode;
    scanSel = null;
    hoverEdge = null;
    renderActions();
    updateBoard();
  }

  function stopTargeting() {
    targeting = null;
    scanSel = null;
    hoverEdge = null;
    renderActions();
    updateBoard();
  }

  document.querySelectorAll("#action-menu [data-mode]").forEach((button) =>
    button.addEventListener("click", () => startTargeting(button.dataset.mode))
  );
  $("heal-btn").addEventListener("click", () => {
    if (isMyTurn()) lobby.sendGame({ action: "heal" });
  });
  $("cancel-target").addEventListener("click", stopTargeting);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && targeting) stopTargeting();
  });
  document.addEventListener("mouseup", () => {
    scanDragging = false;
  });

  // --- Whose turn: the board pulses at the start of your turn until you click anything --------

  const updateTurnAlert = AppLobbyUI.turnAlert($("board-card"), { text: "Your turn! Pick an action." });

  function renderTurnAlert() {
    updateTurnAlert(
      isMyTurn() ? `${state.gameNumber}:${state.game.log.length}`
        : isPlacing() ? `${state.gameNumber}:placing` : null
    );
  }

  // --- Scan selection on the board's row/column labels --------------------------------------------

  const scanCost = (lines) => state.game.costs.scan[lines - 1];

  function scanRange() {
    if (!scanSel) return null;
    return [Math.min(scanSel.anchor, scanSel.end), Math.max(scanSel.anchor, scanSel.end)];
  }

  function onLabelDown(axis, index, e) {
    if (targeting !== "scan" || !isMyTurn()) return;
    e.preventDefault();
    if (e.shiftKey && scanSel?.axis === axis) scanSel.end = index;
    else scanSel = { axis, anchor: index, end: index };
    scanDragging = true;
    renderActions();
    updateBoard();
  }

  function extendScan(axis, index) {
    if (!scanDragging || targeting !== "scan" || scanSel?.axis !== axis || scanSel.end === index) return;
    scanSel.end = index;
    renderActions();
  }

  $("scan-btn").addEventListener("click", () => {
    const range = scanRange();
    if (!range || !isMyTurn()) return;
    lobby.sendGame({ action: "scan", axis: scanSel.axis, from: range[0], to: range[1] });
    stopTargeting();
  });

  // --- Placement: a tank square and the starting mines, then confirm ---------------------------

  const minesAtStart = () => state.game.rules.minesAtStart;

  $("place-tank-mode").addEventListener("click", () => {
    placing.mode = "tank";
    renderPlacement();
  });
  $("place-mine-mode").addEventListener("click", () => {
    placing.mode = "mines";
    renderPlacement();
  });
  $("place-btn").addEventListener("click", () => {
    if (!placing.tank || placing.mines.length !== minesAtStart()) return;
    lobby.sendGame({ action: "place", row: placing.tank[0], col: placing.tank[1], mines: placing.mines });
  });

  function onPlaceClick(r, c) {
    if (placing.mode === "tank") {
      placing.tank = [r, c];
      if (placing.mines.length < minesAtStart()) placing.mode = "mines";
    } else {
      const index = placing.mines.findIndex(([a, b]) => a === r && b === c);
      if (index >= 0) placing.mines.splice(index, 1);
      else {
        if (placing.mines.length >= minesAtStart()) placing.mines.shift();
        placing.mines.push([r, c]);
      }
    }
    renderPlacement();
  }

  // --- Board geometry -------------------------------------------------------------------------------

  // Walls between neighboring squares, as "r1,c1|r2,c2" with the smaller square first.
  let wallSet = new Set();
  const wallKey = (r1, c1, r2, c2) =>
    r1 < r2 || (r1 === r2 && c1 < c2) ? `${r1},${c1}|${r2},${c2}` : `${r2},${c2}|${r1},${c1}`;
  const hasWall = (r1, c1, r2, c2) => wallSet.has(wallKey(r1, c1, r2, c2));
  const DIRECTIONS = { up: [-1, 0], down: [1, 0], left: [0, -1], right: [0, 1] };
  const onBoard = (r, c) => r >= 0 && r < state.game.size && c >= 0 && c < state.game.size;

  /** Walking distance from a square (walls block), up to limit steps. extraWall: a wall key to add. */
  function stepsFrom([r0, c0], limit = Infinity, extraWall = null) {
    const blocked = (r1, c1, r2, c2) => hasWall(r1, c1, r2, c2) || wallKey(r1, c1, r2, c2) === extraWall;
    const dist = new Map([[key(r0, c0), 0]]);
    let frontier = [[r0, c0]];
    for (let d = 1; d <= limit && frontier.length; d++) {
      const next = [];
      for (const [r, c] of frontier) {
        for (const [dr, dc] of Object.values(DIRECTIONS)) {
          const nr = r + dr;
          const nc = c + dc;
          if (onBoard(nr, nc) && !dist.has(key(nr, nc)) && !blocked(r, c, nr, nc)) {
            dist.set(key(nr, nc), d);
            next.push([nr, nc]);
          }
        }
      }
      frontier = next;
    }
    return dist;
  }

  /** Squares a blast could cross in each direction, until a wall or the edge. */
  function blastLines() {
    const [myRow, myCol] = myLocation();
    const lines = {};
    for (const [dir, [dr, dc]] of Object.entries(DIRECTIONS)) {
      lines[dir] = [];
      let r = myRow;
      let c = myCol;
      while (onBoard(r + dr, c + dc) && !hasWall(r, c, r + dr, c + dc)) {
        r += dr;
        c += dc;
        lines[dir].push(key(r, c));
      }
    }
    return lines;
  }

  const blastDirAt = (k) => Object.entries(blastLines()).find(([, cells]) => cells.includes(k))?.[0];

  /** Squares a targeting mode may pick (null = any square, or the mode doesn't pick squares). */
  function allowedCells() {
    const location = myLocation();
    if (!location) return new Set();
    const [myRow, myCol] = location;
    if (targeting === "blast") return new Set(Object.values(blastLines()).flat());
    if (targeting === "mine") return new Set(stepsFrom(location, state.game.rules.mineRange).keys());
    if (targeting === "move") {
      const cells = new Set();
      for (const [dr, dc] of Object.values(DIRECTIONS)) {
        const r = myRow + dr;
        const c = myCol + dc;
        if (onBoard(r, c) && !hasWall(myRow, myCol, r, c)) cells.add(key(r, c));
      }
      return cells;
    }
    return null;
  }

  /** Top-left of the 2x2 spray area for a hovered square, kept on the board. */
  function sprayAnchor([r, c]) {
    const max = state.game.size - 2;
    return [Math.min(r, max), Math.min(c, max)];
  }

  /** The inner edge of a square nearest the pointer, as [smaller square, other square]. */
  function nearestEdge(r, c, e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    const size = state.game.size;
    const options = [];
    if (r > 0) options.push([y, [r - 1, c]]);
    if (r < size - 1) options.push([1 - y, [r + 1, c]]);
    if (c > 0) options.push([x, [r, c - 1]]);
    if (c < size - 1) options.push([1 - x, [r, c + 1]]);
    if (!options.length) return null;
    options.sort((a, b) => a[0] - b[0]);
    const other = options[0][1];
    const mine = [r, c];
    return other[0] < r || (other[0] === r && other[1] < c) ? [other, mine] : [mine, other];
  }

  /** "ok" / "remove" if the wall action can use this edge, else "bad". */
  function edgeStatus([[r1, c1], [r2, c2]]) {
    const exists = hasWall(r1, c1, r2, c2);
    if (targeting === "unwall") return exists ? "remove" : "bad";
    if (exists) return "bad";
    return stepsFrom([r1, c1], Infinity, wallKey(r1, c1, r2, c2)).has(key(r2, c2)) ? "ok" : "bad";
  }

  function onCellClick(r, c, e) {
    if (!inGame()) return;
    if (isPlacing()) {
      onPlaceClick(r, c);
    } else if (targeting && isMyTurn()) {
      const k = key(r, c);
      if (targeting === "scan") return;
      if (targeting === "wall" || targeting === "unwall") {
        const edge = nearestEdge(r, c, e);
        if (!edge) return;
        const status = edgeStatus(edge);
        if (status === "bad") {
          showError(targeting === "unwall" ? "There's no wall there." : hasWall(...edge[0], ...edge[1])
            ? "There's already a wall there." : "That wall would cut the board in two.");
          return;
        }
        lobby.sendGame({ action: targeting, cells: edge });
      } else if (targeting === "spray") {
        const [row, col] = sprayAnchor([r, c]);
        lobby.sendGame({ action: "spray", row, col });
      } else if (targeting === "artillery") {
        lobby.sendGame({ action: "artillery", row: r, col: c });
      } else if (targeting === "blast") {
        const dir = blastDirAt(k);
        if (!dir) return;
        lobby.sendGame({ action: "blast", dir });
      } else {
        if (!allowedCells().has(k)) return;
        lobby.sendGame({ action: targeting, row: r, col: c });
      }
      targeting = null;
      hoverEdge = null;
      renderActions();
    } else {
      const k = key(r, c);
      const next = NEXT_MARK[marks[k] || "none"];
      if (next === "none") delete marks[k];
      else marks[k] = next;
      saveMarks();
    }
    updateBoard();
  }

  // --- Game rendering ------------------------------------------------------------------------

  function render() {
    const lobbyPhase = state.phase === "lobby";
    $("lobby").hidden = !lobbyPhase;
    $("game").hidden = lobbyPhase;
    renderButtons();
    if (lobbyPhase) {
      targeting = null;
      updateTurnAlert(null);
      renderLobby();
      return;
    }
    if (state.gameNumber !== lastGameNumber) {
      lastGameNumber = state.gameNumber;
      placing = { tank: null, mines: [], mode: "tank" };
      targeting = null;
    }
    if (!isMyTurn()) {
      targeting = null;
      scanSel = null;
    }

    loadMarks(`tanks.marks.${lobby.roomId}.${state.gameNumber}`);
    renderBanner();
    renderTanks();
    renderPlacement();
    renderActions();
    buildBoard();
    renderLog();
    renderTurnAlert();

    const finished = state.phase === "finished";
    $("game-note").textContent = finished
      ? lobby.isHost() ? "" : "Waiting for the host to return to the lobby."
      : "Your marks are private and only saved in this tab.";
  }

  function renderBanner() {
    const game = state.game;
    const me = myGamePlayer();
    const n = names();
    let text;
    if (state.phase === "finished") {
      const winner = state.result?.winner;
      text = winner === state.you ? "You win!" : winner ? `${n[winner]} wins!` : "Game over.";
      if (state.result?.reason) text += ` ${state.result.reason}`;
    } else if (game.stage === "placing") {
      const hidden = game.players.filter((p) => p.alive && p.placed).length;
      const total = game.players.filter((p) => p.alive).length;
      text = isPlacing()
        ? "Choose a hidden square for your tank and lay your mines."
        : `Waiting for tanks to hide (${hidden}/${total})…`;
    } else if (me && !me.alive) {
      text = "Your tank was destroyed. You're watching now.";
    } else if (game.current === state.you) {
      text = "▶ Your turn!";
    } else {
      text = `${n[game.current] || "?"}'s turn`;
    }
    $("banner").textContent = text;
    $("banner").classList.toggle("my-turn", isMyTurn() || Boolean(isPlacing()));
  }

  function renderTanks() {
    const game = state.game;
    $("tanks").replaceChildren(
      ...game.players.map((p) => {
        const item = el("li", { className: p.alive ? "" : "destroyed" });
        if (p.id === game.current) item.classList.add("current");

        let turnText;
        if (!p.alive) turnText = "—";
        else if (game.stage === "placing") turnText = p.placed ? "hidden" : "hiding…";
        else turnText = `(T+${p.turn})`;

        const bar = el("span", { className: "hp-bar", title: `${p.hp} / ${game.maxHp} HP` }, el("span"));
        bar.firstChild.style.width = `${(100 * p.hp) / game.maxHp}%`;

        const who = el("span", { className: "who" }, el("span", { className: "tname" }, p.name + (p.id === state.you ? " (you)" : "")));
        if (p.alive && p.shielded) {
          who.append(el("span", { className: "shield", title: "Takes no damage until its next turn" }, "🛡 Shielded"));
        }
        item.append(
          el("span", { className: "turn" }, turnText),
          who,
          el("span", { className: "spacer" }),
          bar, el("span", { className: "hp" }, p.alive ? `${p.hp} HP` : "Destroyed"));
        return item;
      })
    );
  }

  function renderPlacement() {
    $("place-panel").hidden = !isPlacing();
    if (!isPlacing()) return;
    const total = minesAtStart();
    const ready = placing.tank && placing.mines.length === total;
    $("place-tank-mode").textContent = `Tank: ${placing.tank ? coord(...placing.tank) : "—"}`;
    $("place-mine-mode").textContent = `Mines: ${placing.mines.length}/${total}`;
    $("place-tank-mode").classList.toggle("on", placing.mode === "tank");
    $("place-mine-mode").classList.toggle("on", placing.mode === "mines");
    $("place-btn").disabled = !ready;
    $("place-btn").textContent = ready ? `Hide at ${coord(...placing.tank)} and lay mines` : "Confirm";
    $("place-text").textContent = placing.mode === "tank"
      ? "Click a square for your tank. Only you will know where it is."
      : `Click ${total} different squares for your mines (click a mine again to remove it). ` +
        "A mine hits everyone on its square for 1 damage when a tank moves onto it.";
  }

  function costText(cost) {
    if (Array.isArray(cost)) {
      const low = Math.min(...cost);
      const high = Math.max(...cost);
      return low === high ? plural(low, "turn") : `${low}–${high} turns`;
    }
    return plural(cost, "turn");
  }

  function renderActions() {
    if (!inGame()) return;
    const game = state.game;
    $("actions").hidden = !isMyTurn();
    if (!isMyTurn()) return;

    $("action-menu").hidden = Boolean(targeting);
    $("targeting").hidden = !targeting;
    document.querySelectorAll("#action-menu [data-cost]").forEach((small) => {
      small.textContent = costText(game.costs[small.dataset.cost]);
    });
    const me = myGamePlayer();
    $("heal-btn").disabled = me.hp >= game.maxHp;
    $("heal-btn").title = me.hp >= game.maxHp ? "You're at full HP." : "Repair 1 HP.";

    const d = game.rules.damage;
    let text = {
      spray: `Spray: click to hit the highlighted 2×2 area (${d.spray} damage each).`,
      artillery: `Artillery: click any square to shell it (${d.artillery} damage).`,
      blast: `Blast: click a highlighted line. It hits the first tank in that direction for ${d.blast} damage; walls stop it. Others only learn where it hit, or "miss".`,
      move: "Move: click a highlighted square next to your tank (not through walls).",
      mine: `Mine: click a highlighted square within ${game.rules.mineRange} steps of your tank.`,
      wall: "Build wall: point at the gap between two squares and click. It can't cut the board in two.",
      unwall: "Remove wall: point at a wall and click.",
    }[targeting] || "";

    $("scan-btn").hidden = targeting !== "scan";
    if (targeting === "scan") {
      const range = scanRange();
      if (!range) {
        text = "Scan: click a row number or column letter on the board. Drag or Shift-click to pick several.";
        $("scan-btn").disabled = true;
        $("scan-btn").textContent = "Scan";
      } else {
        const [from, to] = range;
        const count = to - from + 1;
        const word = scanSel.axis === "row" ? "row" : "column";
        const name = scanSel.axis === "row" ? rowName : colName;
        const where = from === to ? `${word} ${name(from)}` : `${word}s ${name(from)}–${name(to)}`;
        text = `Scan ${where} (${plural(count, word)}). Drag or Shift-click to change it.`;
        $("scan-btn").disabled = false;
        $("scan-btn").textContent = `Scan · ${plural(scanCost(count), "turn")}`;
      }
    }
    $("targeting-text").textContent = text;
  }

  // The board is rebuilt on each state update; highlights are updated in place (e.g. on hover).
  let cellEls = [];
  let labelEls = { row: [], col: [] };

  function buildBoard() {
    const game = state.game;
    const size = game.size;
    const location = myLocation();
    const n = names();
    wallSet = new Set((game.walls || []).map(([r1, c1, r2, c2]) => wallKey(r1, c1, r2, c2)));

    // Tanks to draw: mine always; everyone's once the game is over.
    const tanksAt = {};
    if (game.locations) {
      for (const [pid, [r, c]] of Object.entries(game.locations)) (tanksAt[key(r, c)] ||= []).push(pid);
    } else if (location) {
      tanksAt[key(location[0], location[1])] = [state.you];
    }

    const board = $("board");
    board.style.gridTemplateColumns = `26px repeat(${size}, minmax(0, 1fr))`;
    const nodes = [el("span")];
    labelEls = { row: [], col: [] };
    const label = (axis, index, text) => {
      const node = el("span", { className: "label" }, text);
      node.addEventListener("mousedown", (e) => onLabelDown(axis, index, e));
      node.addEventListener("mouseenter", () => {
        scanHover = { axis, index };
        extendScan(axis, index);
        updateBoard();
      });
      node.addEventListener("mouseleave", () => {
        scanHover = null;
        updateBoard();
      });
      labelEls[axis].push(node);
      return node;
    };
    for (let c = 0; c < size; c++) nodes.push(label("col", c, colName(c)));

    cellEls = [];
    for (let r = 0; r < size; r++) {
      nodes.push(label("row", r, rowName(r)));
      const rowEls = [];
      for (let c = 0; c < size; c++) {
        const cell = el("button", { className: "cell" }, el("span", { className: "pv r" }), el("span", { className: "pv b" }));
        if (c < size - 1 && hasWall(r, c, r, c + 1)) cell.classList.add("wall-right");
        if (r < size - 1 && hasWall(r, c, r + 1, c)) cell.classList.add("wall-bottom");
        const here = tanksAt[key(r, c)];
        let text = coord(r, c);
        if (here) {
          const mine = here.includes(state.you);
          const tankText = here.length > 1 ? String(here.length) : mine ? "YOU" : (n[here[0]] || "?").slice(0, 2);
          cell.append(el("span", { className: "tank" + (mine ? "" : " enemy") }, tankText));
          text += `: ${here.map((pid) => (pid === state.you ? "your tank" : n[pid])).join(", ")}`;
        }
        cell.append(el("span", { className: "mine", hidden: true }, "✸"));
        cell.dataset.label = text;
        cell.addEventListener("click", (e) => onCellClick(r, c, e));
        cell.addEventListener("mouseenter", () => {
          hover = [r, c];
          if (scanSel) extendScan(scanSel.axis, scanSel.axis === "row" ? r : c);
          updateBoard();
        });
        cell.addEventListener("mousemove", (e) => {
          if (targeting !== "wall" && targeting !== "unwall") return;
          const edge = nearestEdge(r, c, e);
          if (JSON.stringify(edge) === JSON.stringify(hoverEdge)) return;
          hoverEdge = edge;
          updateBoard();
        });
        rowEls.push(cell);
        nodes.push(cell);
      }
      cellEls.push(rowEls);
    }
    board.onmouseleave = () => {
      hover = null;
      hoverEdge = null;
      updateBoard();
    };
    board.replaceChildren(...nodes);
    updateBoard();
  }

  /** Mines to draw: key -> "own" | "enemy" (yours while playing, everyone's at the end). */
  function visibleMines() {
    const mines = new Map();
    if (isPlacing()) {
      placing.mines.forEach(([r, c]) => mines.set(key(r, c), "own"));
    } else if (state.game.mines) {
      state.game.mines.forEach((m) => {
        if (mines.get(key(m.row, m.col)) !== "own") mines.set(key(m.row, m.col), m.owner === state.you ? "own" : "enemy");
      });
    } else {
      (state.private?.mines || []).forEach(([r, c]) => mines.set(key(r, c), "own"));
    }
    return mines;
  }

  /** Update marks and highlights without rebuilding the board. */
  function updateBoard() {
    if (!inGame() || !cellEls.length) return;
    const size = state.game.size;
    const myTurn = isMyTurn();
    const allowed = targeting && myTurn ? allowedCells() : null;
    const mines = visibleMines();
    const n = names();

    const targets = new Set();
    if (myTurn && hover) {
      const hk = key(...hover);
      if (targeting === "spray") {
        const [r, c] = sprayAnchor(hover);
        [[r, c], [r + 1, c], [r, c + 1], [r + 1, c + 1]].forEach(([a, b]) => targets.add(key(a, b)));
      } else if (targeting === "artillery") {
        targets.add(hk);
      } else if (targeting === "blast") {
        const dir = blastDirAt(hk);
        if (dir) blastLines()[dir].forEach((k) => targets.add(k));
      } else if (allowed?.has(hk)) {
        targets.add(hk);
      }
    }

    // Scan area: the chosen range, or the hovered label before anything is chosen.
    const scanning = targeting === "scan" && myTurn;
    let scanArea = null;
    if (scanning) {
      const range = scanRange();
      if (range) scanArea = { axis: scanSel.axis, from: range[0], to: range[1] };
      else if (scanHover) scanArea = { axis: scanHover.axis, from: scanHover.index, to: scanHover.index };
    }
    const inScan = (r, c) => {
      if (!scanArea) return false;
      const i = scanArea.axis === "row" ? r : c;
      return i >= scanArea.from && i <= scanArea.to;
    };
    for (const axis of ["row", "col"]) {
      labelEls[axis].forEach((node, i) => {
        node.classList.toggle("scan-pick", scanning);
        node.classList.toggle("picked", Boolean(scanning && scanSel?.axis === axis && scanRange() && i >= scanRange()[0] && i <= scanRange()[1]));
      });
    }

    // Wall preview on the gap nearest the pointer.
    const walling = (targeting === "wall" || targeting === "unwall") && myTurn;
    let edgeCell = null;
    let edgeClass = null;
    let edgeState = null;
    if (walling && hoverEdge) {
      const [[r1, c1], [r2]] = hoverEdge;
      edgeCell = key(r1, c1);
      edgeClass = r1 === r2 ? "pv-right" : "pv-bottom";
      edgeState = edgeStatus(hoverEdge);
    }

    const placingNow = isPlacing();
    $("board").classList.toggle("targeting", Boolean(targeting) && !scanning);
    $("board").classList.toggle("scanning", scanning);
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const cell = cellEls[r][c];
        const k = key(r, c);
        const mark = marks[k];
        cell.classList.toggle("suspect", mark === "suspect");
        cell.classList.toggle("clear", mark === "clear");
        cell.classList.toggle("preview", inScan(r, c));
        cell.classList.toggle("allowed", Boolean(allowed?.has(k)) && !targets.has(k));
        cell.classList.toggle("target", targets.has(k));
        cell.classList.toggle("blocked", Boolean(allowed) && !allowed.has(k));
        cell.classList.toggle("pending", Boolean(placingNow && placing.tank && placing.tank[0] === r && placing.tank[1] === c));
        const isEdge = edgeCell === k;
        cell.classList.toggle("pv-right", isEdge && edgeClass === "pv-right");
        cell.classList.toggle("pv-bottom", isEdge && edgeClass === "pv-bottom");
        cell.classList.toggle("pv-remove", isEdge && edgeState === "remove");
        cell.classList.toggle("pv-bad", isEdge && edgeState === "bad");

        const mine = mines.get(k);
        const mineEl = cell.querySelector(".mine");
        mineEl.hidden = !mine;
        mineEl.classList.toggle("enemy", mine === "enemy");

        let label = cell.dataset.label;
        if (mine === "own") label += " (your mine)";
        if (mine === "enemy") {
          const owners = state.game.mines.filter((m) => m.row === r && m.col === c).map((m) => n[m.owner]);
          label += ` (mine: ${owners.join(", ")})`;
        }
        if (mark === "suspect") label += " (marked: suspect)";
        if (mark === "clear") label += " (marked: clear)";
        cell.title = label;
        cell.setAttribute("aria-label", label);
      }
    }
  }

  function describeHits(hits, n) {
    if (!hits?.length) return " No hits.";
    return " " + hits.map((h) => {
      const who = h.player === state.you ? "you" : n[h.player];
      if (h.shielded) return `Hit ${who}, but ${who === "you" ? "you were" : `${who} was`} shielded (no damage).`;
      return `Hit ${who} (−${h.damage})${h.destroyed ? `, ${who === "you" ? "you were" : `${who} was`} destroyed` : ""}.`;
    }).join(" ");
  }

  const DIR_NAMES = { up: "up", down: "down", left: "left", right: "right" };

  function renderLog() {
    const n = names();
    const notes = state.private?.notes || {};
    const items = state.game.log.map((entry, index) => {
      const actor = entry.actor === state.you ? "You" : n[entry.actor];
      const note = notes[String(index)];
      const item = el("li");
      const addNote = (text, className = "muted") => item.append(" ", el("span", { className }, text));
      switch (entry.type) {
        case "start":
          item.textContent = "All tanks are hidden and the mines are laid. The battle begins!";
          break;
        case "left":
          item.textContent = `${actor} left the game.`;
          break;
        case "move":
          item.textContent = `${actor} moved (+${entry.cost}).`;
          if (entry.mine) item.textContent += " A mine went off!" + describeHits(entry.hits, n);
          if (note?.mineAt) addNote(`Your mine at ${coord(...note.mineAt)} went off.`, "found");
          break;
        case "scan": {
          const word = entry.axis === "row" ? "row" : "column";
          const name = entry.axis === "row" ? rowName : colName;
          const where = entry.from === entry.to ? `${word} ${name(entry.from)}` : `${word}s ${name(entry.from)} to ${name(entry.to)}`;
          item.textContent = `${actor} scanned ${where} (+${entry.cost}).`;
          if (note && "found" in note) {
            addNote(note.found ? "Someone is there!" : "No one there.", note.found ? "found" : "not-found");
          }
          break;
        }
        case "spray":
          item.textContent = `${actor} sprayed ${coord(entry.row, entry.col)}–${coord(entry.row + 1, entry.col + 1)} (+${entry.cost}).` + describeHits(entry.hits, n);
          break;
        case "artillery":
          item.textContent = `${actor} shelled ${coord(entry.row, entry.col)} with artillery (+${entry.cost}).` + describeHits(entry.hits, n);
          break;
        case "blast":
          item.textContent = `${actor} fired a blast (+${entry.cost}).` +
            (entry.hit ? ` It hit ${coord(...entry.hit)}.` + describeHits(entry.hits, n) : " Miss.");
          if (note?.dir) addNote(`(You fired ${DIR_NAMES[note.dir]}.)`);
          break;
        case "heal":
          item.textContent = `${actor} repaired ${entry.amount} HP (+${entry.cost}).`;
          break;
        case "wall":
        case "unwall": {
          const [a, b] = entry.cells;
          const verb = entry.type === "wall" ? "built a wall" : "removed the wall";
          item.textContent = `${actor} ${verb} between ${coord(...a)} and ${coord(...b)} (+${entry.cost}).`;
          break;
        }
        case "mine":
          item.textContent = `${actor} laid a mine (+${entry.cost}).`;
          if (note?.cell) addNote(`(At ${coord(...note.cell)}.)`);
          break;
        default:
          return null;
      }
      return item;
    }).filter(Boolean);

    if (!items.length) items.push(el("li", { className: "muted" }, "Nothing has happened yet."));
    $("log").replaceChildren(...items.reverse());
  }
})();
