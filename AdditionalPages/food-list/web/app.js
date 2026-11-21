// Food list page (/food-list/): shows one shared list (adds/edits/checks items, uploads pictures)
// and the lists screen (the title button: open, add, rename, delete lists; the phone's Back button
// closes it). The open list is remembered in localStorage. While typing a new item, names added
// before (the server keeps them all, see ../store.py) that aren't on this list are suggested.
// Item names are lowercase: the server lowercases them too.
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
  const HEX_ID = /^[0-9a-f]{16}$/;

  const $ = (id) => document.getElementById(id);
  const list = $("list"), editor = $("editor"), viewer = $("viewer");
  let lists = [];      // [{id, name, count, left}]
  let foods = [];      // every item name ever added (sorted)
  let listId = remembered();
  let listName = "";
  let items = [];
  let editingId = null;
  let msgTimer = 0;

  function remembered() {
    try {
      const id = localStorage.getItem(CURRENT_KEY);
      return id && HEX_ID.test(id) ? id : null;
    } catch (e) { return null; }
  }

  function remember(id) {
    try { localStorage.setItem(CURRENT_KEY, id); } catch (e) { /* private mode: fine */ }
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

  // Loads the open list (or the first one, when none is open or it was deleted) and the summary.
  async function reload() {
    let data = null;
    if (listId) {
      try { data = await request("/lists/" + listId); } catch (e) { if (e.status !== 404) throw e; }
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
    items = Array.isArray(open.items) ? open.items : [];
    listName = String(open.name || "");
    if (open.id !== listId) { listId = open.id; remember(listId); }
    render();
    renderLists();
    renderSuggestions();
    if (editingId) renderEditorPics();
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

  function render() {
    $("listName").textContent = listName;
    document.title = listName || "Food list";
    const sorted = items.filter((i) => !i.checked).concat(items.filter((i) => i.checked));
    list.replaceChildren(...sorted.map(row));
    $("empty").hidden = items.length > 0;
    $("clearChecked").disabled = !items.some((i) => i.checked);
    $("clearAll").disabled = items.length === 0;
  }

  function row(item) {
    const li = el("li", "item" + (item.checked ? " done" : ""));

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
    info.append(el("div", "name", item.name));
    if (item.notes) info.append(el("div", "notes", item.notes));
    if (item.images && item.images.length) {
      const thumbs = el("div", "thumbs");
      thumbs.append(...item.images.map(thumb));
      info.append(thumbs);
    }
    info.addEventListener("click", () => openEditor(item.id));

    const edit = el("button", "edit", "Edit");
    edit.type = "button";
    edit.addEventListener("click", () => openEditor(item.id));

    li.append(check, info, edit);
    return li;
  }

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
    if (typed) {
      for (const name of foods) {
        if (name === typed || onList.has(name)) continue;
        const at = name.indexOf(typed);
        if (at === 0) starts.push(name);
        else if (at > 0) contains.push(name);
      }
    }
    const shown = starts.concat(contains).slice(0, MAX_SUGGESTIONS);
    box.replaceChildren(...shown.map((name) => {
      const li = el("li");
      const pick = el("button", "", name);
      pick.type = "button";
      pick.addEventListener("click", () => addItem(name));
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
      listName = (lists.find((l) => l.id === id) || {}).name || "";
      render();
      renderSuggestions();
    }
    closeLists();
    reload().catch(showError);
  }

  function renderLists() {
    $("lists").replaceChildren(...lists.map((l) => {
      const li = el("li", "item" + (l.id === listId ? " current" : ""));
      const info = el("div", "info");
      info.append(el("div", "name", l.name),
        el("div", "notes", l.count ? l.left + " to get · " + plural(l.count, "item") : "Empty"));
      info.addEventListener("click", () => openList(l.id));

      const rename = el("button", "edit", "Rename");
      rename.type = "button";
      rename.addEventListener("click", () => {
        const name = prompt("New name for “" + l.name + "”:", l.name);
        if (name === null || !name.trim() || name.trim() === l.name) return;
        act(() => post("/lists/" + l.id + "/update", { name: name.trim() }));
      });

      const remove = el("button", "edit danger", "Delete");
      remove.type = "button";
      remove.disabled = lists.length < 2;
      remove.title = remove.disabled ? "The only list can't be deleted" : "";
      remove.addEventListener("click", () => {
        const what = l.count ? " and its " + plural(l.count, "item") : "";
        if (confirm("Delete the list “" + l.name + "”" + what + "? This can't be undone.")) {
          act(() => post("/lists/" + l.id + "/delete"));
        }
      });

      li.append(info, rename, remove);
      return li;
    }));
  }

  $("listButton").addEventListener("click", openLists);
  $("closeLists").addEventListener("click", closeLists);
  window.addEventListener("popstate", () => showScreen(onListsScreen() ? "lists" : "list"));

  $("newList").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("newListName");
    const name = input.value.trim();
    if (!name) return;
    let made;
    try { made = await post("/lists", { name }); } catch (err) { showError(err); return; }
    input.value = "";
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
    $("busy").textContent = "";
    renderEditorPics();
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
        if (confirm("Remove this picture?")) act(() => post("/items/" + item.id + "/images/" + id + "/delete"));
      });
      box.append(img, remove);
      return box;
    });
    $("editPics").replaceChildren(...pics);
  }

  editor.addEventListener("close", () => { editingId = null; });
  $("cancelEdit").addEventListener("click", () => editor.close());

  $("editForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const item = current();
    if (!item) return editor.close();
    const name = $("editName").value.trim().toLowerCase();
    if (!name) { showError(new Error("Give the item a name.")); return; }
    const id = item.id;
    editor.close();
    act(() => post("/items/" + id + "/update", { name, notes: $("editNotes").value }));
  });

  $("deleteItem").addEventListener("click", () => {
    const item = current();
    if (!item || !confirm("Delete “" + item.name + "”?")) return;
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
        await request("/items/" + item.id + "/images", {
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
    if (document.hidden || editor.open || viewer.open) return;
    reload().catch(() => { /* quiet: try again next time */ });
  }
  setInterval(refresh, REFRESH_MS);
  document.addEventListener("visibilitychange", refresh);

  showScreen(onListsScreen() ? "lists" : "list");
  reload().catch(showError);
})();
