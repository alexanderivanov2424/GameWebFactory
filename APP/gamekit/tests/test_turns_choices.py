"""TurnQueue and SecretChoices."""

import unittest

from gamekit import SecretChoices, TurnQueue


class TurnQueueTests(unittest.TestCase):
    def test_round_robin_with_cost_one(self):
        queue = TurnQueue(["a", "b", "c"])
        seen = []
        for _ in range(6):
            pid = queue.current()
            seen.append(pid)
            queue.advance(pid)
        self.assertEqual(seen, ["a", "b", "c", "a", "b", "c"])

    def test_costs_and_offsets(self):
        queue = TurnQueue(["a", "b"], staggered=True)  # a=1, b=2
        queue.advance("a", 3)  # a=4
        self.assertEqual(queue.current(), "b")
        self.assertEqual(queue.offsets(), {"a": 2, "b": 0})

    def test_remove(self):
        queue = TurnQueue(["a", "b"])
        queue.remove("a")
        self.assertNotIn("a", queue)
        self.assertEqual(queue.current(), "b")
        queue.remove("b")
        self.assertIsNone(queue.current())


class SecretChoicesTests(unittest.TestCase):
    def test_hidden_until_reveal(self):
        choices = SecretChoices(["a", "b"])
        self.assertTrue(choices.choose("a", "stay"))
        self.assertFalse(choices.choose("a", "leave"))  # one pick each
        self.assertEqual(choices.public()["a"], {"chosen": True, "choice": None})
        self.assertFalse(choices.complete())
        choices.choose("b", "leave")
        self.assertTrue(choices.complete())
        self.assertEqual(choices.reveal(), {"a": "stay", "b": "leave"})
        self.assertEqual(choices.public()["b"]["choice"], "leave")

    def test_optional_choosers_hidden_until_they_pick(self):
        choices = SecretChoices(["a"], optional_ids=["x"])
        self.assertNotIn("x", choices.public())
        choices.choose("a", 1)
        self.assertTrue(choices.complete())  # nobody waits for x
        choices.choose("x", 2)
        self.assertIn("x", choices.public())

    def test_remove_unblocks(self):
        choices = SecretChoices(["a", "b"])
        choices.choose("a", 1)
        choices.remove("b")
        self.assertTrue(choices.complete())


if __name__ == "__main__":
    unittest.main()
