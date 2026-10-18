"""햄봇 보호 규칙 — 카톡 · kakaocli 없이 돈다.

  python3 -m unittest discover -s examples/ham-bot -v
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


class Ham(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["KAKAO_HOME"] = self.tmp.name
        spec = importlib.util.spec_from_file_location("ham", HERE / "ham_bot.py")
        self.ham = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ham)
        self.ham.CONFIRM_FOR = 0
        self.db = self.ham.connect()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def event(self, state="pending", age=0):
        self.db.execute("INSERT INTO events VALUES ('1', ?, ?, ?)", (time.time() - age, state, self.ham.REPLY))
        self.db.commit()

    def state(self):
        return self.db.execute("SELECT state FROM events").fetchone()[0]

    def deliver(self, rc, db_rows):
        with patch.object(self.ham, "discover", return_value=7), \
             patch.object(self.ham, "send", return_value=rc) as send, \
             patch.object(self.ham, "query", return_value=db_rows):
            self.ham.deliver(self.db, 7)
        return send.call_count

    def test_crash_while_sending_becomes_uncertain(self):
        self.event("sending")
        other = self.ham.connect()
        self.assertEqual(other.execute("SELECT state FROM events").fetchone()[0], "uncertain")
        other.close()

    def test_found_in_db_is_replied(self):
        self.event()
        self.assertEqual(self.deliver(0, [[9, "🤖 " + self.ham.REPLY]]), 1)
        self.assertEqual(self.state(), "replied")

    def test_emoji_variation_still_matches(self):
        self.event()
        stored = "🤖  " + self.ham.REPLY.replace("🐹", "🐹️")
        self.deliver(0, [[9, stored]])
        self.assertEqual(self.state(), "replied")

    def test_not_in_db_is_uncertain_and_never_resent(self):
        self.event()
        self.assertEqual(self.deliver(2, []), 1)
        self.assertEqual(self.state(), "uncertain")
        self.assertEqual(self.deliver(0, []), 0)  # 다음 바퀴에도 안 보낸다

    def test_blocked_before_send_stays_pending(self):
        self.event()
        self.deliver(1, [])
        self.assertEqual(self.state(), "pending")

    def test_old_greeting_expires_without_sending(self):
        self.event(age=self.ham.EXPIRE + 1)
        self.assertEqual(self.deliver(0, []), 0)
        self.assertEqual(self.state(), "expired")

    def test_first_run_ignores_history(self):
        with patch.object(self.ham, "query", return_value=[[1, 0, "햄봇 안녕"]]):
            self.ham.collect(self.db, 7)
        self.assertIsNone(self.db.execute("SELECT * FROM events").fetchone())

    def test_trigger_is_exact(self):
        self.db.execute("INSERT INTO meta VALUES ('cursor', ?)", (time.time() - 1,))
        now = time.time()
        rows = [[1, now, "햄봇 안녕"], [2, now, "햄봇 안녕하세요"], [3, now, "🤖 햄봇 안녕"]]
        with patch.object(self.ham, "query", return_value=rows):
            self.ham.collect(self.db, 7)
        self.assertEqual([r[0] for r in self.db.execute("SELECT id FROM events")], ["1"])

    def test_multi_member_room_blocks(self):
        with patch.object(self.ham, "query", return_value=[[7, 2]]):
            with self.assertRaises(RuntimeError):
                self.ham.discover()

    def test_register_keeps_existing_rooms(self):
        path = Path(self.tmp.name) / "rooms.json"
        path.write_text(json.dumps({"me": 42, "default": "work", "rooms": {"work": {"chatId": 1}}}))
        self.ham.register(7)
        reg = json.loads(path.read_text())
        self.assertEqual((reg["me"], reg["default"]), (42, "work"))
        self.assertEqual(set(reg["rooms"]), {"work", "hamtest"})


if __name__ == "__main__":
    unittest.main()
