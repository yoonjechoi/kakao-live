"""ksend.sh 다시 보내기 · 화면 잠금 규칙 — 카톡 없이 돈다.

  python3 -m unittest discover -s tests -v

ksend.sh 를 임시 폴더에 복사하고 klib.sh · session_guard.py 를 가짜로 바꿔 끼운다.
kmsg 는 run_timeout 가짜가 대신 받아, 몇 번 불렸는지만 센다.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/kakao-live/scripts"

FAKE_KLIB = r'''
kroom_parse(){ KROOM_ALIAS=t; KROOM_ARGS=("$@"); }
kroom(){ case "$2" in chatId) echo 1;; *) echo t;; esac; }
kroom_verify(){ return "${VERIFY_FAIL:-0}"; }
kfocus(){ :; }
klog(){ echo "$*" >> "$LOGS"; }
now_ms(){ echo 0; }
run_timeout(){ echo call >> "$CALLS"; if [ "${KMSG_OK:-0}" = 1 ]; then echo "✓ sent"; return 0; fi; echo "INPUT_NOT_REFLECTED"; return "${KMSG_RC:-124}"; }
'''


class Ksend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "ksend.sh").write_text((SCRIPTS / "ksend.sh").read_text())
        (self.root / "klib.sh").write_text(FAKE_KLIB)
        self.guard(0)
        self.env = dict(os.environ, CALLS=str(self.root / "calls"), LOGS=str(self.root / "logs"))

    def tearDown(self):
        self.tmp.cleanup()

    def guard(self, code):
        (self.root / "session_guard.py").write_text("raise SystemExit(%d)" % code)

    def run_ksend(self, **env):
        p = subprocess.run(["bash", str(self.root / "ksend.sh"), "hi"],
                           env=dict(self.env, **env), capture_output=True, text=True, timeout=60)
        calls = (self.root / "calls").read_text().splitlines() if (self.root / "calls").exists() else []
        logs = (self.root / "logs").read_text() if (self.root / "logs").exists() else ""
        return p.returncode, len(calls), logs

    def test_default_still_retries_four_times(self):
        rc, calls, _ = self.run_ksend()
        self.assertEqual((rc, calls), (1, 4))

    def test_no_retry_tries_once_and_reports_uncertain(self):
        rc, calls, logs = self.run_ksend(KSEND_NO_RETRY="1")
        self.assertEqual((rc, calls), (2, 1))
        self.assertIn("send.uncertain", logs)

    def test_success_is_zero_either_way(self):
        self.assertEqual(self.run_ksend(KMSG_OK="1")[:2], (0, 1))
        (self.root / "calls").unlink()
        self.assertEqual(self.run_ksend(KMSG_OK="1", KSEND_NO_RETRY="1")[:2], (0, 1))

    def test_ambiguous_room_blocks_before_kmsg(self):
        rc, calls, _ = self.run_ksend(VERIFY_FAIL="1", KSEND_NO_RETRY="1")
        self.assertEqual((rc, calls), (1, 0))

    def test_locked_blocks_before_kmsg_in_both_modes(self):
        self.guard(1)
        self.assertEqual(self.run_ksend()[:2], (1, 0))
        self.assertEqual(self.run_ksend(KSEND_NO_RETRY="1")[:2], (1, 0))

    def test_unknown_session_blocks_only_in_strict_mode(self):
        self.guard(2)
        rc, calls, logs = self.run_ksend(KMSG_OK="1")
        self.assertEqual((rc, calls), (0, 1))
        self.assertIn("session.unknown", logs)
        (self.root / "calls").unlink()
        self.assertEqual(self.run_ksend(KMSG_OK="1", KSEND_NO_RETRY="1")[:2], (1, 0))


if __name__ == "__main__":
    unittest.main()
