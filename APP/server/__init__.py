"""The site server (platform): WebSocket protocol, game rooms, site-wide chat, accounts and
sessions (saved player data), and the turtle emergency shutdown.

Games don't import from here; they build on the `gamekit` package. Run from the APP folder:

    python3 -m server.main
"""
