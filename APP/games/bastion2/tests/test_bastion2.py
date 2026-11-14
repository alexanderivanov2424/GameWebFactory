"""Bastion 2: tests. Run: python3 -I tools/run_tests.py bastion2

Two layers:
- Rules tests drive logic.Match directly (fast, no lobby): set up a position, act, check.
- Lobby tests go through the real lobby with gamekit.sim.Sim, the way browsers do.
None yet: see NOTES.md for the tests proposed so far (added once the user agrees).
"""
