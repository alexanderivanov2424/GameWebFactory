/*
 * Shared lobby UI helpers for game pages. Load after lobby.js.
 * Page styles (buttons, cards, inputs) come from /shared/theme.js.
 * Injects its own styles once (all classes are prefixed "gwf-").
 *
 *   AppLobbyUI.renderPlayers(ulElement, lobby, { afterName(player) })
 *       Fills a list with the lobby's players:
 *       [✓ if ready] name (you) [afterName(player)] [Host] [Offline] ... [Make host (host only)]
 *   AppLobbyUI.renderStart(element, lobby)
 *       Start status: why the game can't start yet, or "waiting for the host". The host
 *       also gets a "Start game" button, enabled once everyone is ready.
 *   AppLobbyUI.renderSpectators(element, state)   "Watching: a, b"
 *   AppLobbyUI.lobbyButtons(lobby, { join, leave, ready, back })   Returns render().
 *       Wires the page's own buttons (any may be omitted): Join (spectators in the lobby),
 *       Leave and Ready/Not ready (players in the lobby; Ready gets class "green"/"red"),
 *       Back to lobby (the host, once the game is finished). Call render() on every state.
 *   AppLobbyUI.settingsForm(element, lobby)       Returns render(). Fills `element` with an
 *       input per host setting from state.settingsSpec (declared in the game's SETTINGS on
 *       the server), plus a note on who can change them. Only the host can edit; changes
 *       are sent after a short pause. Call render() on every lobby render.
 *   AppLobbyUI.connectionText(status, roomId)     Text for AppLobby's onConnection
 *   AppLobbyUI.errorBox(element)                  Returns show(message): auto-hiding error banner
 *   AppLobbyUI.turnAlert(element, { text })       Returns update(turnId). Call it on every render
 *       with an id for the current turn when it's this player's turn (e.g. `${gameNumber}:${step}`),
 *       else null. A new id makes `element` (the board) pulse with a badge (default "Your turn!")
 *       until the player clicks anything; the tab title gets a "▶ Your turn" prefix while it's
 *       their turn.
 */
(() => {
  const STYLE = `
    .gwf-players { list-style: none; margin: 0; padding: 0; }
    .gwf-player { display: flex; align-items: center; gap: 8px; padding: 10px 0; border-bottom: 1px solid #eee; }
    .gwf-player:last-child { border-bottom: none; }
    .gwf-check { width: 20px; flex: none; text-align: center; color: #1a8a4a; font-weight: 700; }
    .gwf-name { overflow-wrap: anywhere; }
    .gwf-you { font-weight: 600; }
    .gwf-tag { font-size: 0.75rem; padding: 2px 8px; border-radius: 999px; background: #eef0ff; color: #4a5cff; flex: none; }
    .gwf-tag.gwf-offline { background: #eee; color: #888; }
    .gwf-spacer { flex: 1; }
    .gwf-make-host, .gwf-make-host:hover:not(:disabled) {
      font: inherit; font-size: 0.8rem; padding: 4px 10px; border: none; border-radius: 6px;
      background: #eef0ff; color: #4a5cff; cursor: pointer;
    }
    .gwf-make-host:hover:not(:disabled) { background: #dfe3ff; }
    .gwf-empty { color: #999; padding: 10px 0; }
    .gwf-start { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 12px 0; color: #666; }
    .gwf-start-btn {
      font: inherit; font-weight: 600; padding: 8px 20px; border: none; border-radius: 6px;
      background: #1a8a4a; color: #fff; cursor: pointer;
    }
    .gwf-start-btn:hover:not(:disabled) { background: #146e3b; }
    .gwf-start-btn:disabled { opacity: 0.45; cursor: default; }
    .gwf-turn-alert { position: relative; animation: gwf-turn-pulse 1.2s ease-in-out infinite; }
    .gwf-turn-alert::before {
      content: attr(data-gwf-alert); position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
      background: #1a8a4a; color: #fff; font-weight: 700; font-size: 0.85rem; white-space: nowrap;
      padding: 3px 12px; border-radius: 999px; z-index: 5; pointer-events: none;
    }
    @keyframes gwf-turn-pulse {
      0%, 100% { box-shadow: 0 0 0 3px rgba(26, 138, 74, 0.9); }
      50% { box-shadow: 0 0 0 9px rgba(26, 138, 74, 0.25); }
    }
    .gwf-settings { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; }
    .gwf-setting { display: flex; align-items: center; gap: 8px; }
    .gwf-settings-note { margin: 10px 0 0; color: #666; font-size: 0.85rem; }
    .gwf-error { background: #fdecec; color: #b4232a; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; }
  `;

  const style = document.createElement("style");
  style.textContent = STYLE;
  document.head.append(style);

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function renderPlayers(list, lobby, { afterName } = {}) {
    const state = lobby.state;
    list.classList.add("gwf-players");
    if (!state.players.length) {
      list.replaceChildren(el("li", "gwf-empty", "No one has joined yet."));
      return;
    }
    const isHost = lobby.isHost();
    list.replaceChildren(
      ...state.players.map((player) => {
        const isMe = player.id === state.you;
        const item = el("li", "gwf-player");
        const check = el("span", "gwf-check", player.ready ? "✓" : "");
        check.title = player.ready ? "Ready" : "Not ready";
        item.append(check, el("span", "gwf-name" + (isMe ? " gwf-you" : ""), player.name + (isMe ? " (you)" : "")));
        const extra = afterName?.(player);
        if (extra) item.append(extra);
        if (player.id === state.hostId) item.append(el("span", "gwf-tag", "Host"));
        if (!player.connected) item.append(el("span", "gwf-tag gwf-offline", "Offline"));
        item.append(el("span", "gwf-spacer"));
        if (isHost && !isMe) {
          const button = el("button", "gwf-make-host", "Make host");
          button.addEventListener("click", () => lobby.makeHost(player.id));
          item.append(button);
        }
        return item;
      })
    );
  }

  function renderStart(element, lobby) {
    const state = lobby.state;
    element.classList.add("gwf-start");
    const blocker = state.startBlocker;
    const children = [];
    if (lobby.isHost()) {
      const button = el("button", "gwf-start-btn", "Start game");
      button.disabled = Boolean(blocker);
      button.addEventListener("click", () => lobby.start());
      children.push(button, el("span", "", blocker || "Everyone's ready."));
    } else if (blocker) {
      children.push(el("span", "", blocker));
    } else {
      const host = state.players.find((p) => p.id === state.hostId);
      children.push(el("span", "", `Everyone's ready. Waiting for ${host ? host.name : "the host"} to start.`));
    }
    element.replaceChildren(...children);
  }

  function renderSpectators(element, state) {
    const names = state.spectators.map((s) => s.name);
    element.textContent = names.length ? `Watching: ${names.join(", ")}` : "";
  }

  function connectionText(status, roomId) {
    if (status === "online") return `Room: ${roomId}`;
    if (status === "replaced") return "This room was opened in another tab. Reload to use it here.";
    return "Disconnected, reconnecting…";
  }

  function errorBox(element) {
    element.classList.add("gwf-error");
    element.setAttribute("role", "alert");
    element.hidden = true;
    let timer;
    return (message) => {
      element.textContent = message;
      element.hidden = false;
      clearTimeout(timer);
      timer = setTimeout(() => (element.hidden = true), 4000);
    };
  }

  function turnAlert(element, { text = "Your turn!" } = {}) {
    const baseTitle = document.title;
    let lastId = null;
    element.dataset.gwfAlert = text;
    // Capture phase, so any click on the page counts, even ones that stop propagation.
    document.addEventListener("pointerdown", () => element.classList.remove("gwf-turn-alert"), true);
    return (turnId) => {
      turnId = turnId ?? null;
      if (turnId !== lastId) element.classList.toggle("gwf-turn-alert", turnId !== null);
      lastId = turnId;
      document.title = turnId !== null ? `▶ Your turn · ${baseTitle}` : baseTitle;
    };
  }

  function lobbyButtons(lobby, { join, leave, ready, back } = {}) {
    join?.addEventListener("click", () => lobby.join());
    leave?.addEventListener("click", () => lobby.leave());
    ready?.addEventListener("click", () => lobby.setReady(!lobby.me()?.ready));
    back?.addEventListener("click", () => lobby.backToLobby());
    return () => {
      const state = lobby.state;
      if (!state) return;
      const me = lobby.me();
      const inLobby = state.phase === "lobby";
      if (join) join.hidden = !inLobby || !me || me.player;
      if (leave) leave.hidden = !inLobby || !me?.player;
      if (ready) {
        ready.hidden = !inLobby || !me?.player;
        ready.textContent = me?.ready ? "Not ready" : "Ready";
        ready.classList.toggle("green", !me?.ready);
        ready.classList.toggle("red", Boolean(me?.ready));
      }
      if (back) back.hidden = !(state.phase === "finished" && lobby.isHost());
    };
  }

  function settingsForm(element, lobby) {
    let builtFor = null;
    let inputs = {};
    let note;
    let timer;

    function send() {
      const values = {};
      for (const [key, input] of Object.entries(inputs)) {
        const value = Number(input.value);
        if (input.value !== "" && Number.isInteger(value)) values[key] = value;
      }
      if (Object.keys(values).length) lobby.updateSettings(values);
    }

    function build(spec) {
      inputs = {};
      const row = el("div", "gwf-settings");
      for (const field of spec) {
        const label = el("label", "gwf-setting", field.label);
        if (field.hint) label.title = field.hint;
        const input = el("input");
        input.type = "number";
        input.step = "1";
        input.addEventListener("input", () => {
          clearTimeout(timer);
          timer = setTimeout(send, 400);
        });
        label.append(input);
        if (field.suffix) label.append(el("span", "", field.suffix));
        inputs[field.key] = input;
        row.append(label);
      }
      note = el("p", "gwf-settings-note");
      element.replaceChildren(row, note);
    }

    return () => {
      const state = lobby.state;
      const spec = state?.settingsSpec || [];
      const signature = JSON.stringify(spec);
      if (signature !== builtFor) {
        build(spec);
        builtFor = signature;
      }
      const isHost = lobby.isHost();
      const bound = (field, name) => (field[name + "From"] ? state.settings[field[name + "From"]] : field[name]);
      for (const field of spec) {
        const input = inputs[field.key];
        input.min = bound(field, "min");
        input.max = bound(field, "max");
        input.disabled = !isHost;
        if (document.activeElement !== input) input.value = state.settings[field.key];
      }
      const host = state.players.find((p) => p.id === state.hostId);
      note.textContent = !spec.length
        ? "This game has no settings."
        : isHost
          ? "You're the host, so you can change these."
          : host ? `Only the host (${host.name}) can change these.` : "Only the host can change these.";
    };
  }

  window.AppLobbyUI = {
    renderPlayers, renderStart, renderSpectators, connectionText, errorBox, turnAlert, lobbyButtons, settingsForm,
  };
})();
