"""Food list: several shopping lists plus every item name ever added, kept in <data>/lists.json,
with the pictures in <data>/images/<id>.png.

The data:
- foods: every item name ever added ({id, name, tags: [tag id]}), kept forever (removing an item
  from a list keeps its food) so the page can suggest them when adding. Food names are lowercase
  (whatever is typed is lowercased; symbols, spaces and digits are fine) and unique. Tags belong
  to the food, so they come back when it's added again and show on every list holding it.
- tags: every tag ever made ({id, name, hue}), kept forever. Names are lowercase letters and
  single spaces only, and unique; hue (0-359) is the tag's colour, picked at random when it's made
  among the hues used least so far. Setting an item's tags by name makes any new ones.
- lists: {id, name, items}; list names are unique ignoring case and there is always at least one.
  An item is {id, food (a food id), notes, checked, images}; a food is on a list at most once.
  Adding a name that's already a food reuses it; renaming an item renames its food (so the new
  name is what's suggested, and it shows on every list holding it); a rename to another food's
  name is refused.
An older list.json (one list: {"items": [{id, name, notes, checked, images}]}) becomes the list
"Food list" when lists.json doesn't exist yet; list.json itself is left as it was.

Nothing from the browser is trusted. Every value is checked here before it's kept:
- text: must be a string, normalised (NFC), control/format/private/unassigned characters dropped
  (newlines kept in notes), trimmed, and rejected when longer than the limit;
- checked: must be exactly true or false;
- ids are made here (random hex) and the browser can only name existing ones; file names are
  only ever built from those ids, never from anything the browser sends;
- images come in as raw RGB and go out as a PNG written by images.py.
Limits (lists, items per list, foods, pictures per item and in all, total data size, uploads per
hour) keep a stranger who finds the page from filling the disk. lists.json is checked the same way
when it's loaded, and image files nobody refers to are removed then.

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
LIST_NAME_MAX = 40
TAG_NAME_MAX = 24
NOTES_MAX = 500
MAX_LISTS = 30
MAX_ITEMS = 300  # per list
MAX_FOODS = 3000
MAX_TAGS = 200
MAX_TAGS_PER_ITEM = 10
HUES = range(0, 360, 30)  # colours a new tag picks from
MAX_IMAGES_PER_ITEM = 4
MAX_IMAGES = 300
MAX_DATA_BYTES = 200 * 1024 * 1024
UPLOADS_PER_HOUR = 120
DEFAULT_LIST = "Food list"

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


def food_name(value):
    """An item name as it's kept: cleaned text, lowercase."""
    return clean_text(value, NAME_MAX, label="The name").lower()[:NAME_MAX]


def tag_name(value):
    """A tag name as it's kept: lowercase letters and single spaces, or Rejected."""
    name = clean_text(value, TAG_NAME_MAX, label="A tag").lower()[:TAG_NAME_MAX]
    if not name:
        raise Rejected("Give the tag a name.")
    if not all(ch.isalpha() or ch == " " for ch in name):
        raise Rejected("Tags can only have letters and spaces.")
    return name


def free_name(name, taken, limit=NAME_MAX):
    """name, or name with " 2", " 3"... added so its lowercase isn't in taken (when loading bad data)."""
    n = 1
    candidate = name
    while candidate.lower() in taken:
        n += 1
        suffix = f" {n}"
        candidate = name[:limit - len(suffix)] + suffix
    return candidate


def write_atomic(path, data):
    tmp = path.with_name(f".{path.name}.tmp")
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path):
    """The JSON object in path, or None when it's missing or unreadable."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.images_dir = self.folder / "images"
        self.data_file = self.folder / "lists.json"
        self.old_file = self.folder / "list.json"  # before there were several lists
        self.lists = []
        self.foods = {}     # food id -> {"name", "tags": [tag id]}
        self.food_ids = {}  # name -> food id
        self.tags = {}      # tag id -> {"name", "hue"}
        self.tag_ids = {}   # name -> tag id
        self.uploads = deque()  # times of recent uploads (all users)
        self.images_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.load()

    # ---- loading and saving ----

    def load(self):
        fresh = not self.data_file.exists()
        raw = read_json(self.data_file)
        if raw is None and fresh:
            old = read_json(self.old_file) or {}
            raw = {"lists": [{"id": new_id(), "name": DEFAULT_LIST, "items": old.get("items", [])}]}
        raw = raw or {}
        self.lists, self.foods, self.food_ids, self.tags, self.tag_ids = [], {}, {}, {}, {}
        seen = set()
        for entry in raw.get("tags", []) if isinstance(raw.get("tags"), list) else []:
            if len(self.tags) >= MAX_TAGS:
                break
            try:
                self._load_tag(entry, seen)
            except Rejected:
                continue
        for entry in raw.get("foods", []) if isinstance(raw.get("foods"), list) else []:
            if len(self.foods) >= MAX_FOODS:
                break
            try:
                self._load_food(entry, seen)
            except Rejected:
                continue
        for entry in raw.get("lists", []) if isinstance(raw.get("lists"), list) else []:
            if len(self.lists) >= MAX_LISTS:
                break
            try:
                self._load_list(entry, seen)
            except Rejected:
                continue
        if not self.lists:
            self.lists.append({"id": new_id(), "name": DEFAULT_LIST, "items": []})
        referenced = {image for item in self.all_items() for image in item["images"]}
        for path in self.images_dir.iterdir():
            if path.is_file() and (path.stem not in referenced or path.suffix != ".png"):
                path.unlink(missing_ok=True)
        self.data_bytes = sum(p.stat().st_size for p in self.images_dir.iterdir() if p.is_file())
        if fresh:
            self.save()

    def _load_food(self, entry, seen):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not ID.match(entry["id"]):
            raise Rejected("bad food")
        if entry["id"] in seen:
            raise Rejected("duplicate id")
        name = free_name(food_name(entry.get("name")) or "?", self.food_ids)
        tags = []
        for tag in entry.get("tags", []) if isinstance(entry.get("tags"), list) else []:
            if isinstance(tag, str) and tag in self.tags and tag not in tags and len(tags) < MAX_TAGS_PER_ITEM:
                tags.append(tag)
        seen.add(entry["id"])
        self._set_food(entry["id"], name)
        self.foods[entry["id"]]["tags"] = tags

    def _load_tag(self, entry, seen):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not ID.match(entry["id"]):
            raise Rejected("bad tag")
        if entry["id"] in seen:
            raise Rejected("duplicate id")
        name = tag_name(entry.get("name"))
        if name in self.tag_ids:
            raise Rejected("duplicate tag")
        hue = entry.get("hue")
        if not isinstance(hue, int) or isinstance(hue, bool) or not 0 <= hue < 360:
            hue = self._new_hue()
        seen.add(entry["id"])
        self.tags[entry["id"]] = {"name": name, "hue": hue}
        self.tag_ids[name] = entry["id"]

    def _load_list(self, entry, seen):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not ID.match(entry["id"]):
            raise Rejected("bad list")
        if entry["id"] in seen:
            raise Rejected("duplicate id")
        seen.add(entry["id"])
        taken = {lst["name"].lower() for lst in self.lists}
        name = free_name(clean_text(entry.get("name"), LIST_NAME_MAX) or "List", taken, LIST_NAME_MAX)
        lst = {"id": entry["id"], "name": name, "items": []}
        on_list = set()
        for raw in entry.get("items", []) if isinstance(entry.get("items"), list) else []:
            if len(lst["items"]) >= MAX_ITEMS:
                break
            try:
                lst["items"].append(self._load_item(raw, seen, on_list))
            except Rejected:
                continue
        self.lists.append(lst)

    def _load_item(self, entry, seen, on_list):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not ID.match(entry["id"]):
            raise Rejected("bad item")
        if entry["id"] in seen:
            raise Rejected("duplicate id")
        if "food" in entry:
            food = entry["food"]
            if not isinstance(food, str) or food not in self.foods or food in on_list:
                raise Rejected("bad food")
        else:  # from the old list.json: the item has its own name
            name = food_name(entry.get("name")) or "?"
            food = self.food_ids.get(name)
            if food in on_list:
                name, food = free_name(name, self.food_ids), None
            if food is None:
                if len(self.foods) >= MAX_FOODS:
                    raise Rejected("too many foods")
                food = new_id()
                self._set_food(food, name)
        seen.add(entry["id"])
        on_list.add(food)
        pictures = []
        for image in entry.get("images", []) if isinstance(entry.get("images"), list) else []:
            if (isinstance(image, str) and ID.match(image) and image not in seen
                    and (self.images_dir / f"{image}.png").is_file()
                    and len(pictures) < MAX_IMAGES_PER_ITEM):
                seen.add(image)
                pictures.append(image)
        return {
            "id": entry["id"],
            "food": food,
            "notes": clean_text(entry.get("notes"), NOTES_MAX, multiline=True),
            "checked": entry.get("checked") is True,
            "images": pictures,
        }

    def save(self):
        data = json.dumps({
            "tags": [dict(tag, id=tag_id) for tag_id, tag in self.tags.items()],
            "foods": [{"id": food, "name": entry["name"], "tags": entry["tags"]} for food, entry in self.foods.items()],
            "lists": self.lists,
        }, ensure_ascii=False, indent=1)
        write_atomic(self.data_file, data.encode("utf-8"))

    def _set_food(self, food, name):
        """Make a food or rename one."""
        entry = self.foods.setdefault(food, {"name": name, "tags": []})
        self.food_ids.pop(entry["name"], None)
        entry["name"] = name
        self.food_ids[name] = food

    def _new_hue(self):
        used = [tag["hue"] for tag in self.tags.values()]
        counts = {hue: sum(abs((h - hue + 180) % 360 - 180) < 15 for h in used) for hue in HUES}
        least = min(counts.values())
        return secrets.choice([hue for hue, n in counts.items() if n == least])

    # ---- reading ----

    def all_items(self):
        return [item for lst in self.lists for item in lst["items"]]

    def summary(self):
        """Every list (without items) and every food name, for the lists screen and suggestions."""
        return {
            "lists": [{"id": lst["id"], "name": lst["name"], "count": len(lst["items"]),
                       "left": sum(not item["checked"] for item in lst["items"])} for lst in self.lists],
            "foods": sorted(entry["name"] for entry in self.foods.values()),
            "tags": sorted(({"id": tag_id, "name": tag["name"], "hue": tag["hue"]}
                            for tag_id, tag in self.tags.items()), key=lambda tag: tag["name"]),
        }

    def public_item(self, item):
        food = self.foods[item["food"]]
        return {"id": item["id"], "name": food["name"], "tags": list(food["tags"]), "notes": item["notes"],
                "checked": item["checked"], "images": list(item["images"])}

    def public_list(self, list_id):
        """One list with its items, plus the summary."""
        lst = self.find_list(list_id)
        items = [self.public_item(item) for item in lst["items"]]
        return dict(self.summary(), list={"id": lst["id"], "name": lst["name"], "items": items})

    def find_list(self, list_id):
        for lst in self.lists:
            if lst["id"] == list_id:
                return lst
        raise Rejected("That list is gone (someone may have deleted it).", 404)

    def find(self, item_id):
        """(list, item) for an item on any list."""
        for lst in self.lists:
            for item in lst["items"]:
                if item["id"] == item_id:
                    return lst, item
        raise Rejected("That item is gone (someone may have removed it).", 404)

    def image_path(self, image_id):
        """The file for a picture that's on a list, else None."""
        if not ID.match(image_id) or not any(image_id in item["images"] for item in self.all_items()):
            return None
        return self.images_dir / f"{image_id}.png"

    # ---- lists ----

    def _list_name(self, value, other_than=None):
        name = clean_text(value, LIST_NAME_MAX, label="The list name")
        if not name:
            raise Rejected("Give the list a name.")
        if any(lst["name"].lower() == name.lower() for lst in self.lists if lst is not other_than):
            raise Rejected(f"There's already a list called “{name}”.")
        return name

    def add_list(self, data):
        if len(self.lists) >= MAX_LISTS:
            raise Rejected(f"There are already {MAX_LISTS} lists.", 507)
        lst = {"id": new_id(), "name": self._list_name(data.get("name")), "items": []}
        self.lists.append(lst)
        self.save()
        return {"id": lst["id"], "name": lst["name"]}

    def rename_list(self, list_id, data):
        lst = self.find_list(list_id)
        lst["name"] = self._list_name(data.get("name"), other_than=lst)
        self.save()
        return {"id": lst["id"], "name": lst["name"]}

    def delete_list(self, list_id):
        lst = self.find_list(list_id)
        if len(self.lists) == 1:
            raise Rejected("That's the only list; add another one before deleting it.")
        self.lists.remove(lst)
        self.save()
        self._remove_files([image for item in lst["items"] for image in item["images"]])

    # ---- items ----

    def add(self, list_id, data):
        lst = self.find_list(list_id)
        if len(lst["items"]) >= MAX_ITEMS:
            raise Rejected(f"The list is full ({MAX_ITEMS} items).", 507)
        name = food_name(data.get("name"))
        if not name:
            raise Rejected("Give the item a name.")
        food = self.food_ids.get(name)
        if food is not None and any(item["food"] == food for item in lst["items"]):
            raise Rejected(f"“{name}” is already on this list.", 409)
        if food is None:
            if len(self.foods) >= MAX_FOODS:
                raise Rejected(f"There are already {MAX_FOODS} saved names.", 507)
            food = new_id()
            self._set_food(food, name)
        item = {"id": new_id(), "food": food,
                "notes": clean_text(data.get("notes"), NOTES_MAX, multiline=True, label="The notes"),
                "checked": False, "images": []}
        lst["items"].append(item)
        self.save()
        return self.public_item(item)

    def update(self, item_id, data):
        _, item = self.find(item_id)
        name = notes = checked = tags = None
        if "tags" in data:
            tags = self._tag_names(data["tags"])
        if "name" in data:
            name = food_name(data["name"])
            if not name:
                raise Rejected("Give the item a name.")
            other = self.food_ids.get(name)
            if other is not None and other != item["food"]:
                raise Rejected(f"There's already an item called “{name}”.", 409)
        if "notes" in data:
            notes = clean_text(data["notes"], NOTES_MAX, multiline=True, label="The notes")
        if "checked" in data:
            if not isinstance(data["checked"], bool):
                raise Rejected("Bad checked value.")
            checked = data["checked"]
        if name is not None:
            self._set_food(item["food"], name)
        if tags is not None:
            self.foods[item["food"]]["tags"] = [self._tag(tag) for tag in tags]
        if notes is not None:
            item["notes"] = notes
        if checked is not None:
            item["checked"] = checked
        self.save()
        return self.public_item(item)

    def _tag_names(self, value):
        """Checked tag names for an item (nothing is made yet)."""
        if not isinstance(value, list) or len(value) > MAX_TAGS_PER_ITEM * 2:
            raise Rejected("Bad tags.")
        names = []
        for raw in value:
            name = tag_name(raw)
            if name not in names:
                names.append(name)
        if len(names) > MAX_TAGS_PER_ITEM:
            raise Rejected(f"An item can have at most {MAX_TAGS_PER_ITEM} tags.")
        if len(self.tags) + sum(name not in self.tag_ids for name in names) > MAX_TAGS:
            raise Rejected(f"There are already {MAX_TAGS} tags.", 507)
        return names

    def _tag(self, name):
        """The id of the tag called name, made if it's new."""
        if name not in self.tag_ids:
            tag_id = new_id()
            self.tags[tag_id] = {"name": name, "hue": self._new_hue()}
            self.tag_ids[name] = tag_id
        return self.tag_ids[name]

    def delete(self, item_id):
        lst, item = self.find(item_id)
        lst["items"].remove(item)
        self.save()
        self._remove_files(item["images"])

    def clear(self, list_id, which):
        lst = self.find_list(list_id)
        if which not in ("checked", "all"):
            raise Rejected("Bad clear request.")
        gone = [item for item in lst["items"] if which == "all" or item["checked"]]
        lst["items"] = [item for item in lst["items"] if item not in gone]
        self.save()
        self._remove_files([image for item in gone for image in item["images"]])
        return len(gone)

    def add_image(self, item_id, body, now=None):
        _, item = self.find(item_id)
        if len(item["images"]) >= MAX_IMAGES_PER_ITEM:
            raise Rejected(f"An item can have at most {MAX_IMAGES_PER_ITEM} pictures.", 507)
        if sum(len(i["images"]) for i in self.all_items()) >= MAX_IMAGES:
            raise Rejected(f"The lists already have {MAX_IMAGES} pictures; remove some first.", 507)
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
        _, item = self.find(item_id)
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
