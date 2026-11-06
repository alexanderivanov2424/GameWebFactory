(() => {
  const { $, el, listNames } = AppDom;
  let state = null;

  const lobby = AppLobby.connect("peruvian-silver", {
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

  // --- Lobby controls ------------------------------------------------------------

  const renderButtons = AppLobbyUI.lobbyButtons(lobby, {
    join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back"),
  });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);

  // --- Playing cards -------------------------------------------------------------

  let selected = null; // index into your hand
  let selectedStep = null; // the reveal the selection belongs to

  // Hand card types an explorer may play: sent by the server (EXPLORER_PLAYS in server.py),
  // so the two can't drift apart (that's how Backstab ended up unplayable).
  const explorerPlays = () => new Set(state?.game?.explorerPlays || []);

  const FORK_SIDES = { stay: "left", leave: "right" }; // at a fork, Stay goes left and Leave goes right
  let returnPath = null; // path picked for Seconds when several have explorers

  function atFork() {
    if (!state || state.phase !== "playing" || state.game.stage !== "fork") return false;
    const play = state.game.plays[state.you];
    return Boolean(play) && !play.chosen;
  }

  // Open paths (not forked off), even empty ones: where Seconds can take you.
  function joinablePaths(game) {
    return game.paths.filter((p) => !p.closed).map((p) => p.id);
  }

  // Can you play a card this turn? Explorers must; players at camp holding Seconds may.
  function canPlay() {
    if (atFork()) return true;
    if (!state || state.phase !== "playing" || state.game.stage !== "choosing") return false;
    if (state.private?.played) return false;
    const seat = state.game.seats[state.you];
    if (seat?.status === "exploring") return true;
    return seat?.status === "camp" && (state.private?.hand || []).some((c) => state.game.handCards[c]?.type === "return");
  }

  function cardPlayable(cardId) {
    if (!canPlay()) return false;
    const type = state.game.handCards[cardId]?.type;
    if (atFork()) return type in FORK_SIDES;
    return state.game.seats[state.you].status === "exploring" ? explorerPlays().has(type) : type === "return";
  }

  // A Crystal Ball is used any time during the game, not played as a turn.
  function canPeek(cardId) {
    if (!state || state.phase !== "playing" || state.game.handCards[cardId]?.type !== "peek") return false;
    return !["over", "marking", "gem"].includes(state.game.stage) && state.game.deckCount > 0;
  }

  function cardUsable(cardId) {
    return canPeek(cardId) || cardPlayable(cardId);
  }

  function select(index) {
    const hand = state?.private?.hand || [];
    if (index < 0 || index >= hand.length || !cardUsable(hand[index])) return;
    selected = index;
    selectedStep = state.game.step;
    render();
  }

  function needsReturnPath(cardId) {
    return state.game.handCards[cardId]?.type === "return" && joinablePaths(state.game).length > 1;
  }

  function play(index = selected) {
    const hand = state?.private?.hand || [];
    if (index !== null && index < hand.length && canPeek(hand[index])) {
      lobby.sendGame({ action: "peek" });
      selected = null;
      return;
    }
    if (index === null || index >= hand.length || !cardPlayable(hand[index])) return;
    if (needsReturnPath(hand[index])) {
      if (!joinablePaths(state.game).includes(returnPath)) {
        selected = index;
        selectedStep = state.game.step;
        render();
        showError("Pick which path to join first.");
        return;
      }
      lobby.sendGame({ action: "play", card: hand[index], path: returnPath });
      return;
    }
    lobby.sendGame({ action: "play", card: hand[index] });
  }

  function pickReturnPath(pathId) {
    returnPath = pathId;
    render();
  }

  // PLAY plays the selected card; while you're deciding on a charm it's PASS instead.
  $("play").addEventListener("click", () => (canDecideCharm() ? decideCharm(false) : play()));

  // --- Marking: put one of this round's emoji on the back of one of your 3 cards ------

  let draftSelected = null; // index into your offers
  let markEmoji = null; // the emoji you picked
  let draftKey = null; // which marking round the selection belongs to

  function canDraft() {
    if (!state || state.phase !== "playing" || state.game.stage !== "marking") return false;
    return (state.private?.offers || []).length > 0 && !state.private.picked;
  }

  function markKey() {
    return `${state.gameNumber}:${state.game.expedition}`;
  }

  function pickEmoji(emoji) {
    if (!canDraft()) return;
    if (draftKey !== markKey()) draftSelected = null;
    markEmoji = emoji;
    draftKey = markKey();
    render();
  }

  function selectOffer(index) {
    const offers = state?.private?.offers || [];
    if (!canDraft() || index < 0 || index >= offers.length) return;
    if (draftKey !== markKey()) markEmoji = null;
    draftSelected = index;
    draftKey = markKey();
    render();
  }

  function draft(index = draftSelected) {
    const offers = state?.private?.offers || [];
    if (!canDraft() || index === null || index >= offers.length) return;
    if (!markEmoji || !state.game.markEmojis.includes(markEmoji)) {
      showError("Pick a mark first.");
      return;
    }
    lobby.sendGame({ action: "mark", uid: offers[index].uid, emoji: markEmoji });
  }

  // --- Gem auction: one bid each, in turn -----------------------------------------

  function myBidTurn() {
    if (!state || state.phase !== "playing" || state.game.stage !== "auction") return false;
    const a = state.game.auction;
    return Boolean(a) && a.order[a.turn] === state.you;
  }

  function bid(amount) {
    if (myBidTurn()) lobby.sendGame({ action: "bid", amount });
  }

  $("bid-btn").addEventListener("click", () => {
    const amount = parseInt($("bid-amount").value, 10);
    if (!Number.isInteger(amount) || amount <= 0) {
      showError("Enter a bid, or PASS.");
      return;
    }
    bid(amount);
  });
  $("pass-btn").addEventListener("click", () => bid(0));
  $("bid-amount").addEventListener("keydown", (event) => {
    if (event.key === "Enter") $("bid-btn").click();
  });

  // --- Gems: the holder uses their gem at the end of the round -----------------------

  let gemPicks = []; // Red Gem: indexes of chosen cards
  let gemEmoji = null; // Blue Gem: chosen mark
  let gemKey = null;

  function myGemTurn() {
    return Boolean(state && state.phase === "playing" && state.game.stage === "gem" && state.game.gemTurn?.player === state.you);
  }

  $("gem-btn").addEventListener("click", () => {
    if (!myGemTurn()) return;
    if (state.game.gemTurn.color === "red") {
      const options = state.private?.gemOptions || [];
      lobby.sendGame({ action: "gem", cards: gemPicks.map((i) => options[i]) });
    } else if (gemEmoji) {
      lobby.sendGame({ action: "gem", emoji: gemEmoji });
    }
  });

  // --- Robbery: the richest player(s) choose a relic to lose ------------------------

  function canChooseLoss() {
    if (!state || state.phase !== "playing" || state.game.stage !== "robbery") return false;
    const play = state.game.plays[state.you];
    return Boolean(play) && !play.chosen;
  }

  function chooseLoss(kind, card) {
    if (canChooseLoss()) lobby.sendGame({ action: "rob", kind, card });
  }

  $("draft-btn").addEventListener("click", () => draft());

  // --- Charms: a hazard struck and you hold its charm ------------------------------

  function canDecideCharm() {
    if (!state || state.phase !== "playing" || state.game.stage !== "charm") return false;
    const play = state.game.plays[state.you];
    return Boolean(play) && !play.chosen;
  }

  function decideCharm(use) {
    if (canDecideCharm()) lobby.sendGame({ action: "charm", use });
  }


  // --- Fountain: move silver between your backpack and your fountain pool ----------

  let fountainKey = null; // which fountain the slider belongs to

  function canUseFountain() {
    if (!state || state.phase !== "playing" || state.game.stage !== "fountain") return false;
    const play = state.game.plays[state.you];
    return Boolean(play) && !play.chosen;
  }

  function fountainAmount() {
    return parseInt($("fountain-range").value, 10) || 0;
  }

  $("fountain-range").addEventListener("input", () => render());
  $("fountain-none").addEventListener("click", () => { $("fountain-range").value = 0; render(); });
  $("fountain-all-in").addEventListener("click", () => { $("fountain-range").value = $("fountain-range").max; render(); });
  $("fountain-all-out").addEventListener("click", () => { $("fountain-range").value = $("fountain-range").min; render(); });
  $("fountain-btn").addEventListener("click", () => {
    if (canUseFountain()) lobby.sendGame({ action: "fountain", amount: fountainAmount() });
  });

  // Keys: 1-9 pick a card, Enter or Space plays (or adds) it. Ignored while typing (e.g. in chat).
  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target;
    if (target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(target.tagName))) return;
    const drafting = canDraft();
    if (/^[1-9]$/.test(event.key)) {
      if (drafting) selectOffer(Number(event.key) - 1);
      else select(Number(event.key) - 1);
    } else if (event.key === "Enter" || event.key === " ") {
      if (drafting && draftSelected !== null) {
        event.preventDefault();
        draft();
      } else if (!drafting && selected !== null && canPlay()) {
        event.preventDefault();
        play();
      }
    }
  });

  // --- Animation bookkeeping ------------------------------------------------------
  // Animate only what's new since the last render, never on the first render (a reload).

  let firstGameRender = true;
  const seenCards = new Set(); // "game:step" of path cards already shown
  const seenFaceDown = new Set(); // "game:step:pid" face-down cards already shown
  const seenFaceUp = new Set(); // "game:step:pid" revealed cards already shown
  let lastPacks = {};

  function firstTime(set, key) {
    if (set.has(key)) return false;
    set.add(key);
    return !firstGameRender;
  }

  // --- Rendering -----------------------------------------------------------------

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    renderButtons();
    if (inLobby) {
      firstGameRender = true;
      $("hand-bar").hidden = true;
      $("draft").hidden = true;
      $("charm-prompt").hidden = true;
      $("fountain-prompt").hidden = true;
      $("rob-prompt").hidden = true;
      $("auction").hidden = true;
      $("gem-prompt").hidden = true;
      $("main").classList.remove("with-hand");
      renderLobby();
    } else {
      renderGame();
      firstGameRender = false;
    }
  }

  function renderLobby() {
    AppLobbyUI.renderPlayers($("players"), lobby);
    AppLobbyUI.renderStart($("start"), lobby);
    AppLobbyUI.renderSpectators($("spectators"), state);
    renderSettings();
  }

  function renderGame() {
    const game = state.game;
    const name = (pid) => {
      const seat = game.seats[pid];
      return seat ? seat.name + (pid === state.you ? " (you)" : "") : "Someone";
    };

    renderStatus(game, name);
    renderSeats(game);
    renderPath(game);
    renderBanner(game, name);
    renderLog(game, name);
    renderHand(game);
    renderDraft(game);
    renderCharmPrompt(game, name);
    renderFountainPrompt(game);
    renderRobPrompt(game);
    renderAuction(game, name);
    renderGemPrompt(game, name);
    renderVision(game);
    renderMyMarks(game);

    const packs = {};
    for (const [pid, seat] of Object.entries(game.seats)) packs[pid] = seat.backpack;
    lastPacks = packs;
  }

  function renderStatus(game, name) {
    const finished = state.phase === "finished";
    const isHost = lobby.isHost();

    $("expedition-chip").textContent = `⛏️ Expedition ${game.expedition} of ${game.expeditions}`;
    const plural = (n) => `${n} card${n === 1 ? "" : "s"}`;
    $("deck-chip").textContent = game.stage === "marking" || game.stage === "over" || finished
      ? `🂠 ${plural(game.deckSize)} in the deck`
      : `🂠 ${game.deckCount} of ${plural(game.deckSize)} left`;

    // Final result.
    $("result").hidden = !finished;
    if (finished) {
      const result = state.result || {};
      const winners = result.winners || [];
      const scores = result.scores || {};
      const chests = result.chests || {};
      const idols = result.idols || {};
      const bonus = result.bonus || {};
      const best = winners.length ? scores[winners[0]] : 0;
      const youWon = winners.includes(state.you);
      const headline = !winners.length
        ? "The game is over."
        : winners.length === 1
          ? `🏆 ${youWon ? "You win" : `${game.seats[winners[0]].name} wins`} with ${best} points!`
          : `🏆 A tie at ${best} points between ${listNames(winners.map(name))}!`;
      const standings = Object.keys(scores)
        .sort((a, b) => scores[b] - scores[a])
        .map((pid) => `${name(pid)}: ${scores[pid]}` + (idols[pid] || bonus[pid]
          ? ` (🧰 ${chests[pid]}${idols[pid] ? ` + 🗿 ${idols[pid]}` : ""}${bonus[pid] ? ` + ${bonus[pid]} relic bonus` : ""})`
          : ""))
        .join(" · ");
      $("result").replaceChildren(
        el("div", {}, headline),
        el("div", { className: "standings muted" }, standings),
        isHost ? "" : el("div", { className: "standings muted" }, "Waiting for the host to return to the lobby.")
      );
    }

    // What's happening / what you should do.
    const mySeat = game.seats[state.you];
    const pending = Object.values(game.plays);
    const played = pending.filter((p) => p.chosen).length;
    const progress = `${played}/${pending.length} decided`;
    let message = "";
    if (finished) {
      message = "Final standings";
    } else if (game.stage === "choosing") {
      if (canPlay() && mySeat?.status === "camp") message = `You can play Seconds to go back into the mine. (${progress})`;
      else if (canPlay()) message = "Stay or leave? Pick a card and press PLAY.";
      else if (mySeat?.status === "exploring") message = `Waiting for the others… (${progress})`;
      else if (mySeat?.status === "camp") message = `You're safe at camp. Explorers are deciding… (${progress})`;
      else if (mySeat?.status === "busted") message = `Explorers are deciding… (${progress})`;
      else message = `Explorers are deciding… (${progress})`;
    } else if (game.stage === "reveal") {
      message = "Cards revealed!";
    } else if (game.stage === "charm") {
      const hazard = game.deckCards[game.strike?.card];
      message = canDecideCharm()
        ? `Another ${hazard?.name || "hazard"}! Use your charm?`
        : `Another ${hazard?.name || "hazard"}! Charm holders are deciding… (${progress})`;
    } else if (game.stage === "saved") {
      message = "Charms used! The survivors carry on.";
    } else if (game.stage === "fork") {
      message = atFork()
        ? "The path forks! Play Go Left or Go Right."
        : `Explorers at the fork are picking a path… (${progress})`;
    } else if (game.stage === "forked") {
      message = "The explorers split up!";
    } else if (game.stage === "fountain") {
      message = canUseFountain()
        ? "A fountain! Move silver between your backpack and your fountain pool."
        : `Explorers are at the fountain… (${progress})`;
    } else if (game.stage === "over") {
      message = game.expedition < game.expeditions ? "Back to camp…" : "";
    } else if (game.stage === "marking") {
      message = canDraft()
        ? "Mark the back of a card."
        : `Players are marking cards… (${progress})`;
    } else if (game.stage === "auction" && game.auction) {
      const bidder = game.auction.order[game.auction.turn];
      message = myBidTurn() ? "Your turn to bid for the gem!" : `Gem auction: ${name(bidder)} is bidding…`;
    } else if (game.stage === "gem" && game.gemTurn) {
      const gem = game.deckCards[game.gemTurn.gem];
      message = myGemTurn() ? `Use your ${gem?.name || "gem"}.` : `${name(game.gemTurn.player)} is using the ${gem?.name || "gem"}…`;
    } else if (game.stage === "robbery") {
      message = canChooseLoss()
        ? "Robbery! You have the most silver. Choose a relic to lose."
        : `Robbery! ${listNames((game.robbery?.choosers || []).map(name))} must give up a relic…`;
    }
    $("message").textContent = message;
  }

  const STATUS_TEXT = {
    exploring: "In the mine",
    camp: "Safe at camp",
    busted: "Lost their backpack",
    gone: "Left the game",
  };

  function renderSeats(game) {
    const rows = game.order.map((pid) => {
      const seat = game.seats[pid];
      const isMe = pid === state.you;
      const play = game.plays[pid];

      let status = STATUS_TEXT[seat.status] || "";
      if (seat.status === "exploring" && game.stage === "choosing") {
        status = play?.chosen ? "Played a card" : "Deciding…";
      } else if (game.stage === "marking" && play) {
        status = play.chosen ? "Marked a card" : "Marking a card…";
      } else if (game.stage === "robbery" && play) {
        status = play.chosen ? "Chose what to lose" : "Being robbed…";
      } else if (game.stage === "charm" && play) {
        status = play.chosen ? "Decided" : "Deciding on a charm…";
      } else if (game.stage === "fountain" && play) {
        status = play.chosen ? "Done at the fountain" : "At the fountain…";
      } else if (game.stage === "fork" && play) {
        status = play.chosen ? "Picked a path" : "Picking a path…";
      }
      if (game.paths.length > 1 && seat.status === "exploring") status += ` · ${pathLabel(game, seat.path)}`;

      const main = el(
        "div",
        { className: "seat-main" },
        el("div", { className: "seat-name", title: seat.name }, seat.name + (isMe ? " (you)" : "")),
        el("div", { className: "seat-status" }, status),
        el("div", { className: "seat-chest", title: "Chest: banked silver. Safe from hazards; only spent on gem bids." }, `🧰 ${seat.chest}`)
      );
      const relicChips = [
        ...(seat.charms || []).map((charmId) => {
          const charm = game.deckCards[charmId];
          const hazard = game.deckCards[charm?.protects];
          return el("span", { className: "charm-chip", title: charm?.name || charmId }, `🧿 ${hazard?.icon || ""} ${hazard?.name || ""}`);
        }),
        ...(seat.idols || []).map((idolId) => {
          const idol = game.deckCards[idolId];
          return el("span", { className: "idol-chip", title: `${idol?.name || idolId}: worth ${idol?.value ?? "?"} at the end` }, `${idol?.icon || "🗿"} ${idol?.value ?? "?"}`);
        }),
        ...(seat.relics || []).map((relicId) => {
          const relic = game.deckCards[relicId];
          return el("span", { className: "relic-chip", title: relic?.text || relicId }, `${relic?.icon || ""} ${relic?.name || relicId}`);
        }),
        ...(seat.gems || []).map((gemId) => {
          const gem = game.deckCards[gemId];
          return el("span", { className: "gem-chip", title: gem?.text || gemId }, `${gem?.icon || "💎"} ${gem?.name || gemId}`);
        }),
        ...(seat.fountain ? [el("span", { className: "fountain-chip", title: "Fountain pool: doubles at every fountain while this player is still exploring" }, `⛲ ${seat.fountain}`)] : []),
      ];
      if (relicChips.length) main.append(el("div", { className: "seat-charms" }, ...relicChips));

      const amount = el("div", { className: "amount" }, String(seat.backpack));
      if (!firstGameRender && seat.backpack > (lastPacks[pid] ?? seat.backpack)) amount.classList.add("bump");
      const pack = el(
        "div",
        { className: "seat-pack" + (seat.backpack ? "" : " empty"), title: "Backpack: silver carried this expedition. Leave to bank it." },
        el("div", { className: "label" }, "🎒 Backpack"),
        amount
      );

      return el("div", { className: `seat ${seat.status}${isMe ? " me" : ""}` }, main, pack, renderSlot(game, pid, play));
    });
    $("seats").replaceChildren(...rows);
  }

  // The card a player played: empty, face-down, or flipping face-up at the reveal.
  function renderSlot(game, pid, play) {
    const charmStage = game.stage === "charm" || game.stage === "saved";
    const forkStage = game.stage === "fork" || game.stage === "forked";
    const round = game.stage === "marking" ? `mark${game.expedition}`
      : game.stage === "robbery" ? `rob${game.step}`
      : charmStage ? `charm${game.step}`
      : game.stage === "fountain" ? `fountain${game.step}`
      : forkStage ? `fork${game.step}` : game.step;
    const key = `${state.gameNumber}:${round}:${pid}`;
    if (!play?.chosen) {
      const waiting = (game.seats[pid].status === "exploring" && game.stage === "choosing") ||
        (["marking", "charm", "fountain", "fork", "robbery"].includes(game.stage) && play);
      return el("div", { className: "slot" + (waiting ? " empty" : "") });
    }
    const slot = el("div", { className: "slot" });
    const flip = el("div", { className: "flip" });
    const back = el("div", { className: "face back" }, "⛏️");
    flip.append(back);
    slot.append(flip);

    const revealedCard = play.choice;
    if (charmStage && revealedCard !== null && revealedCard !== undefined) {
      const used = revealedCard === true;
      flip.append(el("div", { className: `face front ${used ? "charm-used" : "charm-kept"}` },
        el("span", { className: "icon" }, used ? "🧿" : "✋"), used ? "Charm!" : "No charm"));
      slot.title = used ? "Used a charm" : "Kept their charm";
      seenFaceDown.add(key);
      if (firstTime(seenFaceUp, key)) requestAnimationFrame(() => requestAnimationFrame(() => flip.classList.add("up")));
      else flip.classList.add("up");
      return slot;
    }
    if (forkStage && (revealedCard === "left" || revealedCard === "right")) {
      const left = revealedCard === "left";
      flip.append(el("div", { className: `face front ${left ? "stay" : "leave"}` },
        el("span", { className: "icon" }, left ? "⬅️" : "➡️"), left ? "Left" : "Right"));
      slot.title = left ? "Took the left path" : "Took the right path";
      seenFaceDown.add(key);
      if (firstTime(seenFaceUp, key)) requestAnimationFrame(() => requestAnimationFrame(() => flip.classList.add("up")));
      else flip.classList.add("up");
      return slot;
    }
    const myCard = pid === state.you ? state.private?.played : null;
    const myPick = pid === state.you ? state.private?.picked : null;
    if (myCard) slot.title = `You played ${game.handCards[myCard]?.name || myCard}`;
    if (myPick) slot.title = `You marked a card with ${myPick.emoji}`;

    if (revealedCard) {
      const card = game.handCards[revealedCard] || { name: revealedCard, type: "", icon: "" };
      flip.append(el("div", { className: `face front ${card.type}` }, el("span", { className: "icon" }, card.icon || "🂠"), card.name));
      slot.title = card.name;
      seenFaceDown.add(key);
      if (firstTime(seenFaceUp, key)) {
        // Start face-down, then flip once it's in the page.
        requestAnimationFrame(() => requestAnimationFrame(() => flip.classList.add("up")));
      } else {
        flip.classList.add("up");
      }
    } else if (firstTime(seenFaceDown, key)) {
      slot.classList.add("drop-in");
    }
    return slot;
  }

  // A deck card (treasure, hazard, ...) as shown in the mine and in the draft picker.
  // Border categories: treasure, hazard, idol (anything a lone leaver picks up), event (the rest).
  function category(type) {
    if (type === "treasure") return "treasure";
    if (type === "hazard" || type === "death") return "hazard";
    if (type === "charm" || type === "idol" || type === "relic") return "idol";
    if (type === "gem") return "gem";
    return "event";
  }

  // A short label at the bottom of a card: a number or a couple of words. Rules text lives in
  // the card's "text" (hover, and in the marking view).
  function cardLabel(game, info, { fatal, inMine }) {
    switch (info.type) {
      case "treasure":
      case "idol":
        return String(info.value);
      case "hazard":
        return fatal ? "Strikes!" : inMine ? "Twice = strike" : "Hazard";
      case "charm": {
        const hazard = game.deckCards[info.protects];
        return `🛡️ ${hazard?.icon || ""}`;
      }
      case "relic": {
        const gives = game.handCards[info.gives];
        return `→ ${gives?.icon || ""} card`;
      }
      case "pot":
        return `+${info.growth}/turn`;
      case "death":
        return "Ends expedition";
      case "gem":
        return "Auction";
      default:
        return "";
    }
  }

  function deckCard(game, cardId, { fatal = false, inMine = true, flavor = false } = {}) {
    const info = game.deckCards[cardId] || { name: cardId, type: "", icon: "" };
    const card = el(
      "div",
      { className: `card ${info.type} cat-${category(info.type)}`, title: info.text || info.name },
      el("div", { className: "icon" }, info.icon || "🂠"),
      el("div", { className: "name" }, info.name)
    );
    if (info.type === "hazard" && inMine) card.classList.add(fatal ? "fatal" : "warn");
    const numeric = info.type === "treasure" || info.type === "idol";
    if (flavor && info.text) card.append(el("div", { className: "flavor" }, info.text));
    const label = cardLabel(game, info, { fatal, inMine });
    if (label && (numeric || !(flavor && info.text))) card.append(el("div", { className: "value" }, label));
    return card;
  }

  // Players explore along paths: the main path, then left/right paths after each Fork.
  function pathLabel(game, id) {
    const sides = [];
    let path = game.paths[id];
    while (path && path.parent !== null && path.parent !== undefined) {
      sides.unshift(path.side === "left" ? "Left" : "Right");
      path = game.paths[path.parent];
    }
    return sides.length ? `${sides.join(" → ")} path` : "Main path";
  }

  // Paths in tree order: each path, then its left and right branches.
  function pathOrder(game) {
    const order = [];
    const visit = (path) => {
      order.push(path);
      game.paths.filter((p) => p.parent === path.id).sort((a, b) => (a.side === "left" ? -1 : 1)).forEach(visit);
    };
    game.paths.filter((p) => p.parent === null || p.parent === undefined).forEach(visit);
    return order;
  }

  function deckPile(game) {
    const count = game.deckCount;
    const pile = el("div", { className: "deck-pile" + (count ? "" : " empty"), title: count ? `${count} cards left in the deck` : "The deck is empty" });
    if (count) {
      if (count > 2) pile.append(el("div", { className: `card-back under2 back-default` }));
      if (count > 1) pile.append(el("div", { className: `card-back under back-default` }));
      const top = game.deckTop || { back: "default", marks: [] };
      const topCard = el("div", { className: `card-back back-${top.back}` }, "⛏️");
      if (top.blackSquare) topCard.append(el("div", { className: "black-square", title: "A black square: Death or Blessing" }));
      if (top.marks?.length) topCard.append(el("div", { className: "top-marks", title: "Marks players put on this card" }, top.marks.join("")));
      pile.append(topCard);
    } else {
      pile.append(el("div", { className: "card-back" }, "Empty"));
    }
    pile.append(el("div", { className: "count" }, count ? `${count} left` : ""));
    return pile;
  }

  function renderPath(game) {
    const mySeat = game.seats[state.you];
    const several = game.paths.length > 1;
    const picking = canPlay() && mySeat?.status === "camp" && selected !== null &&
      needsReturnPath((state.private?.hand || [])[selected]);
    const joinable = joinablePaths(game);
    const rows = pathOrder(game).map((path) => {
      const isMine = mySeat?.status === "exploring" && mySeat.path === path.id;
      const row = el("div", { className: "path-row" + (path.closed ? " closed" : "") + (isMine && several ? " mine" : "") });
      if (several) {
        const explorers = Object.entries(game.seats)
          .filter(([, s]) => s.status === "exploring" && s.path === path.id)
          .map(([pid, s]) => s.name + (pid === state.you ? " (you)" : ""));
        row.append(el("div", { className: "path-head" },
          el("b", {}, pathLabel(game, path.id)),
          path.closed ? " · forked, left behind" : explorers.length ? ` · ${explorers.join(", ")}` : " · nobody here"));
      }
      if (picking && joinable.includes(path.id)) {
        row.classList.add("pickable");
        if (returnPath === path.id) row.classList.add("picked");
        row.title = "Join this path with Seconds";
        row.addEventListener("click", () => pickReturnPath(path.id));
      }
      row.append(el("div", { className: "path-cards" }, ...pathCards(game, path)));
      return row;
    });
    $("path").replaceChildren(deckPile(game), el("div", { className: "paths" }, ...rows));

    const myPathCards = game.paths[mySeat?.status === "exploring" ? mySeat.path : 0]?.cards || [];
    const left = myPathCards.reduce((sum, entry) => sum + entry.left, 0);
    $("mine-note").textContent = left ? `${left} silver left on ${several ? "your path" : "the cards"} for whoever leaves` : "";
  }

  function pathCards(game, path) {
    const fatal = game.ending?.reason === "bust" ? game.ending.card : null;
    return path.cards.map((entry) => {
      const acting = entry.as || entry.card;
      const struck = game.strike?.card === acting && game.stage !== "charm" ? game.strike : null;
      const card = deckCard(game, acting, { fatal: acting === fatal || game.stage === "charm" && game.strike?.card === acting });
      if (entry.as) {
        card.append(el("div", { className: "mirror-tag", title: "A Mirror copying this card" }, "🪞 Mirror"));
      }
      if (entry.marks?.length) {
        card.append(el("div", { className: "marks", title: "Marks on this card's back" }, entry.marks.join("")));
      }
      if (struck && struck.users?.length) card.classList.replace("warn", "saved");
      if (entry.taken) {
        card.classList.add("taken");
        const taker = game.seats[entry.taken];
        card.append(el("div", { className: "taken-by" }, `Taken by ${taker ? taker.name : "someone"}`));
      }
      if (entry.left > 0) {
        card.append(el("div", { className: "left", title: "Silver left on this card. Players who leave split it." }, `+${entry.left}`));
      }
      if (firstTime(seenCards, `${state.gameNumber}:${entry.step}`)) {
        card.classList.add(acting === fatal ? "shake" : "deal");
      }
      return card;
    });
  }

  // What just happened, under the cards.
  function renderBanner(game, name) {
    const banner = $("banner");
    let text = "";
    let tone = "";
    const last = game.log[game.log.length - 1];
    if (game.stage === "reveal" && last?.type === "reveal") {
      text = revealText(last, name, game) || "Everyone stays in the mine.";
      tone = last.groups.length || last.returned.length ? "good" : "";
    } else if (game.stage === "robbery" && game.robbery) {
      text = `🦹 Robbery! ${listNames(game.robbery.choosers.map(name))} (most silver in the chest) must give up a relic.`;
      tone = "bad";
    } else if (game.stage === "fork") {
      text = "🔱 The path forks! Its cards are discarded (except the Fork and hazards), with any silver on them. Pick a side: Go Left or Go Right.";
    } else if (game.stage === "forked" && last?.type === "fork-choice") {
      text = forkChoiceText(last, name);
      tone = "good";
    } else if (game.stage === "charm" && game.strike) {
      const hazard = game.deckCards[game.strike.card];
      text = `${hazard?.icon || ""} Another ${hazard?.name || "hazard"}! ${listNames(game.strike.holders.map(name))} ` +
        `${game.strike.holders.length === 1 ? "holds" : "hold"} its charm and ${game.strike.holders.length === 1 ? "is" : "are"} deciding whether to use it.`;
      tone = "bad";
    } else if (game.stage === "saved" && last?.type === "saved") {
      text = savedText(last, name, game);
      tone = "good";
    } else if (game.stage === "over" && game.ending) {
      const ending = game.ending;
      if (ending.reason === "death") {
        const losers = Object.keys(ending.lost || {});
        text = "☠️ Death! The expedition ends. " + (losers.length ? `${listNames(losers.map(name))} lost everything in their backpack.` : "Nobody was inside.");
        tone = "bad";
      } else if (ending.reason === "bust") {
        const card = game.deckCards[ending.card];
        const losers = Object.keys(ending.lost || {});
        text = `${card?.icon || ""} Another ${card?.name || "hazard"}! ` + guidedText(ending, name) +
          (losers.length ? `${listNames(losers.map(name))} lost everything in their backpack. ` : "") +
          (ending.removed ? `One ${card?.name || "hazard"} card is removed from the deck.` : "");
        tone = "bad";
      } else if (ending.reason === "empty") {
        text = "The mine is picked clean. Everyone still inside returned safely.";
        tone = "good";
      } else {
        text = "Everyone is back at camp.";
        tone = "good";
      }
    }
    banner.hidden = !text;
    banner.textContent = text;
    banner.className = tone;
  }

  function savedText(entry, name, game) {
    const hazard = game.deckCards[entry.card];
    const losers = Object.entries(entry.lost || {}).map(([pid, amount]) => `${name(pid)} lost ${amount}`);
    return `${hazard?.icon || ""} Another ${hazard?.name || "hazard"}! ${listNames(entry.users.map(name))} ` +
      `used ${entry.users.length === 1 ? "a charm" : "charms"} and ${entry.users.length === 1 ? "keeps" : "keep"} exploring. ` +
      guidedText(entry, name) +
      (losers.length ? `${losers.join(", ")}. ` : "") +
      (entry.removed ? `One ${hazard?.name || "hazard"} card is removed from the deck.` : "");
  }

  function guidedText(entry, name) {
    const guided = Object.entries(entry.guided || {});
    if (!guided.length) return "";
    return guided.map(([pid, amount]) => `${name(pid)}'s Guide Dog led them back to camp with ${amount} silver.`).join(" ") + " ";
  }

  // A group that left together (Flee, Leave, or everyone when the deck ran out).
  function groupText(group, name, game, verb) {
    const banked = group.players.map((pid) => `${name(pid)} banked ${group.banked[pid]}`);
    let text = `${listNames(group.players.map(name))} ${verb}` +
      (group.share ? `, taking ${group.share} each from the cards` : "") + `. ${banked.join(", ")}.`;
    if (group.relics?.length) {
      const names = group.relics.map((c) => game.deckCards[c]?.name || c);
      text += ` ${name(group.players[0])} was alone and took the ${listNames(names)}!`;
    }
    return text;
  }

  function revealText(entry, name, game) {
    const parts = [];
    for (const group of entry.groups || []) {
      if (group.type === "backstab") {
        const robbedEntries = Object.entries(group.robbed || {});
        const banked = group.players.map((pid) => `${name(pid)} banked ${group.banked[pid]}`);
        const victims = robbedEntries.length === 1
          ? `${name(robbedEntries[0][0])} in the back, taking ${robbedEntries[0][1]}!`
          : `${listNames(robbedEntries.map(([pid, amount]) => `${name(pid)} (${amount})`))} in the back!`;
        parts.push(`🗡️ ${listNames(group.players.map(name))} stabbed ${victims} ${banked.join(", ")}.`);
        continue;
      }
      parts.push(groupText(group, name, game, group.type === "flee" ? "fled first" : "left"));
    }
    for (const [pid, amount] of Object.entries(entry.stash || {})) {
      parts.push(`${name(pid)} stashed ${amount} in their chest and keeps exploring.`);
    }
    if (entry.guard?.length) {
      parts.push(`${listNames(entry.guard.map(name))} brought a Guide Dog.`);
    }
    if (entry.stay?.length) {
      parts.push(`${listNames(entry.stay.map(name))} ${entry.stay.length === 1 ? "stays" : "stay"} in the mine.`);
    }
    if (entry.returned?.length) {
      const where = (pid) => game.paths.length > 1 && entry.paths?.[pid] !== undefined ? ` (${pathLabel(game, entry.paths[pid]).toLowerCase()})` : "";
      parts.push(`${listNames(entry.returned.map((pid) => name(pid) + where(pid)))} went back into the mine!`);
    }
    return parts.join(" ");
  }

  function forkChoiceText(entry, name) {
    const left = Object.keys(entry.sides || {}).filter((pid) => entry.sides[pid] === "left");
    const right = Object.keys(entry.sides || {}).filter((pid) => entry.sides[pid] === "right");
    const parts = [];
    if (left.length) parts.push(`${listNames(left.map(name))} went left`);
    if (right.length) parts.push(`${listNames(right.map(name))} went right`);
    return `🔱 ${parts.join(", ")}.`;
  }

  function mirrorPrefix(entry) {
    return entry.mirror ? "🪞 Mirror copy: " : "";
  }

  function renderLog(game, name) {
    const items = [];
    for (const entry of game.log) {
      const card = game.deckCards[entry.card];
      let text = "";
      let className = "";
      switch (entry.type) {
        case "expedition":
          text = `Expedition ${entry.number} of ${game.expeditions}`;
          className = "heading";
          break;
        case "treasure":
          text = mirrorPrefix(entry) + `${card?.icon || ""} ${card?.name || "Treasure"} (${card?.value ?? "?"}): ` +
            (entry.share
              ? `${entry.share} each` +
                (entry.gremlins ? `, ${entry.share} to ${entry.gremlins === 1 ? "the Gremlin" : `each of ${entry.gremlins} Gremlins`}` : "") +
                `, ${entry.left || 0} left on the card.`
              : `${entry.left || 0} stays on the card.`);
          break;
        case "hazard":
          text = mirrorPrefix(entry) + `${card?.icon || ""} ${card?.name || "A hazard"} revealed. Another one strikes.`;
          break;
        case "mirror":
          text = "🪞 A Mirror appears. It will copy the next card on this path.";
          break;
        case "fork":
          text = mirrorPrefix(entry) + "🔱 A Fork! After this decision the path splits in two.";
          break;
        case "split":
          text = `🔱 The ${pathLabel(game, entry.path).toLowerCase()} splits.` +
            (entry.discarded ? ` ${entry.discarded} card${entry.discarded === 1 ? " is" : "s are"} discarded` +
              (entry.lost ? ` and ${entry.lost} silver on them is lost.` : ".") : "");
          break;
        case "fork-choice":
          text = forkChoiceText(entry, name);
          className = "good";
          break;
        case "gremlin":
          text = mirrorPrefix(entry) + "👺 A Gremlin appears. It takes a share of every treasure on this path from now on.";
          break;
        case "pot":
          text = mirrorPrefix(entry) + `🏺 ${card?.name || "A pot"} appears. It gains ${card?.growth ?? 5} every turn.`;
          break;
        case "fountain": {
          const doubled = Object.entries(entry.doubled || {}).map(([pid, amount]) => `${name(pid)} ${amount}→${amount * 2}`);
          text = mirrorPrefix(entry) + "⛲ A Fountain! " + (doubled.length ? `Fountain pools double: ${doubled.join(", ")}.` : "Nobody exploring had a fountain pool to double.");
          break;
        }
        case "fountain-moves": {
          const moves = Object.entries(entry.moves || {}).filter(([, amount]) => amount).map(([pid, amount]) =>
            amount > 0 ? `${name(pid)} put ${amount} in` : `${name(pid)} took ${-amount} out`);
          text = `⛲ ${moves.length ? moves.join(", ") + "." : "Nobody touched the fountain."}`;
          break;
        }
        case "bust": {
          const lost = Object.entries(entry.lost || {}).map(([pid, amount]) => `${name(pid)} lost ${amount}`);
          text = mirrorPrefix(entry) + `${card?.icon || ""} Another ${card?.name || "hazard"}! ${guidedText(entry, name)}${lost.length ? lost.join(", ") + "." : ""}` +
            (entry.removed ? ` One ${card?.name || "hazard"} removed from the deck.` : "");
          className = "bad";
          break;
        }
        case "relic":
          text = mirrorPrefix(entry) + `${card?.icon || ""} ${card?.name || "A relic"} appears` +
            (card?.type === "idol" ? ` (worth ${card.value})` : "") + ". Be the only one to leave to take it.";
          break;
        case "saved":
          text = savedText(entry, name, game);
          className = "good";
          break;
        case "gem":
          text = mirrorPrefix(entry) + `${card?.icon || "💎"} A ${card?.name || "gem"}! Time for an auction.`;
          break;
        case "auction": {
          const bids = Object.entries(entry.bids || {}).filter(([, b]) => b).map(([pid, b]) => `${name(pid)} ${b}`);
          text = entry.winner
            ? `💎 ${name(entry.winner)} won the ${card?.name || "gem"} for ${entry.price}.` + (bids.length > 1 ? ` Bids: ${bids.join(", ")}.` : "")
            : `💎 Nobody bid on the ${card?.name || "gem"}. It stays in the deck.`;
          className = entry.winner ? "good" : "";
          break;
        }
        case "red-gem":
          text = `🔴 ${name(entry.player)} used the Red Gem: ${entry.added} secret cards added. The deck now has ${entry.deckSize}.`;
          break;
        case "blue-gem":
          text = `🔵 ${name(entry.player)} used the Blue Gem: 3 cards got a secret mark.`;
          break;
        case "peek":
          text = `🔮 ${name(entry.player)} looked into a Crystal Ball.`;
          break;
        case "marked":
          text = "Everyone secretly marked a card in the deck.";
          break;
        case "altar": {
          const given = Object.entries(entry.given || {}).filter(([, a]) => a).map(([pid, a]) => `${name(pid)} ${a}`);
          text = mirrorPrefix(entry) + `🛐 An Altar! ${given.length ? `Backpacks go on it: ${given.join(", ")}.` : "Nobody had anything to give."}`;
          className = "bad";
          break;
        }
        case "blessing": {
          const doubled = Object.entries(entry.doubled || {}).filter(([, a]) => a).map(([pid, a]) => `${name(pid)} ${a}→${a * 2}`);
          text = mirrorPrefix(entry) + `🌟 A Blessing! ${doubled.length ? `Backpacks double: ${doubled.join(", ")}.` : "Every backpack was empty: nothing to double."}`;
          className = "good";
          break;
        }
        case "death": {
          const lost = Object.entries(entry.lost || {}).map(([pid, a]) => `${name(pid)} lost ${a}`);
          text = mirrorPrefix(entry) + `☠️ Death! The expedition ends.${lost.length ? " " + lost.join(", ") + "." : ""}`;
          className = "bad";
          break;
        }
        case "robbery":
          text = mirrorPrefix(entry) + (entry.choosers?.length
            ? `🦹 Robbery! ${listNames(entry.choosers.map(name))} must give up a relic.`
            : "🦹 Robbery! Nobody had anything worth stealing.");
          break;
        case "robbed": {
          const losses = Object.entries(entry.losses || {}).map(([pid, loss]) => `${name(pid)} lost the ${game.deckCards[loss.card]?.name || loss.card}`);
          text = `🦹 ${losses.join(", ")}.`;
          className = "bad";
          break;
        }
        case "reveal":
          text = revealText(entry, name, game);
          className = entry.groups.length || entry.returned.length ? "good" : "";
          break;
        case "empty":
          text = "The deck ran out. " + (entry.groups || []).map((group) => groupText(group, name, game, "returned safely")).join(" ");
          className = "good";
          break;
        case "gone":
          text = `${name(entry.player)} left the game.`;
          break;
      }
      if (text) items.push(el("li", { className }, text));
    }
    $("log").replaceChildren(...items.reverse());
  }

  function renderHand(game) {
    const seat = game.seats[state.you];
    const show = Boolean(seat) && seat.status !== "gone" && state.phase === "playing" && game.stage !== "marking" && game.stage !== "gem";
    $("hand-bar").hidden = !show;
    $("main").classList.toggle("with-hand", show);
    if (!show) return;

    const hand = state.private?.hand || [];
    const playable = canPlay();
    if (selected !== null && (selected >= hand.length || !cardUsable(hand[selected]) ||
        (!canPeek(hand[selected]) && (!playable || selectedStep !== game.step)))) selected = null;

    const cards = hand.map((cardId, index) => {
      let info = game.handCards[cardId] || { name: cardId, type: "", icon: "" };
      if (game.stage === "fork" && info.type in FORK_SIDES) {
        // Just for this decision, Stay and Leave pick a side of the fork.
        const left = FORK_SIDES[info.type] === "left";
        info = { ...info, name: left ? "Go Left" : "Go Right", icon: left ? "⬅️" : "➡️", text: left ? "Take the left path." : "Take the right path." };
      }
      const usable = cardUsable(cardId);
      const card = el(
        "div",
        {
          className: `hand-card ${info.type}` + (usable ? "" : " disabled") + (index === selected ? " selected" : ""),
          title: info.text || info.name,
        },
        el("div", { className: "icon" }, info.icon || "🂠"),
        el("div", { className: "name" }, info.name),
        usable && index < 9 ? el("div", { className: "key" }, String(index + 1)) : ""
      );
      card.addEventListener("click", () => select(index));
      card.addEventListener("dblclick", () => play(index));
      return card;
    });
    const deciding = canDecideCharm();
    const struckHazard = game.strike?.card;
    const charms = (seat.charms || []).map((charmId) => {
      const charm = game.deckCards[charmId] || { name: charmId };
      const hazard = game.deckCards[charm.protects];
      const usable = deciding && charm.protects === struckHazard;
      const card = el(
        "div",
        { className: "hand-card charm-card" + (usable ? " usable" : ""), title: usable ? `Use ${charm.name}` : charm.text || charm.name },
        el("div", { className: "icon" }, `🧿${hazard?.icon || ""}`),
        el("div", { className: "name" }, charm.name)
      );
      if (usable) card.addEventListener("click", () => decideCharm(true));
      return card;
    });
    const idols = (seat.idols || []).map((idolId) => {
      const idol = game.deckCards[idolId] || { name: idolId };
      return el(
        "div",
        { className: "hand-card charm-card idol-card", title: idol.text || idol.name },
        el("div", { className: "icon" }, idol.icon || "🗿"),
        el("div", { className: "name" }, `${idol.name} (${idol.value})`)
      );
    });
    const relics = [...charms, ...idols];
    $("hand").replaceChildren(
      ...(cards.length ? cards : [el("div", { className: "none" }, "No cards in hand.")]),
      ...(relics.length ? [el("div", { className: "hand-sep" }), ...relics] : [])
    );

    const myPlay = state.private?.played;
    let hint = "";
    let note = "";
    const peeking = selected !== null && canPeek(hand[selected]);
    if (peeking) {
      hint = "Use it to privately see the next 3 cards. It's used up afterwards.";
      note = "Use the Crystal Ball";
    } else if (deciding) {
      hint = "Click your glowing charm to use it, or PASS.";
      note = "Passing keeps the charm, but you lose your backpack and you're out.";
    } else if (game.stage === "charm" && game.plays[state.you]?.chosen) {
      hint = "Waiting for the other charm holders.";
      note = state.private?.charmChoice ? "You used your charm" : "You passed";
    } else if (atFork()) {
      hint = "Pick Go Left or Go Right.";
      note = selected === null ? "Pick a side first." : `Play ${FORK_SIDES[game.handCards[hand[selected]]?.type] === "left" ? "Go Left" : "Go Right"}`;
    } else if (game.stage === "fork" && game.plays[state.you]?.chosen) {
      hint = "Waiting for the others at the fork.";
      note = state.private?.forkChoice === "left" ? "You're going left" : "You're going right";
    } else if (playable && seat.status === "camp") {
      hint = "You're at camp. Play Seconds to go back in, or just wait.";
      if (selected !== null && needsReturnPath(hand[selected])) {
        note = joinablePaths(game).includes(returnPath) ? `Join the ${pathLabel(game, returnPath).toLowerCase()}` : "Click a path in the mine to join it.";
      } else {
        note = selected === null ? "" : "Play Seconds";
      }
    } else if (playable) {
      hint = "Click a card (or press 1–9), then PLAY.";
      note = selected === null ? "Pick a card first." : `Play ${game.handCards[hand[selected]]?.name || "card"}`;
    } else if (game.stage === "choosing" && myPlay) {
      hint = "Waiting for the reveal.";
      note = `You played ${game.handCards[myPlay]?.name || myPlay}`;
    } else if (seat.status === "camp") {
      hint = "You're safe at camp for this expedition.";
    } else if (seat.status === "busted") {
      hint = "Your backpack was lost. Wait for the next expedition.";
    } else {
      hint = "Wait for the next card.";
    }
    $("hand-hint").textContent = hint;
    $("play-note").textContent = note;
    $("play").textContent = deciding ? "PASS" : peeking ? "USE" : "PLAY";
    $("play").classList.toggle("pass", deciding);
    $("play").disabled = deciding || peeking ? false : !playable || selected === null;
  }

  // A hazard struck and you hold its charm. Only the charm holders see this.
  function renderCharmPrompt(game, name) {
    const play = game.plays[state.you];
    const show = state.phase === "playing" && game.stage === "charm" && Boolean(play) && Boolean(game.strike);
    $("charm-prompt").hidden = !show;
    if (!show) return;
    const hazardId = game.strike.card;
    const hazard = game.deckCards[hazardId];
    const seat = game.seats[state.you];
    const charmId = (seat.charms || []).find((c) => game.deckCards[c]?.protects === hazardId);
    const open = canDecideCharm();

    $("charm-title").textContent = `${hazard?.icon || ""} Another ${hazard?.name || "hazard"}!`;
    $("charm-hint").textContent = open
      ? `Click your ${game.deckCards[charmId]?.name || "charm"} in your hand to keep your ${seat.backpack} silver and keep exploring (the charm is used up), or PASS to keep the charm, lose your backpack and be out for this expedition.`
      : state.private?.charmChoice
        ? "You're using your charm."
        : "You're keeping your charm.";
    $("charm-cards").replaceChildren(
      deckCard(game, hazardId, { fatal: true }),
      el("div", { className: "vs" }, "vs"),
      charmId ? deckCard(game, charmId, { inMine: false }) : ""
    );
    const waiting = Object.values(game.plays).filter((p) => !p.chosen).length;
    $("charm-note").textContent = open ? "Your choice stays secret until every charm holder decides." : `Waiting for ${waiting} more…`;
  }

  // A fountain on your path: only explorers with silver to move see this.
  function renderFountainPrompt(game) {
    const play = game.plays[state.you];
    const show = state.phase === "playing" && game.stage === "fountain" && Boolean(play);
    $("fountain-prompt").hidden = !show;
    if (!show) return;
    const seat = game.seats[state.you];
    const open = canUseFountain();
    const range = $("fountain-range");
    const key = `${state.gameNumber}:${game.step}`;
    if (fountainKey !== key) {
      fountainKey = key;
      range.value = 0;
    }
    range.min = -seat.fountain;
    range.max = seat.backpack;
    range.disabled = !open;
    const amount = open ? fountainAmount() : state.private?.fountainChoice ?? 0;
    $("fountain-pack").textContent = String(seat.backpack - amount);
    $("fountain-stash").textContent = String(seat.fountain + amount);
    $("fountain-amount").textContent = amount > 0 ? `Put ${amount} into your fountain pool`
      : amount < 0 ? `Take ${-amount} out of your fountain pool` : "No change";
    $("fountain-hint").textContent = open
      ? "Your fountain pool doubles at every fountain you're still exploring for, and hazards can't touch it. It doesn't score: you can only take silver out at a fountain, and it goes back into your backpack."
      : "Your choice is in.";
    for (const id of ["fountain-btn", "fountain-none", "fountain-all-in", "fountain-all-out"]) $(id).hidden = !open;
    const waiting = Object.values(game.plays).filter((p) => !p.chosen).length;
    $("fountain-note").textContent = open ? "Drag the slider: right puts silver in, left takes it out." : `Waiting for ${waiting} more…`;
  }

  // Robbery: the richest player(s) pick one of their relics to lose.
  function renderRobPrompt(game) {
    const play = game.plays[state.you];
    const show = state.phase === "playing" && game.stage === "robbery" && Boolean(play);
    $("rob-prompt").hidden = !show;
    if (!show) return;
    const seat = game.seats[state.you];
    const open = canChooseLoss();
    const choice = state.private?.robChoice;
    const relics = [
      ...(seat.charms || []).map((c) => ["charm", c]),
      ...(seat.idols || []).map((c) => ["idol", c]),
      ...(seat.relics || []).map((c) => ["relic", c]),
    ];
    $("rob-cards").replaceChildren(...relics.map(([kind, cardId]) => {
      const card = deckCard(game, cardId, { inMine: false });
      if (choice && choice.kind === kind && choice.card === cardId) card.classList.add("selected");
      if (open) card.addEventListener("click", () => chooseLoss(kind, cardId));
      return card;
    }));
    $("rob-cards").classList.toggle("closed", !open);
    $("rob-hint").textContent = open
      ? "You have the most silver in your chest. Click the relic you'll give up."
      : `You gave up the ${game.deckCards[choice?.card]?.name || "relic"}.`;
    const waiting = Object.values(game.plays).filter((p) => !p.chosen).length;
    $("rob-note").textContent = open ? "Idols score their value; other unused relics score 5 each." : waiting ? `Waiting for ${waiting} more…` : "";
  }

  // The gem auction: everyone sees the bids; the bidder whose turn it is gets controls.
  let auctionKey = null;

  function renderAuction(game, name) {
    const a = game.auction;
    const show = state.phase === "playing" && game.stage === "auction" && Boolean(a);
    $("auction").hidden = !show;
    if (!show) return;
    const gem = game.deckCards[a.card];
    $("auction-title").textContent = `${gem?.icon || "💎"} Auction: ${gem?.name || "gem"}`;
    $("auction-card").replaceChildren(deckCard(game, a.card, { inMine: false, flavor: true }));
    $("auction-bids").replaceChildren(...a.order.map((pid, i) => {
      const seat = game.seats[pid];
      const bidText = pid in a.bids ? (a.bids[pid] ? `bid ${a.bids[pid]}` : "passed") : i === a.turn ? "bidding…" : "waiting";
      const item = el("li", {}, `${name(pid)} (🧰 ${seat.chest}): ${bidText}`);
      if (i === a.turn) item.classList.add("turn");
      if (pid === a.leader) item.classList.add("lead");
      return item;
    }));
    const mine = myBidTurn();
    const chest = game.seats[state.you]?.chest ?? 0;
    $("auction-controls").hidden = !mine;
    const key = `${state.gameNumber}:${a.step}:${a.turn}`;
    if (mine) {
      $("bid-amount").min = a.high + 1;
      $("bid-amount").max = chest;
      if (auctionKey !== key) {
        $("bid-amount").value = Math.min(chest, a.high + 1);
        if (document.activeElement?.tagName !== "INPUT") $("bid-amount").focus();
      }
    }
    auctionKey = key;
    $("auction-hint").textContent = mine
      ? `You get one bid: more than ${a.high}, up to your chest (${chest}), or pass. Only the winner pays, and that silver is gone.`
      : `Bids come from chests. Only the winner pays. ${a.leader ? `${name(a.leader)} leads with ${a.high}.` : "No bids yet."}`;
    $("auction-note").textContent = mine ? "Press Enter to bid." : "";
  }

  // End of round: the gem holder uses their gem. Everyone else sees the status line.
  function renderGemPrompt(game, name) {
    const show = myGemTurn();
    $("gem-prompt").hidden = !show;
    if (!show) return;
    const turn = game.gemTurn;
    const gem = game.deckCards[turn.gem];
    const key = `${state.gameNumber}:${game.expedition}:${turn.gem}:${game.log.length}`;
    if (gemKey !== key) {
      gemKey = key;
      gemPicks = [];
      gemEmoji = null;
    }
    $("gem-title").textContent = `${gem?.icon || "💎"} ${gem?.name || "Gem"}`;
    if (turn.color === "red") {
      const options = state.private?.gemOptions || [];
      const need = Math.min(3, options.length);
      $("gem-marks").replaceChildren();
      $("gem-cards").classList.add("open");
      $("gem-cards").replaceChildren(...options.map((cardId, index) => {
        const card = deckCard(game, cardId, { inMine: false, flavor: true });
        if (gemPicks.includes(index)) card.classList.add("selected");
        card.addEventListener("click", () => {
          gemPicks = gemPicks.includes(index) ? gemPicks.filter((i) => i !== index)
            : gemPicks.length < need ? [...gemPicks, index] : gemPicks;
          render();
        });
        return card;
      }));
      $("gem-hint").textContent = `Pick ${need} cards to shuffle into the deck. Nobody else will know which.`;
      $("gem-btn").textContent = "ADD TO DECK";
      $("gem-btn").disabled = gemPicks.length !== need;
      $("gem-note").textContent = `${gemPicks.length} of ${need} picked.`;
    } else {
      $("gem-cards").replaceChildren();
      $("gem-marks").replaceChildren(...(game.markPool || []).map((e) => {
        const button = el("button", { type: "button", title: `Mark with ${e}` }, e);
        if (e === gemEmoji) button.classList.add("selected");
        button.addEventListener("click", () => { gemEmoji = e; render(); });
        return button;
      }));
      $("gem-hint").textContent = "Pick a mark. It goes on the back of 3 random cards in the deck, and you'll see which.";
      $("gem-btn").textContent = "MARK 3 CARDS";
      $("gem-btn").disabled = !gemEmoji;
      $("gem-note").textContent = "";
    }
  }

  // Crystal Ball: the next cards you foresaw (only you).
  function renderVision(game) {
    const vision = state.private?.vision || [];
    $("vision").hidden = !vision.length;
    $("vision").textContent = vision.length
      ? "🔮 Coming up: " + vision.map((c, i) => `${i + 1}. ${game.deckCards[c]?.icon || ""} ${game.deckCards[c]?.name || c}`).join("   ")
      : "";
  }

  // A private reminder of the marks you placed.
  function renderMyMarks(game) {
    const marks = state.private?.myMarks || [];
    $("my-marks").textContent = marks.length
      ? "Your marks: " + marks.map((m) => `${m.emoji} ${game.deckCards[m.card]?.name || m.card}`).join(", ")
      : "";
  }

  // The centered marking view between expeditions. Only players with cards to mark see it.
  const seenDrafts = new Set();

  function renderDraft(game) {
    const offers = state.private?.offers || [];
    const show = state.phase === "playing" && game.stage === "marking" && offers.length > 0;
    $("draft").hidden = !show;
    if (!show) return;

    const key = `${state.gameNumber}:${game.expedition}`;
    const picked = state.private.picked;
    const open = canDraft();
    if (!open || draftKey !== key || draftSelected >= offers.length) draftSelected = null;
    if (!open || draftKey !== key || !game.markEmojis.includes(markEmoji)) markEmoji = null;
    const animate = firstTime(seenDrafts, key);

    const emoji = picked ? picked.emoji : markEmoji;
    $("mark-emojis").replaceChildren(...(game.markEmojis.length ? game.markEmojis : picked ? [picked.emoji] : []).map((e) => {
      const button = el("button", { type: "button", title: `Mark with ${e}`, disabled: !open }, e);
      if (e === emoji) button.classList.add("selected");
      button.addEventListener("click", () => pickEmoji(e));
      return button;
    }));

    const pickedIndex = picked ? offers.findIndex((o) => o.uid === picked.uid) : -1;
    const cards = offers.map((offer, index) => {
      const card = deckCard(game, offer.card, { inMine: false, flavor: true });
      const chosen = open ? index === draftSelected : index === pickedIndex;
      if (chosen) {
        card.classList.add("selected");
        if (emoji) card.append(el("div", { className: "mark-preview" }, emoji));
      } else if (picked) card.classList.add("faded");
      if (open) card.append(el("div", { className: "key" }, String(index + 1)));
      if (animate) {
        card.classList.add("offer-in");
        card.style.animationDelay = `${index * 0.12}s`;
      }
      card.addEventListener("click", () => selectOffer(index));
      card.addEventListener("dblclick", () => draft(index));
      return card;
    });
    $("offers").replaceChildren(...cards);
    $("offers").classList.toggle("open", open);

    const pending = Object.values(game.plays);
    const waiting = pending.filter((p) => !p.chosen).length;
    $("draft-title").textContent = picked ? "Card marked" : "Mark a card";
    $("draft-hint").textContent = picked
      ? `${picked.emoji} is on the back of the ${game.deckCards[offers[pickedIndex]?.card]?.name || "card"}. Only you know.`
      : "Pick a mark and a card. Everyone will see the mark when that card is on top of the deck, but only you know what it means. Marks stay all game.";
    $("draft-btn").hidden = Boolean(picked);
    $("draft-btn").disabled = !open || draftSelected === null || !markEmoji;
    $("draft-note").textContent = picked
      ? `Waiting for ${waiting} more player${waiting === 1 ? "" : "s"}…`
      : !markEmoji ? "Pick a mark above." : draftSelected === null ? "Now click a card (or press 1–3)." : "";
  }
})();
