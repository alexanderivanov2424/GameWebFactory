// Food list page (/food-list/): shows one shared list (adds/edits/checks items, uploads pictures)
// and the lists screen (the title button; the phone's Back button closes it): New list, the Global
// list, then every list with Edit (name, template, delete) and, on templates, Copy (named in a
// popup, "<name>-<month>/<day>" by default; a copy shows its template's name and has Delete list
// instead of the clear buttons). Everything about an item (name, tags, notes, unit, pictures) is
// saved once for all lists (a "food"); only the amount (any short text) and the checkmark belong to
// the list. The Global list ("global") holds only the items added to it with the editor's "Add to
// global" button (new items aren't; an item in neither the Global list nor any list is forgotten):
// edited the same way (its amount is the default new entries start with), nothing checked off or
// cleared, and Delete marks items (red) for deleting for good once the bar at the top confirms. Below the lists, New tag and every tag with Edit
// (both in the tag popup: name, colour; Delete takes an existing tag off every item).
// The open list is remembered in localStorage. While typing a new item, saved names (on any list or in the
// Global list, see ../store.py) that aren't on this list are suggested, with their tags.
// Item names are lowercase: the server lowercases them too.
// Tags (coloured by their hue) are set in the item editor, by name: new names make new tags on Save.
// Two modes, remembered in localStorage: edit (add row, Edit buttons) and view (a row of the list's
// tags that filters the items: tap several to show only items having all of them; the filter only
// applies in view mode).
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
  const CURRENT_KEY = "food-list.current";
  const MODE_KEY = "food-list.mode";
  const HEX_ID = /^[0-9a-f]{16}$/;
  const GLOBAL = "global";        // the Global list's id (all saved items)
  const LIST_NAME_MAX = 40;
  const TAG_NAME = /^[\p{L} ]+$/u;  // the server checks the same: letters and spaces
  const TAG_NAME_MAX = 24;
  const MAX_TAGS_PER_ITEM = 10;
  const AMOUNT_MAX = 20;          // characters, like the server

  const $ = (id) => document.getElementById(id);
  const list = $("list"), editor = $("editor"), viewer = $("viewer");
  const listEditor = $("listEditor"), nameDialog = $("nameDialog"), tagEditor = $("tagEditor");
  let lists = [];      // [{id, name, template, count, left}]
  let foods = [];      // every saved item: [{name, tags, global}] (sorted by name)
  let tags = [];       // every tag: [{id, name, hue}] (sorted by name)
  let tagsById = new Map();
  let viewing = stored(MODE_KEY) === "view";
  let filterTags = new Set();  // view mode shows only items having every one of these tag ids
  let editTagNames = []; // the open editor's tags, saved on Save
  let listId = remembered();
  let listName = "";
  let isGlobal = false;
  let copyOf = null;     // the template's name when the open list is a copy of one
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

  function remembered() {
    const id = stored(CURRENT_KEY);
    return id && (id === GLOBAL || HEX_ID.test(id)) ? id : null;
  }

  function remember(id) {
    store(CURRENT_KEY, id);
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
    return id === GLOBAL ? "/foods" : "/lists/" + id;
  }

  // Loads the open list (or the first one, when none is open or it was deleted) and the summary.
  async function reload() {
    let data = null;
    if (listId) {
      try { data = await request(listPath(listId)); } catch (e) { if (e.status !== 404) throw e; }
    }
    if (!data) {
      const summary = await request("/lists");
      const first = summary && Array.isArray(summary.lists) && summary.lists[0];
      if (!first) throw new Error("There are no lists.");
      data = await request("/lists/" + first.id);
    }
    const open = data.list || {};
    lists = Array.isArray(data.lists) ? data.lists : [];
    foods = Array.isArray(data.foods) ? data.foods : [];
    tags = Array.isArray(data.tags) ? data.tags : [];
    tagsById = new Map(tags.map((t) => [t.id, t]));
    items = Array.isArray(open.items) ? open.items : [];
    listName = String(open.name || "");
    isGlobal = open.global === true;
    copyOf = typeof open.copy_of === "string" ? open.copy_of : null;
    if (open.id !== listId) { listId = open.id; remember(listId); }
    render();
    renderLists();
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

  function render() {
    $("listName").textContent = listName;
    document.title = listName || "Food list";
    document.body.classList.toggle("viewing", viewing);
    document.body.classList.toggle("global", isGlobal);
    document.body.classList.toggle("copy", !!copyOf && !isGlobal);
    $("listSub").textContent = copyOf ? "Copy of " + copyOf : "";
    $("listSub").hidden = !copyOf || isGlobal;
    renderDoomBar();
    $("modeButton").textContent = viewing ? "View" : "Edit";
    $("modeButton").title = viewing ? "View mode: tap to edit" : "Edit mode: tap to view";
    renderFilters();
    const wanted = viewing ? Array.from(filterTags) : [];
    const shown = items.filter((i) => wanted.every((id) => (i.tags || []).includes(id)));
    const sorted = shown.filter((i) => !i.checked).concat(shown.filter((i) => i.checked));
    list.replaceChildren(...sorted.map(row));
    $("empty").hidden = items.length > 0;
    $("empty").textContent = isGlobal ? "Nothing here yet. Edit an item on a list and tap “Add to global”." : "The list is empty.";
    if (items.length && !shown.length) {
      $("empty").hidden = false;
      $("empty").textContent = "No items have all of these tags.";
    }
    $("clearChecked").disabled = !items.some((i) => i.checked);
    $("clearAll").disabled = items.length === 0;
  }

  function row(item) {
    const doom = isGlobal && doomed.has(item.id);
    const li = el("li", "item" + (item.checked && !isGlobal ? " done" : "") + (doom ? " doomed" : ""));

    const check = el("label", "check");
    const box = el("input");
    box.type = "checkbox";
    box.checked = !!item.checked;
    box.setAttribute("aria-label", "Got " + item.name);
    box.addEventListener("change", () => {
      item.checked = box.checked;
      render();
      act(() => post("/items/" + item.id + "/update", { checked: box.checked }));
    });
    check.append(box);

    const info = el("div", "info");
    const name = el("div", "name", item.name);
    const qty = quantity(item);
    if (qty) name.append(el("span", "qty", qty));
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
    info.addEventListener("click", () => { if (!viewing) openEditor(item.id); });

    const edit = el("button", "edit", "Edit");
    edit.type = "button";
    edit.addEventListener("click", () => openEditor(item.id));

    if (isGlobal) {
      const remove = button(doom ? "Keep" : "Delete", "edit danger", () => {
        if (doomed.has(item.id)) doomed.delete(item.id);
        else doomed.add(item.id);
        render();
      });
      li.append(info, edit, remove);
    } else {
      li.append(check, info, edit);
    }
    return li;
  }

  // "2 dozen", "×3", "a few", or "" when no amount is set.
  function quantity(item) {
    const amount = item.amount === null || item.amount === undefined ? "" : String(item.amount);
    if (!amount) return "";
    if (item.unit) return amount + " " + item.unit;
    return /^\d+([.,]\d+)?$/.test(amount) ? "×" + amount : amount;
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

  $("deleteListTop").addEventListener("click", () => {
    const id = listId;
    if (!confirm("Delete the list “" + listName + "”? This can't be undone.")) return;
    act(async () => {
      await post("/lists/" + id + "/delete");
      if (listId === id) listId = null;  // reload opens the first list
    });
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

  function addItem(name) {
    const input = $("addName");
    input.value = "";
    renderSuggestions();
    const id = listId;
    act(() => post("/lists/" + id + "/items", { name: name.toLowerCase() }));
  }

  // Names starting with what's typed come first, then names containing it.
  function renderSuggestions() {
    const box = $("suggest");
    const typed = $("addName").value.trim().replace(/\s+/g, " ").toLowerCase();
    const onList = new Set(items.map((i) => i.name));
    const starts = [], contains = [];
    if (typed && !isGlobal) {
      for (const food of foods) {
        if (food.name === typed || onList.has(food.name)) continue;
        const at = food.name.indexOf(typed);
        if (at === 0) starts.push(food);
        else if (at > 0) contains.push(food);
      }
    }
    const shown = starts.concat(contains).slice(0, MAX_SUGGESTIONS);
    box.replaceChildren(...shown.map((food) => {
      const li = el("li");
      const pick = el("button");
      pick.type = "button";
      pick.append(el("span", "suggest-name", food.name), ...itemTags(food).map((t) => tagChip(t)));
      pick.addEventListener("click", () => addItem(food.name));
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
    if (!count) return;
    if (confirm("Remove " + plural(count, "checked item") + "?")) {
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

  function showScreen(screen) {
    const showLists = screen === "lists";
    if ($("listsView").hidden !== showLists) return;
    $("listView").hidden = showLists;
    $("listsView").hidden = !showLists;
    window.scrollTo(0, 0);
  }

  function onListsScreen() {
    return !!(history.state && history.state.screen === "lists");
  }

  function openLists() {
    if (!onListsScreen()) history.pushState({ screen: "lists" }, "");
    showScreen("lists");
    reload().catch(showError);
  }

  function closeLists() {
    if (onListsScreen()) history.back();  // popstate shows the list
    else showScreen("list");
  }

  function openList(id) {
    if (id !== listId) {
      listId = id;
      remember(id);
      items = [];
      isGlobal = id === GLOBAL;
      copyOf = null;
      doomed.clear();
      listName = isGlobal ? "Global" : (lists.find((l) => l.id === id) || {}).name || "";
      render();
      renderSuggestions();
    }
    closeLists();
    reload().catch(showError);
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
      plural(foods.filter((f) => f.global).length, "saved item") + " · names and tags", listId === GLOBAL, () => openList(GLOBAL), []);
    $("lists").replaceChildren(global, ...lists.map((l) => {
      const name = el("div", "name", l.name);
      if (l.template) name.append(el("span", "badge", "Template"));
      if (l.copy_of) name.append(el("span", "badge", "Copy"));
      const counts = l.count ? l.left + " to get · " + plural(l.count, "item") : "Empty";
      const buttons = [];
      if (l.template) buttons.push(button("Copy", "edit", () => openNameDialog(l)));
      buttons.push(button("Edit", "edit", () => openListEditor(l)));
      return listRow(name, l.copy_of ? "Copy of " + l.copy_of + " · " + counts : counts,
        l.id === listId, () => openList(l.id), buttons);
    }));
  }

  // ---- the tags section and the tag editor ----

  function renderTagRows() {
    $("tagRows").replaceChildren(...tags.map((t) => {
      const used = foods.filter((f) => (f.tags || []).includes(t.id)).length;
      const li = el("li", "item");
      const info = el("div", "info");
      info.append(tagChip(t), el("div", "notes", used ? plural(used, "item") : "Not on any item"));
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
    const used = foods.filter((f) => (f.tags || []).includes(t.id)).length;
    const what = used ? " It comes off " + plural(used, "item") + "." : "";
    if (!confirm("Delete the tag “" + t.name + "” for good?" + what)) return;
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
  window.addEventListener("popstate", () => showScreen(onListsScreen() ? "lists" : "list"));

  // ---- editing a list (name, template, delete) ----

  let editingList = null;

  function openListEditor(l) {
    editingList = l;
    $("listNameInput").value = l.name;
    $("listTemplate").checked = !!l.template;
    $("listError").textContent = "";
    $("deleteList").disabled = lists.length < 2;
    $("deleteList").title = lists.length < 2 ? "The only list can't be deleted" : "";
    listEditor.showModal();
  }

  $("cancelList").addEventListener("click", () => listEditor.close());

  $("listForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const l = editingList;
    const name = $("listNameInput").value.trim();
    if (!l) return listEditor.close();
    if (!name) { $("listError").textContent = "Give the list a name."; return; }
    try {
      await post("/lists/" + l.id + "/update", { name, template: $("listTemplate").checked });
    } catch (err) { $("listError").textContent = err.message; return; }
    listEditor.close();
    reload().catch(showError);
  });

  $("deleteList").addEventListener("click", () => {
    const l = editingList;
    if (!l) return;
    const what = l.count ? " and its " + plural(l.count, "item") : "";
    if (!confirm("Delete the list “" + l.name + "”" + what + "? This can't be undone.")) return;
    listEditor.close();
    act(() => post("/lists/" + l.id + "/delete"));
  });

  // ---- naming a new list or a copy of a template ----

  let copyFrom = null;  // the template being copied, or null for a new empty list

  function copyName(name) {
    const now = new Date();
    const suffix = "-" + (now.getMonth() + 1) + "/" + now.getDate();
    return name.slice(0, LIST_NAME_MAX - suffix.length) + suffix;
  }

  function openNameDialog(template) {
    copyFrom = template || null;
    $("nameTitle").textContent = copyFrom ? "Copy “" + copyFrom.name + "”" : "New list";
    $("nameOk").textContent = copyFrom ? "Copy" : "Create";
    $("nameInput").value = copyFrom ? copyName(copyFrom.name) : "";
    $("nameError").textContent = "";
    nameDialog.showModal();
  }

  $("newListButton").addEventListener("click", () => openNameDialog(null));
  $("cancelName").addEventListener("click", () => nameDialog.close());

  $("nameForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("nameInput").value.trim();
    if (!name) { $("nameError").textContent = "Give the list a name."; return; }
    let made;
    try {
      made = await post(copyFrom ? "/lists/" + copyFrom.id + "/copy" : "/lists", { name });
    } catch (err) { $("nameError").textContent = err.message; return; }
    nameDialog.close();
    openList(made.id);
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
    $("editUnit").value = item.unit || "";
    $("editAmount").value = item.amount === null || item.amount === undefined ? "" : String(item.amount);
    $("amountLabel").textContent = isGlobal ? "Default amount" : "Amount";
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

  // The "Add to global" / "Remove from global" button (list items only; it saves right away).
  function renderEditorGlobal() {
    const item = current();
    if (!item) return;
    $("globalItem").textContent = item.global ? "Remove from global" : "Add to global";
    $("globalHint").textContent = item.global ? "In the Global list." : "Not in the Global list.";
  }

  $("globalItem").addEventListener("click", () => {
    const item = current();
    if (!item || isGlobal) return;
    act(() => post("/items/" + item.id + "/update", { global: !item.global }));
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
      chip.title = tag ? "Remove this tag" : "New tag (made on Save); tap to remove";
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
    const amountText = $("editAmount").value.trim().replace(/\s+/g, " ");
    const amount = amountText === "" ? null : amountText;
    if (amountText.length > AMOUNT_MAX) {
      $("editError").textContent = "The amount can have at most " + AMOUNT_MAX + " characters.";
      return;
    }
    if (!addTypedTag()) return;  // a tag typed but not added yet counts
    const change = { name, tags: editTagNames.slice(), notes: $("editNotes").value, unit: $("editUnit").value, amount };
    const path = isGlobal ? "/foods/" + item.food + "/update" : "/items/" + item.id + "/update";
    editor.close();
    act(() => post(path, change));
  });

  $("deleteItem").addEventListener("click", () => {
    const item = current();
    if (!item) return;
    const after = item.global ? "It stays in the Global list." : "It's not in the Global list, so it's forgotten unless another list has it.";
    if (!confirm("Remove “" + item.name + "” from this list? " + after)) return;
    editor.close();
    act(() => post("/items/" + item.id + "/delete"));
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

  showScreen(onListsScreen() ? "lists" : "list");
  reload().catch(showError);
})();
