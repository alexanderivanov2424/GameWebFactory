"""Food list: the shopping list, kept in <data>/list.json, with its pictures in <data>/images/<id>.png.

Nothing from the browser is trusted. Every value is checked here before it's kept:
- text: must be a string, normalised (NFC), control/format/private/unassigned characters dropped
  (newlines kept in notes), trimmed, and rejected when longer than the limit;
- checked: must be exactly true or false;
- ids are made here (random hex) and the browser can only name existing ones; file names are
  only ever built from those ids, never from anything the browser sends;
- images come in as raw RGB and go out as a PNG written by images.py.
Limits (items, pictures per item and in all, total data size, uploads per hour) keep a stranger
who finds the page from filling the disk. list.json is checked the same way when it's loaded,
and image files nobody refers to are removed then.

Files are written to a temporary name and renamed, so a crash never leaves a half-written file.
"""

import json
import os
import re
import secrets
import time
import unicodedata
from collections import deque
from pathlib import Path

import images

NAME_MAX = 80
NOTES_MAX = 500
MAX_ITEMS = 300
MAX_IMAGES_PER_ITEM = 4
MAX_IMAGES = 300
MAX_DATA_BYTES = 200 * 1024 * 1024
UPLOADS_PER_HOUR = 120

ID = re.compile(r"^[0-9a-f]{16}$")
KEEP_FORMAT = {"‍"}  # zero-width joiner: needed by combined emoji


class Rejected(Exception):
    """A request we refuse; the message is shown to the user."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def new_id():
    return secrets.token_hex(8)


def clean_text(value, limit, multiline=False, label="Text"):
    """Return safe text from an untrusted value, or raise Rejected."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise Rejected(f"{label} must be text.")
    if len(value) > limit * 4:
        raise Rejected(f"{label} is too long (at most {limit} characters).")
    kept = []
    for ch in unicodedata.normalize("NFC", value):
        if ch == "\n" and multiline:
            kept.append(ch)
        elif ch in "\t\r\n":
            kept.append(" ")
        elif unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn") and ch not in KEEP_FORMAT:
            continue
        else:
            kept.append(ch)
    text = "".join(kept)
    if multiline:
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(line.strip() for line in text.split("\n")))
    else:
        text = re.sub(r" {2,}", " ", text)
    text = text.strip()
    if len(text) > limit:
        raise Rejected(f"{label} is too long (at most {limit} characters).")
    return text


def write_atomic(path, data):
    tmp = path.with_name(f".{path.name}.tmp")
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.images_dir = self.folder / "images"
        self.list_file = self.folder / "list.json"
        self.items = []
        self.uploads = deque()  # times of recent uploads (all users)
        self.images_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.load()

    # ---- loading and saving ----

    def load(self):
        raw = []
        if self.list_file.is_file():
            try:
                raw = json.loads(self.list_file.read_text(encoding="utf-8")).get("items", [])
            except (OSError, ValueError, AttributeError):
                raw = []
        self.items = []
        seen = set()
        for entry in raw if isinstance(raw, list) else []:
            try:
                item = self._clean_saved(entry, seen)
            except Rejected:
                continue
            self.items.append(item)
            if len(self.items) >= MAX_ITEMS:
                break
        referenced = {image for item in self.items for image in item["images"]}
        for path in self.images_dir.iterdir():
            if path.is_file() and (path.stem not in referenced or path.suffix != ".png"):
                path.unlink(missing_ok=True)
        self.data_bytes = sum(p.stat().st_size for p in self.images_dir.iterdir() if p.is_file())

    def _clean_saved(self, entry, seen):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not ID.match(entry["id"]):
            raise Rejected("bad item")
        if entry["id"] in seen:
            raise Rejected("duplicate item")
        seen.add(entry["id"])
        pictures = []
        for image in entry.get("images", []) if isinstance(entry.get("images"), list) else []:
            if (isinstance(image, str) and ID.match(image) and image not in seen
                    and (self.images_dir / f"{image}.png").is_file()
                    and len(pictures) < MAX_IMAGES_PER_ITEM):
                seen.add(image)
                pictures.append(image)
        return {
            "id": entry["id"],
            "name": clean_text(entry.get("name"), NAME_MAX) or "?",
            "notes": clean_text(entry.get("notes"), NOTES_MAX, multiline=True),
            "checked": entry.get("checked") is True,
            "images": pictures,
        }

    def save(self):
        data = json.dumps({"items": self.items}, ensure_ascii=False, indent=1)
        write_atomic(self.list_file, data.encode("utf-8"))

    # ---- reading ----

    def public(self):
        return {"items": [dict(item, images=list(item["images"])) for item in self.items]}

    def find(self, item_id):
        for item in self.items:
            if item["id"] == item_id:
                return item
        raise Rejected("That item is gone (someone may have removed it).", 404)

    def image_path(self, image_id):
        """The file for a picture that's on the list, else None."""
        if not ID.match(image_id) or not any(image_id in item["images"] for item in self.items):
            return None
        return self.images_dir / f"{image_id}.png"

    # ---- changes ----

    def add(self, data):
        if len(self.items) >= MAX_ITEMS:
            raise Rejected(f"The list is full ({MAX_ITEMS} items).", 507)
        name = clean_text(data.get("name"), NAME_MAX, label="The name")
        if not name:
            raise Rejected("Give the item a name.")
        item = {"id": new_id(), "name": name,
                "notes": clean_text(data.get("notes"), NOTES_MAX, multiline=True, label="The notes"),
                "checked": False, "images": []}
        self.items.append(item)
        self.save()
        return item

    def update(self, item_id, data):
        item = self.find(item_id)
        changes = {}
        if "name" in data:
            changes["name"] = clean_text(data["name"], NAME_MAX, label="The name")
            if not changes["name"]:
                raise Rejected("Give the item a name.")
        if "notes" in data:
            changes["notes"] = clean_text(data["notes"], NOTES_MAX, multiline=True, label="The notes")
        if "checked" in data:
            if not isinstance(data["checked"], bool):
                raise Rejected("Bad checked value.")
            changes["checked"] = data["checked"]
        item.update(changes)
        self.save()
        return item

    def delete(self, item_id):
        item = self.find(item_id)
        self.items.remove(item)
        self.save()
        self._remove_files(item["images"])

    def clear(self, which):
        if which not in ("checked", "all"):
            raise Rejected("Bad clear request.")
        gone = [item for item in self.items if which == "all" or item["checked"]]
        self.items = [item for item in self.items if item not in gone]
        self.save()
        self._remove_files([image for item in gone for image in item["images"]])
        return len(gone)

    def add_image(self, item_id, body, now=None):
        item = self.find(item_id)
        if len(item["images"]) >= MAX_IMAGES_PER_ITEM:
            raise Rejected(f"An item can have at most {MAX_IMAGES_PER_ITEM} pictures.", 507)
        if sum(len(i["images"]) for i in self.items) >= MAX_IMAGES:
            raise Rejected(f"The list already has {MAX_IMAGES} pictures; remove some first.", 507)
        now = time.monotonic() if now is None else now
        while self.uploads and now - self.uploads[0] > 3600:
            self.uploads.popleft()
        if len(self.uploads) >= UPLOADS_PER_HOUR:
            raise Rejected("Too many pictures uploaded in the last hour; try again later.", 429)
        try:
            png = images.encode_png(*images.parse_rgb(body))
        except images.BadImage as error:
            raise Rejected(str(error)) from None
        if self.data_bytes + len(png) > MAX_DATA_BYTES:
            raise Rejected("There's no room for more pictures; remove some first.", 507)
        self.uploads.append(now)
        image_id = new_id()
        write_atomic(self.images_dir / f"{image_id}.png", png)
        self.data_bytes += len(png)
        item["images"].append(image_id)
        self.save()
        return image_id

    def delete_image(self, item_id, image_id):
        item = self.find(item_id)
        if image_id not in item["images"]:
            raise Rejected("That picture is gone.", 404)
        item["images"].remove(image_id)
        self.save()
        self._remove_files([image_id])

    def _remove_files(self, image_ids):
        for image_id in image_ids:
            path = self.images_dir / f"{image_id}.png"
            try:
                self.data_bytes -= path.stat().st_size
                path.unlink()
            except FileNotFoundError:
                pass
