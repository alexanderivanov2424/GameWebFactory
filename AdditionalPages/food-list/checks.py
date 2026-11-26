"""Food list: checking values from the browser or from saved data (shared by store.py and groups.py).

Nothing from the browser is trusted: text is cleaned by clean_text (see store.py's docstring for the
rules), names are normalised here, and ids must look like ids we make (new_id).
"""

import re
import secrets
import unicodedata

NAME_MAX = 80
LIST_NAME_MAX = 40  # list and group names
TAG_NAME_MAX = 24
LIST_NAME = re.compile(r"^[A-Za-z0-9_-]+$")  # list and group names work in the address as they are
ID = re.compile(r"^[0-9a-f]{16}$")
KEEP_FORMAT = {"\u200d"}  # zero-width joiner: needed by combined emoji


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


def url_name(text):
    """A list name from older data made to fit LIST_NAME: accents dropped ("É" -> "E"), every other
    character becomes "-"."""
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9_-]", "-", text)).strip("-")[:LIST_NAME_MAX]


def free_name(name, taken, limit=NAME_MAX, sep=" "):
    """name, or name with " 2", " 3"... (sep before the number) added so its lowercase isn't in taken
    (when loading bad data)."""
    n = 1
    candidate = name
    while candidate.lower() in taken:
        n += 1
        suffix = f"{sep}{n}"
        candidate = name[:limit - len(suffix)] + suffix
    return candidate


def address_name(value, what):
    """A list or group name as typed (it's an address: letters, digits, - and _), or Rejected."""
    name = clean_text(value, LIST_NAME_MAX, label=f"The {what} name")
    if not name:
        raise Rejected(f"Give the {what} a name.")
    if not LIST_NAME.match(name):
        raise Rejected(f"{what.capitalize()} names can only have letters, digits, - and _ (no spaces): the name is the {what}'s address.")
    return name


def has_id(entry):
    return isinstance(entry, dict) and isinstance(entry.get("id"), str) and bool(ID.match(entry["id"]))
