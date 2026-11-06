"""Small helpers shared by the server and by games."""

import re

# A tab's client id: a random UUID (made by web/shared/settings.js), the key to its seat and session.
CLIENT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def clean_text(value, limit):
    """Return value stripped and cut to `limit` characters, or "" if it isn't a string."""
    return value.strip()[:limit] if isinstance(value, str) else ""
