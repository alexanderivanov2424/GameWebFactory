// Food list page: the lists screen at /food-list/ and one shared list at /food-list/<list name> (adds/edits/checks
// items, uploads pictures); the list's title button opens the lists screen, and Back/forward move between
// them. The lists screen: New List, the Global list, then every list with Edit (name, delete), then New Group
// and every group with Edit (name, delete), then New Tag and every tag with Edit (both in the tag popup: name,
// colour; Delete takes an existing tag off every item).
// Groups (see ../groups.py) are named sets of items and other groups, at /food-list/group/<name>: shown like a
// list but always editing (no checkboxes, mode button, clear buttons or Push), each entry with Edit (items) or
// a tap to open it (groups) and Delete. While adding, groups are suggested next to items (with a Group badge):
// picking one on a list adds every item it holds (nested groups too); on a group it puts that group inside
// (never one that would end up inside itself). The open page's kind ("list", "global" or "group") is `kind`.
// Everything about an item (name, tags, notes, pictures) is saved once for all lists (a "food"); only the
// checkmark belongs to the list. The Global list ("global") holds the items added to it with the editor's
// "Add to global" button and every item with a picture (those can't be taken out); new items aren't in it,
// and an item in neither the Global list nor any list is forgotten. It's edited the same way, nothing is
// checked off or cleared, and Delete marks items (red) for deleting for good once the bar at the top confirms.
// The address picks the screen (route()): /food-list/ is the lists screen, /food-list/<list name> that list
// (Global: /food-list/global; list names are letters, digits, - and _ only, and never "global", checked here
// and by the server; nginx serves index.html for any path under /food-list/, see startup.sh). The address
// follows renames; an unknown or deleted list or group goes back to the lists screen. Removing an item from a
// list or group never asks first. While typing a new item, saved names (on any list or in the
// Global list, see ../store.py) that aren't on this list are suggested, with their tags.
// Item names are lowercase: the server lowercases them too.
// Tags (coloured by their hue) are set in the item editor, by name: new names make new tags on Save.
// Two modes, remembered in localStorage: editing (add row, each item's Edit and Delete buttons) and
// viewing (each item's Push / Unpush button: a pushed item is greyed with a grey border and sorts after the
// others, before the checked ones (green border); checking unpushes and pushing unchecks; Clear checked removes
// the checked items and unpushes the rest; and a row of the list's tags that filters
// the items: tap several to show only items having all of them; the filter only applies when viewing).
// The Global list isn't a real list, just every global item shown like one: always editing (no mode button,
// no Push, no filter), with Edit and Delete (marks for deleting for good) on each item.
// Pictures are decoded and scaled down here, then sent as raw RGB pixels only (4-byte size header
// + width*height*3 bytes, see ../images.py); the server writes its own PNG from them.
// Everything shown comes from the server and is put on the page as text (textContent), never HTML.
// The page reloads every 15 s while it's visible and no dialog is open.
"use strict";

(() => {
  const API = "/food-list/api";
  const MAX_SIDE = 800;           // must match images.MAX_SIDE on the server
  const MAX_FILE = 40e6;          // don't even try to decode files bigger than this
  const REFRESH_MS = 15000;
  const MAX_SUGGESTIONS = 8;
  const MODE_KEY = "food-list.mode";
  const GLOBAL = "global";        // the Global list's id (all saved items) and its name in the address
  const BASE = "/food-list/";     // the page's address; a list name may follow
  const LIST_NAME = /^[A-Za-z0-9_-]+$/;  // the server checks the same: the name is the list's address
  const TAG_NAME = /^[\p{L} ]+$/u;  // the server checks the same: letters and spaces
  const TAG_NAME_MAX = 24;
  const MAX_TAGS_PER_ITEM = 10;

  const $ = (id) => document.getElementById(id);
  const list = $("list"), editor = $("editor"), viewer = $("viewer");
  const listEditor = $("listEditor"), nameDialog = $("nameDialog"), tagEditor = $("tagEditor");
  let lists = [];      // [{id, name, count, left}]
  let groups = [];     // [{id, name, size (items it adds), groups: [ids of the groups directly in it]}]
  let foods = [];      // every saved item: [{name, tags, global}] (sorted by name)
  let tags = [];       // every tag: [{id, name, hue}] (sorted by name)
  let tagsById = new Map();
  let viewing = stored(MODE_KEY) === "view";
  let filterTags = new Set();  // view mode shows only items having every one of these tag ids
  let editTagNames = []; // the open editor's tags, saved on Save
  let wantedName = null;  // the address after /food-list/ ("<list>", "global" or "group/<name>"), until reload() opens it
  let listId = null;      // the open list or group (kept while the lists screen shows)
  let listName = "";
  let kind = "list";      // what's open: "list", "global" or "group" (setKind)
  let isGlobal = false;
  let isGroup = false;
  let doomed = new Set(); // Global list: food ids marked for deleting
  let items = [];
  let editingId = null;
  let msgTimer = 0;

  function stored(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  function store(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* private mode: fine */ }
  }

  function setKind(k) {
    kind = k;
    isGlobal = k === "global";
    isGroup = k === "group";
  }

  // The address after /food-list/ ("<list name>", "global" or "group/<name>"), or null on the lists screen.
  function nameFromPath() {
    const path = location.pathname;
    if (!path.startsWith(BASE)) return null;
    try { return decodeURIComponent(path.slice(BASE.length)).trim() || null; } catch (e) { return null; }
  }

  // Puts the open list's current name in the address (after a rename), while it's showing.
  function syncAddress() {
    if (wantedName || !nameFromPath() || (!isGlobal && !listName)) return;  // lists screen, or not loaded yet
    const want = addressPath(openAddressName());
    if (location.pathname === want) return;
    try { history.replaceState(history.state, "", want); } catch (e) { /* fine: the address just stays */ }
  }

  // The page's path for an address ("group/<name>" keeps its slash).
  function addressPath(address) {
    return BASE + address.split("/").map(encodeURIComponent).join("/");
  }

  // Why a list or group name can't be used, or "" when it's fine (the server checks uniqueness too).
  function listNameProblem(name, what) {
    if (!name) return "Give the " + what + " a name.";
    if (!LIST_NAME.test(name)) return "Letters, digits, - and _ only (no spaces): the name is the " + what + "'s address.";
    if (what === "list" && name.toLowerCase() === GLOBAL) return "“" + name + "” is the Global list's address; pick another name.";
    return "";
  }

  // Finds the list or group named in the address (ignoring case); none: says so and shows the lists screen.
  async function openWanted() {
    const address = wantedName;
    const group = address.toLowerCase().startsWith("group/");
    const name = (group ? address.slice(6) : address).toLowerCase();
    let found = null;
    try {
      const summary = await request("/lists");
      const pool = summary && Array.isArray(group ? summary.groups : summary.lists) ? (group ? summary.groups : summary.lists) : [];
      found = pool.find((l) => String(l.name).toLowerCase() === name);
    } finally {
      if (wantedName === address) wantedName = null;
    }
    if (found || (!group && name === GLOBAL)) {
      listId = found ? found.id : GLOBAL;
      setKind(group ? "group" : found ? "list" : "global");
    } else {
      showError(new Error("There's no " + (group ? "group" : "list") + " called “" + (group ? address.slice(6) : address) + "”."));
      toListsScreen();
    }
  }

  // Shows the lists screen in place of a list that isn't there (the address becomes /food-list/).
  function toListsScreen() {
    listId = null;
    try { history.replaceState(null, "", BASE); } catch (e) { /* fine */ }
    showScreen("lists");
  }

  // ---- talking to the server ----

  async function request(path, options) {
    let response;
    try {
      response = await fetch(API + path, Object.assign({ cache: "no-store", credentials: "same-origin" }, options));
    } catch (e) {
      throw new Error("Can't reach the server. Check your connection.");
    }
    let data = null;
    try { data = await response.json(); } catch (e) { /* not JSON */ }
    if (!response.ok) {
      const text = data && typeof data.error === "string" ? data.error : "Request failed (" + response.status + ").";
      const error = new Error(text.slice(0, 200));
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function post(path, data) {
    return request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {}),
    });
  }

  function imageUrl(id) {
    return API + "/images/" + encodeURIComponent(id) + ".png";
  }

  function listPath(id) {
    return isGlobal ? "/foods" : (isGroup ? "/groups/" : "/lists/") + id;
  }

  // Loads the summary and the open list, if any (one deleted meanwhile: back to the lists screen).
  async function reload() {
    let data = null;
    if (wantedName) await openWanted();
    if (listId) {
      try { data = await request(listPath(listId)); } catch (e) { if (e.status !== 404) throw e; }
    }
    if (!data) {
      if (nameFromPath()) {
        if (listId) showError(new Error("That " + (isGroup ? "group" : "list") + " is gone (someone may have deleted it)."));
        toListsScreen();
      }
      listId = null;
      data = await request("/lists");
    }
    const open = data.list || {};
    lists = Array.isArray(data.lists) ? data.lists : [];
    groups = Array.isArray(data.groups) ? data.groups : [];
    foods = Array.isArray(data.foods) ? data.foods : [];
    tags = Array.isArray(data.tags) ? data.tags : [];
    tagsById = new Map(tags.map((t) => [t.id, t]));
    items = Array.isArray(open.items) ? open.items : [];
    listName = String(open.name || "");
    if (data.list) setKind(open.global === true ? "global" : open.group === true ? "group" : "list");
    render();
    renderLists();
    renderGroupRows();
    renderTagRows();
    renderSuggestions();
    if (editingId) { renderEditorPics(); renderEditorGlobal(); }
  }

  function showError(error) {
    const box = $("msg");
    box.textContent = error && error.message ? error.message : String(error);
    box.classList.add("show");
    clearTimeout(msgTimer);
    msgTimer = setTimeout(() => box.classList.remove("show"), 5000);
  }

  // Runs an action, shows any error, and reloads the list afterwards either way.
  async function act(fn) {
    try { await fn(); } catch (e) { showError(e); }
    try { await reload(); } catch (e) { showError(e); }
  }

  // ---- the list ----

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function thumb(id) {
    const img = el("img");
    img.src = imageUrl(id);
    img.alt = "";
    img.loading = "lazy";
    img.addEventListener("click", (e) => { e.stopPropagation(); openViewer(id); });
    return img;
  }

  // A coloured tag chip: a span, or a button when tag is used as a control.
  function tagChip(tag, tagName, text) {
    const chip = el(tagName || "span", "tag", text === undefined ? tag.name : text);
    if (tagName === "button") chip.type = "button";
    chip.style.setProperty("--h", String(Number(tag.hue) || 0));
    return chip;
  }

  // An item's tags, always in the same order: by name, like the tags list from the server.
  function itemTags(item) {
    const own = new Set(item.tags || []);
    return tags.filter((t) => own.has(t.id));
  }

  // Viewing mode applies to real lists only; the Global list and groups are always edited.
  function isViewing() {
    return viewing && kind === "list";
  }

  function render() {
    $("listName").textContent = listName;
    setTitle();
    syncAddress();
    document.body.classList.toggle("viewing", isViewing());
    document.body.classList.toggle("global", isGlobal);
    document.body.classList.toggle("group", isGroup);
    renderDoomBar();
    $("modeButton").textContent = viewing ? "Viewing" : "Editing";
    renderFilters();
    const wanted = isViewing() ? Array.from(filterTags) : [];
    const shown = items.filter((i) => wanted.every((id) => (i.tags || []).includes(id)));
    const sorted = shown.filter((i) => !i.checked && !i.pushed)
      .concat(shown.filter((i) => i.pushed && !i.checked), shown.filter((i) => i.checked));
    list.replaceChildren(...sorted.map(row));
    $("empty").hidden = items.length > 0;
    $("empty").textContent = isGlobal ? "Nothing here yet. Edit an item on a list and tap “Add to global”."
      : isGroup ? "The group is empty. Add items or other groups above." : "The list is empty.";
    if (items.length && !shown.length) {
      $("empty").hidden = false;
      $("empty").textContent = "No items have all of these tags.";
    }
    $("clearChecked").disabled = !items.some((i) => i.checked || i.pushed);
    $("clearAll").disabled = items.length === 0;
  }

  // A group inside the open group: tap to open it; Delete takes it out.
  function groupEntryRow(entry) {
    const li = el("li", "item");
    const info = el("div", "info");
    const name = el("div", "name", entry.name);
    name.append(el("span", "badge", "Group"));
    info.append(name, el("div", "notes", plural(Number(entry.size) || 0, "item")));
    info.addEventListener("click", () => openList(entry.group, entry.name, "group", false));
    li.append(info, button("Delete", "edit danger", () => removeItem(entry)));
    return li;
  }

  function row(item) {
    if (item.group) return groupEntryRow(item);
    const doom = isGlobal && doomed.has(item.id);
    const state = kind !== "list" ? "" : item.checked ? " done" : item.pushed ? " pushed" : "";
    const li = el("li", "item" + state + (doom ? " doomed" : ""));

    const check = el("label", "check");
    const box = el("input");
    box.type = "checkbox";
    box.checked = !!item.checked;
    box.setAttribute("aria-label", "Got " + item.name);
    box.addEventListener("change", () => {
      item.checked = box.checked;
      if (box.checked) item.pushed = false;
      render();
      act(() => post("/items/" + item.id + "/update", { checked: box.checked }));
    });
    check.append(box);

    const info = el("div", "info");
    const name = el("div", "name", item.name);
    info.append(name);
    const chips = itemTags(item);
    if (chips.length) {
      const line = el("div", "chips");
      line.append(...chips.map((t) => tagChip(t)));
      info.append(line);
    }
    if (item.notes) info.append(el("div", "notes", item.notes));
    if (item.images && item.images.length) {
      const thumbs = el("div", "thumbs");
      thumbs.append(...item.images.map(thumb));
      info.append(thumbs);
    }
    info.addEventListener("click", () => { if (!isViewing()) openEditor(item.id); });

    // Editing: Edit and Delete (.edit); viewing: Push / Unpush (.push). CSS shows one set.
    // The Global list and groups have no checkbox or Push: they're always edited.
    const edit = button("Edit", "edit", () => openEditor(item.id));
    const remove = isGlobal
      ? button(doom ? "Keep" : "Delete", "edit danger", () => {
        if (doomed.has(item.id)) doomed.delete(item.id);
        else doomed.add(item.id);
        render();
      })
      : button("Delete", "edit danger", () => removeItem(item));
    if (kind !== "list") {
      li.append(info, edit, remove);
    } else {
      const push = button(item.pushed ? "Unpush" : "Push", "push", () => {
        item.pushed = !item.pushed;
        if (item.pushed) item.checked = false;
        render();
        act(() => post("/items/" + item.id + "/update", { pushed: item.pushed }));
      });
      push.setAttribute("aria-pressed", String(!!item.pushed));
      li.append(check, info, edit, remove, push);
    }
    return li;
  }

  // Takes an item off the open list, or an entry out of the open group (no questions asked).
  function removeItem(item) {
    if (editor.open) editor.close();
    const path = isGroup ? "/groups/" + listId + "/entries/" + item.id + "/delete" : "/items/" + item.id + "/delete";
    act(() => post(path));
  }

  // ---- deleting saved items for good (Global list) ----

  function renderDoomBar() {
    for (const id of doomed) if (!isGlobal || !items.some((i) => i.id === id)) doomed.delete(id);
    $("doomBar").hidden = doomed.size === 0;
    $("doomText").textContent = "Delete " + plural(doomed.size, "item") + " for good, from every list?";
  }

  $("doomCancel").addEventListener("click", () => { doomed.clear(); render(); });
  $("doomConfirm").addEventListener("click", () => {
    const ids = Array.from(doomed);
    doomed.clear();
    render();
    act(() => post("/foods/delete", { ids }));
  });


  // The view mode's filter row: "All" (clears the selection) plus every tag on this list, each
  // toggled on or off. Selected tags no longer on the list are dropped.
  function renderFilters() {
    const used = new Set(items.flatMap((i) => i.tags || []));
    for (const id of filterTags) if (!used.has(id)) filterTags.delete(id);
    const onList = tags.filter((t) => used.has(t.id));
    if (!onList.length) { $("filters").replaceChildren(); return; }
    const changed = () => { render(); window.scrollTo(0, 0); };
    const all = el("button", "tag plain", "All");
    all.type = "button";
    all.setAttribute("aria-pressed", String(filterTags.size === 0));
    all.addEventListener("click", () => { filterTags.clear(); changed(); });
    $("filters").replaceChildren(all, ...onList.map((t) => {
      const chip = tagChip(t, "button");
      chip.setAttribute("aria-pressed", String(filterTags.has(t.id)));
      chip.addEventListener("click", () => {
        if (filterTags.has(t.id)) filterTags.delete(t.id);
        else filterTags.add(t.id);
        changed();
      });
      return chip;
    }));
  }

  $("modeButton").addEventListener("click", () => {
    viewing = !viewing;
    doomed.clear();
    store(MODE_KEY, viewing ? "view" : "edit");
    render();
  });

  function plural(n, word) {
    return n + " " + word + (n === 1 ? "" : "s");
  }

  // ---- adding items, with suggestions from every name added before ----

  function clearAddRow() {
    $("addName").value = "";
    renderSuggestions();
  }

  function addItem(name) {
    clearAddRow();
    const path = (isGroup ? "/groups/" : "/lists/") + listId + "/items";
    act(() => post(path, { name: name.toLowerCase() }));
  }

  // A group picked from the suggestions: on a list, all its items; on a group, the group itself.
  function addGroup(group) {
    clearAddRow();
    const path = isGroup ? "/groups/" + listId + "/items" : "/lists/" + listId + "/groups";
    act(() => post(path, { group: group.id }));
  }

  // The ids of a group and every group inside it (the server keeps loops out, but stay safe anyway).
  function inside(groupId) {
    const byId = new Map(groups.map((g) => [g.id, g]));
    const found = new Set();
    const todo = [groupId];
    while (todo.length) {
      const id = todo.pop();
      if (found.has(id) || !byId.has(id)) continue;
      found.add(id);
      todo.push(...(byId.get(id).groups || []));
    }
    return found;
  }

  // The groups that may be added here: on a group, not itself, not ones it's inside, not ones already in it.
  function addableGroups() {
    if (!isGroup) return groups;
    const already = new Set(items.filter((i) => i.group).map((i) => i.group));
    return groups.filter((g) => g.id !== listId && !already.has(g.id) && !inside(g.id).has(listId));
  }

  // Names starting with what's typed come first, then names containing it; groups before items in each.
  function renderSuggestions() {
    const box = $("suggest");
    const typed = $("addName").value.trim().replace(/\s+/g, " ").toLowerCase();
    const onList = new Set(items.filter((i) => !i.group).map((i) => i.name));
    const starts = [], contains = [];
    const consider = (name, entry) => {
      const at = name.toLowerCase().indexOf(typed);
      if (at === 0) starts.push(entry);
      else if (at > 0) contains.push(entry);
    };
    if (typed && !isGlobal) {
      for (const g of addableGroups()) consider(g.name, { group: g });
      for (const food of foods) {
        if (food.name !== typed && !onList.has(food.name)) consider(food.name, { food });
      }
    }
    const shown = starts.concat(contains).slice(0, MAX_SUGGESTIONS);
    box.replaceChildren(...shown.map((entry) => {
      const li = el("li");
      const pick = el("button");
      pick.type = "button";
      if (entry.group) {
        pick.append(el("span", "suggest-name", entry.group.name), el("span", "badge", "Group"),
          el("span", "badge", plural(Number(entry.group.size) || 0, "item")));
        pick.addEventListener("click", () => addGroup(entry.group));
      } else {
        pick.append(el("span", "suggest-name", entry.food.name), ...itemTags(entry.food).map((t) => tagChip(t)));
        pick.addEventListener("click", () => addItem(entry.food.name));
      }
      li.append(pick);
      return li;
    }));
    box.hidden = shown.length === 0;
  }

  $("suggest").addEventListener("mousedown", (e) => e.preventDefault());  // keep the keyboard up
  $("addName").addEventListener("input", renderSuggestions);
  $("addName").addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.target.value = ""; renderSuggestions(); }
  });

  $("add").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = $("addName").value.trim();
    if (name) addItem(name);
  });

  $("clearChecked").addEventListener("click", () => {
    const count = items.filter((i) => i.checked).length;
    const pushed = items.filter((i) => i.pushed).length;
    if (!count && !pushed) return;
    const what = [count ? "remove " + plural(count, "checked item") : "", pushed ? "unpush " + plural(pushed, "pushed item") : ""];
    const text = what.filter(Boolean).join(" and ");
    if (confirm(text.charAt(0).toUpperCase() + text.slice(1) + "?")) {
      const id = listId;
      act(() => post("/lists/" + id + "/clear", { which: "checked" }));
    }
  });

  $("clearAll").addEventListener("click", () => {
    if (!items.length) return;
    if (confirm("Remove ALL " + plural(items.length, "item") + " from “" + listName + "”? This can't be undone.")) {
      const id = listId;
      act(() => post("/lists/" + id + "/clear", { which: "all" }));
    }
  });

  // ---- the lists screen ----

  function setTitle() {
    document.title = !$("listsView").hidden ? "Food lists" : listName || "Food list";
  }

  function showScreen(screen) {
    const showLists = screen === "lists";
    if ($("listsView").hidden !== showLists) return;
    $("listView").hidden = showLists;
    $("listsView").hidden = !showLists;
    setTitle();
    window.scrollTo(0, 0);
  }

  // Shows the screen the address names (on load and on Back/forward): /food-list/ the lists screen,
  // /food-list/<name> that list (looked up by reload() unless it's the open one).
  function route() {
    const name = nameFromPath();
    wantedName = name && (!listId || name.toLowerCase() !== openAddressName().toLowerCase()) ? name : null;
    showScreen(name ? "list" : "lists");
    reload().catch(showError);
  }

  // The open page's address after /food-list/ ("global" for the Global list, "group/<name>" for a group).
  function openAddressName() {
    return isGlobal ? GLOBAL : isGroup ? "group/" + listName : listName;
  }

  // History entries made here say where they came from, so going "back up" uses Back instead of piling up.
  function openLists() {
    if (history.state && history.state.fromLists) { history.back(); return; }  // popstate routes
    history.pushState({ fromList: openAddressName() }, "", BASE);
    route();
  }

  // Done: back to the open list (with Back when that's the entry before this one).
  function closeLists() {
    const from = history.state && history.state.fromList;
    if (typeof from === "string" && from.toLowerCase() === openAddressName().toLowerCase()) history.back();
    else if (listId) openList(listId, listName, kind);
  }

  // Opens a list, the Global list or a group (k: "list", "global" or "group"); fromLists: false when
  // opened from another page (a group inside a group), so the title button doesn't go Back to that page.
  function openList(id, name, k, fromLists = true) {
    if (id !== listId || k !== kind) {
      listId = id;
      items = [];
      setKind(k);
      doomed.clear();
      listName = isGlobal ? "Global" : name;
      render();
      renderSuggestions();
    }
    history.pushState(fromLists ? { fromLists: true } : null, "", addressPath(openAddressName()));
    route();
  }

  function listRow(name, detail, isCurrent, onOpen, buttons) {
    const li = el("li", "item" + (isCurrent ? " current" : ""));
    const info = el("div", "info");
    info.append(name, el("div", "notes", detail));
    info.addEventListener("click", onOpen);
    li.append(info, ...buttons);
    return li;
  }

  function button(text, cls, onClick) {
    const b = el("button", cls, text);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function renderLists() {
    const global = listRow(el("div", "name", "Global"),
      plural(foods.filter((f) => f.global).length, "saved item") + " · names and tags", isGlobal && listId === GLOBAL, () => openList(GLOBAL, "Global", "global"), []);
    $("closeLists").hidden = !listId;  // Done goes back to the open list
    $("lists").replaceChildren(global, ...lists.map((l) => {
      const name = el("div", "name", l.name);
      const counts = l.count ? l.left + " to get · " + plural(l.count, "item") : "Empty";
      return listRow(name, counts, kind === "list" && l.id === listId, () => openList(l.id, l.name, "list"),
        [button("Edit", "edit", () => openListEditor(l, "list"))]);
    }));
  }

  // ---- the groups section ----

  function renderGroupRows() {
    $("groupRows").replaceChildren(...groups.map((g) => listRow(el("div", "name", g.name),
      g.size ? plural(g.size, "item") : "Empty", isGroup && g.id === listId, () => openList(g.id, g.name, "group"),
      [button("Edit", "edit", () => openListEditor(g, "group"))])));
    $("noGroups").hidden = groups.length > 0;
  }

  // ---- the tags section and the tag editor ----

  function renderTagRows() {
    $("tagRows").replaceChildren(...tags.map((t) => {
      const li = el("li", "item");
      const info = el("div", "info");
      info.append(tagChip(t));
      info.addEventListener("click", () => openTagEditor(t));
      li.append(info, button("Edit", "edit", () => openTagEditor(t)));
      return li;
    }));
    $("noTags").hidden = tags.length > 0;
  }

  let editingTag = null;  // null while making a new tag
  let tagHue = 0;

  // A random one of the 12 swatch colours least used by tags so far (the server does the same).
  function freshHue() {
    const counts = [];
    for (let h = 0; h < 360; h += 30) {
      counts.push([h, tags.filter((t) => Math.abs(((Number(t.hue) - h + 540) % 360) - 180) < 15).length]);
    }
    const least = Math.min(...counts.map((c) => c[1]));
    const options = counts.filter((c) => c[1] === least);
    return options[Math.floor(Math.random() * options.length)][0];
  }

  function openTagEditor(t) {
    editingTag = t || null;
    tagHue = t ? Number(t.hue) || 0 : freshHue();
    $("tagTitle").textContent = t ? "Edit tag" : "New tag";
    $("deleteTag").hidden = !t;
    $("tagNameInput").value = t ? t.name : "";
    $("tagError").textContent = "";
    renderTagEditor();
    tagEditor.showModal();
  }

  function renderTagEditor() {
    $("tagHue").value = String(tagHue);
    const preview = $("tagPreview");
    preview.textContent = $("tagNameInput").value.trim().toLowerCase() || "tag";
    preview.style.setProperty("--h", String(tagHue));
    const swatches = [];
    for (let h = 0; h < 360; h += 30) {
      const swatch = button("", "swatch", () => { tagHue = h; renderTagEditor(); });
      swatch.style.setProperty("--h", String(h));
      swatch.setAttribute("aria-label", "Colour " + h);
      swatch.setAttribute("aria-pressed", String(h === tagHue));
      swatches.push(swatch);
    }
    $("swatches").replaceChildren(...swatches);
  }

  $("tagHue").addEventListener("input", (e) => { tagHue = Number(e.target.value) || 0; renderTagEditor(); });
  $("tagNameInput").addEventListener("input", () => { $("tagError").textContent = ""; renderTagEditor(); });
  $("cancelTag").addEventListener("click", () => tagEditor.close());
  $("newTagButton").addEventListener("click", () => openTagEditor(null));

  $("deleteTag").addEventListener("click", () => {
    const t = editingTag;
    if (!t) return;
    if (!confirm("Delete the tag “" + t.name + "” for good? It comes off every item.")) return;
    tagEditor.close();
    act(() => post("/tags/" + t.id + "/delete"));
  });

  $("tagForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const t = editingTag;
    const name = $("tagNameInput").value.normalize("NFC").trim().replace(/\s+/g, " ").toLowerCase();
    if (!name || !TAG_NAME.test(name)) { $("tagError").textContent = "Tags can only have letters and spaces."; return; }
    try {
      await post(t ? "/tags/" + t.id + "/update" : "/tags", { name, hue: tagHue });
    } catch (err) { $("tagError").textContent = err.message; return; }
    tagEditor.close();
    reload().catch(showError);
  });

  $("listButton").addEventListener("click", openLists);
  $("closeLists").addEventListener("click", closeLists);
  window.addEventListener("popstate", route);

  // ---- editing a list or a group (name, delete) ----

  let editingList = null;
  let editingKind = "list";  // "list" or "group", for the list popup and the name popup

  function nameHint(what) {
    return "Letters, digits, - and _ only. It's the " + what + "'s address: /food-list/" + (what === "group" ? "group/" : "") + "<name>";
  }

  function kindPath(what) {
    return what === "group" ? "/groups" : "/lists";
  }

  function openListEditor(l, what) {
    editingList = l;
    editingKind = what;
    $("listEditorTitle").textContent = what === "group" ? "Edit group" : "Edit list";
    $("listNameHint").textContent = nameHint(what);
    $("listNameInput").value = l.name;
    $("listError").textContent = "";
    const only = what === "list" && lists.length < 2;
    $("deleteList").disabled = only;
    $("deleteList").title = only ? "The only list can't be deleted" : "";
    listEditor.showModal();
  }

  $("cancelList").addEventListener("click", () => listEditor.close());

  $("listForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const l = editingList;
    const name = $("listNameInput").value.trim();
    if (!l) return listEditor.close();
    const problem = listNameProblem(name, editingKind);
    if (problem) { $("listError").textContent = problem; return; }
    try {
      await post(kindPath(editingKind) + "/" + l.id + "/update", { name });
    } catch (err) { $("listError").textContent = err.message; return; }
    listEditor.close();
    reload().catch(showError);
  });

  $("deleteList").addEventListener("click", () => {
    const l = editingList;
    if (!l) return;
    const group = editingKind === "group";
    const what = group ? "" : l.count ? " and its " + plural(l.count, "item") : "";
    const also = group ? " It's taken out of any group holding it." : "";
    if (!confirm("Delete the " + editingKind + " “" + l.name + "”" + what + "? This can't be undone." + also)) return;
    listEditor.close();
    act(() => post(kindPath(editingKind) + "/" + l.id + "/delete"));
  });

  // ---- naming a new list or group ----

  function openNameDialog(what) {
    editingKind = what;
    $("nameTitle").textContent = what === "group" ? "New group" : "New list";
    $("nameHint").textContent = nameHint(what);
    $("nameInput").value = "";
    $("nameError").textContent = "";
    nameDialog.showModal();
  }

  $("newListButton").addEventListener("click", () => openNameDialog("list"));
  $("newGroupButton").addEventListener("click", () => openNameDialog("group"));
  $("cancelName").addEventListener("click", () => nameDialog.close());

  $("nameForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("nameInput").value.trim();
    const what = editingKind;
    const problem = listNameProblem(name, what);
    if (problem) { $("nameError").textContent = problem; return; }
    let made;
    try {
      made = await post(kindPath(what), { name });
    } catch (err) { $("nameError").textContent = err.message; return; }
    nameDialog.close();
    openList(made.id, made.name, what);
  });

  // ---- editing one item ----

  function current() {
    return items.find((i) => i.id === editingId) || null;
  }

  function openEditor(id) {
    const item = items.find((i) => i.id === id);
    if (!item) return;
    editingId = id;
    $("editName").value = item.name;
    $("editNotes").value = item.notes || "";
    $("editError").textContent = "";
    $("busy").textContent = "";
    editTagNames = itemTags(item).map((t) => t.name);
    $("tagInput").value = "";
    tagHint("");
    renderEditorTags();
    renderEditorPics();
    renderEditorGlobal();
    editor.showModal();
  }

  function renderEditorPics() {
    const item = current();
    if (!item) { editor.close(); return; }
    const pics = (item.images || []).map((id) => {
      const box = el("div", "pic");
      const img = el("img");
      img.src = imageUrl(id);
      img.alt = "";
      img.addEventListener("click", () => openViewer(id));
      const remove = el("button", "", "✕");
      remove.type = "button";
      remove.setAttribute("aria-label", "Remove picture");
      remove.addEventListener("click", () => {
        if (confirm("Remove this picture? It's gone from every list.")) {
          act(() => post("/foods/" + item.food + "/images/" + id + "/delete"));
        }
      });
      box.append(img, remove);
      return box;
    });
    $("editPics").replaceChildren(...pics);
  }

  // The "Add to global" / "Remove from global" button next to Remove (lists and groups; it saves right
  // away). Items with pictures always stay in the Global list, so it's disabled for them.
  function renderEditorGlobal() {
    const item = current();
    if (!item) return;
    const pictures = !!(item.images && item.images.length);
    $("globalItem").textContent = item.global ? "Remove from global" : "Add to global";
    $("globalItem").className = "item-only" + (item.global ? " danger-soft" : "");  // like Remove, lightly filled
    $("globalItem").disabled = item.global && pictures;
    $("globalItem").title = item.global && pictures ? "Items with pictures stay in the Global list" : "";
  }

  $("globalItem").addEventListener("click", () => {
    const item = current();
    if (!item || isGlobal) return;
    act(() => post("/foods/" + item.food + "/update", { global: !item.global }));
  });

  // ---- the editor's tags (sent by name with Save; the server makes new ones) ----

  function tagHint(problem) {
    const hint = $("tagHint");
    hint.textContent = problem || "Letters and spaces only. Tags stay with the item on every list.";
    hint.classList.toggle("bad", !!problem);
  }

  function typedTag() {
    return $("tagInput").value.normalize("NFC").trim().replace(/\s+/g, " ").toLowerCase();
  }

  // Adds the typed tag to the item; returns false (and says why) when it can't.
  function addTypedTag() {
    const name = typedTag();
    if (!name) return true;
    if (!TAG_NAME.test(name)) { tagHint("Tags can only have letters and spaces."); return false; }
    if (name.length > TAG_NAME_MAX) { tagHint("Tags can have at most " + TAG_NAME_MAX + " letters."); return false; }
    if (!editTagNames.includes(name)) {
      if (editTagNames.length >= MAX_TAGS_PER_ITEM) { tagHint("An item can have at most " + MAX_TAGS_PER_ITEM + " tags."); return false; }
      editTagNames.push(name);
    }
    $("tagInput").value = "";
    tagHint("");
    renderEditorTags();
    return true;
  }

  function renderEditorTags() {
    const byName = new Map(tags.map((t) => [t.name, t]));
    $("editTags").replaceChildren(...editTagNames.slice().sort().map((name) => {
      const tag = byName.get(name);
      const chip = tag ? tagChip(tag, "button", name + " ✕") : el("button", "tag plain new", name + " ✕");
      chip.type = "button";
      if (tag) chip.title = "Remove this tag";
      chip.setAttribute("aria-label", "Remove tag " + name);
      chip.addEventListener("click", () => {
        editTagNames = editTagNames.filter((n) => n !== name);
        renderEditorTags();
      });
      return chip;
    }));
    const typed = typedTag();
    const choices = tags.filter((t) => !editTagNames.includes(t.name) && t.name.includes(typed));
    $("tagChoices").replaceChildren(...choices.slice(0, 30).map((t) => {
      const chip = tagChip(t, "button", "+ " + t.name);
      chip.addEventListener("click", () => {
        $("tagInput").value = t.name;
        addTypedTag();
      });
      return chip;
    }));
  }

  $("tagInput").addEventListener("input", () => { tagHint(""); renderEditorTags(); });
  $("tagInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); addTypedTag(); }
  });
  $("addTag").addEventListener("click", addTypedTag);

  editor.addEventListener("close", () => { editingId = null; });
  $("cancelEdit").addEventListener("click", () => editor.close());

  $("editForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const item = current();
    if (!item) return editor.close();
    const name = $("editName").value.trim().toLowerCase();
    if (!name) { showError(new Error("Give the item a name.")); return; }
    if (!addTypedTag()) return;  // a tag typed but not added yet counts
    const change = { name, tags: editTagNames.slice(), notes: $("editNotes").value };
    const path = kind !== "list" ? "/foods/" + item.food + "/update" : "/items/" + item.id + "/update";
    editor.close();
    act(() => post(path, change));
  });

  $("deleteItem").addEventListener("click", () => {
    const item = current();
    if (item) removeItem(item);
  });

  // ---- pictures ----

  // Decodes an image file in the browser and returns raw pixels: [w hi, w lo, h hi, h lo, r, g, b, r, g, b...].
  async function toRawRgb(file) {
    if (!file || !(file.type || "image/").startsWith("image/")) throw new Error("That file isn't an image.");
    if (file.size > MAX_FILE) throw new Error("That image file is too big.");
    const url = URL.createObjectURL(file);
    try {
      const img = new Image();
      img.src = url;
      try { await img.decode(); } catch (e) { throw new Error("That image couldn't be read."); }
      const scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
      const w = Math.max(1, Math.min(MAX_SIDE, Math.round(img.naturalWidth * scale)));
      const h = Math.max(1, Math.min(MAX_SIDE, Math.round(img.naturalHeight * scale)));
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";           // transparent parts become white
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      const rgba = ctx.getImageData(0, 0, w, h).data;
      const out = new Uint8Array(4 + w * h * 3);
      const view = new DataView(out.buffer);
      view.setUint16(0, w);
      view.setUint16(2, h);
      for (let i = 0, j = 4; i < rgba.length; i += 4) {
        out[j++] = rgba[i];
        out[j++] = rgba[i + 1];
        out[j++] = rgba[i + 2];
      }
      return out;
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function uploadFiles(input) {
    const files = Array.from(input.files || []);
    input.value = "";
    const item = current();
    if (!item || !files.length) return;
    const busy = $("busy");
    for (let n = 0; n < files.length; n++) {
      busy.textContent = "Uploading picture " + (n + 1) + " of " + files.length + "…";
      try {
        const raw = await toRawRgb(files[n]);
        await request("/foods/" + item.food + "/images", {
          method: "POST",
          headers: { "Content-Type": "application/octet-stream" },
          body: raw,
        });
      } catch (e) {
        showError(e);
        break;
      }
    }
    busy.textContent = "";
    try { await reload(); } catch (e) { showError(e); }
  }

  $("takePhoto").addEventListener("change", (e) => uploadFiles(e.target));
  $("choosePhoto").addEventListener("change", (e) => uploadFiles(e.target));

  function openViewer(id) {
    $("viewerImg").src = imageUrl(id);
    viewer.showModal();
  }
  $("closeViewer").addEventListener("click", () => viewer.close());
  viewer.addEventListener("click", (e) => { if (e.target === viewer) viewer.close(); });

  // ---- keeping in sync with other phones ----

  function refresh() {
    if (document.hidden || editor.open || viewer.open || listEditor.open || nameDialog.open || tagEditor.open) return;
    reload().catch(() => { /* quiet: try again next time */ });
  }
  setInterval(refresh, REFRESH_MS);
  document.addEventListener("visibilitychange", refresh);

  route();
})();
