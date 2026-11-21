// Food list page (/food-list/): shows the shared list, adds/edits/checks items, uploads pictures.
// Pictures are decoded and scaled down here, then sent as raw RGB pixels only (4-byte size header
// + width*height*3 bytes, see ../images.py); the server writes its own PNG from them.
// Everything shown comes from the server and is put on the page as text (textContent), never HTML.
// The list reloads every 15 s while the page is visible and no dialog is open.
"use strict";

(() => {
  const API = "/food-list/api";
  const MAX_SIDE = 800;           // must match images.MAX_SIDE on the server
  const MAX_FILE = 40e6;          // don't even try to decode files bigger than this
  const REFRESH_MS = 15000;

  const $ = (id) => document.getElementById(id);
  const list = $("list"), editor = $("editor"), viewer = $("viewer");
  let items = [];
  let editingId = null;
  let msgTimer = 0;

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
      throw new Error(text.slice(0, 200));
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

  async function reload() {
    const data = await request("/items");
    items = Array.isArray(data && data.items) ? data.items : [];
    render();
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

  $("add").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("addName");
    const name = input.value.trim();
    if (!name) return;
    input.value = "";
    act(() => post("/items", { name }));
  });

  $("clearChecked").addEventListener("click", () => {
    const count = items.filter((i) => i.checked).length;
    if (!count) return;
    if (confirm("Remove " + count + " checked item" + (count === 1 ? "" : "s") + "?")) {
      act(() => post("/clear", { which: "checked" }));
    }
  });

  $("clearAll").addEventListener("click", () => {
    if (!items.length) return;
    if (confirm("Remove ALL " + items.length + " item" + (items.length === 1 ? "" : "s") + " from the list? This can't be undone.")) {
      act(() => post("/clear", { which: "all" }));
    }
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
    const name = $("editName").value.trim();
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

  reload().catch(showError);
})();
