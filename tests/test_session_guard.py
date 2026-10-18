"""session_guard.py — ioreg 출력 모양별 판정. 실제 ioreg 는 부르지 않는다."""
import plistlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/kakao-live/scripts"))
import session_guard as g  # noqa: E402

UID = 501


def user(**kw):
    u = {"kCGSSessionUserIDKey": UID, "kCGSSessionOnConsoleKey": True,
         "kCGSessionLoginDoneKey": True, "CGSSessionScreenIsLocked": False}
    u.update(kw)
    return u


def as_dict(*users):
    return plistlib.dumps({"IOConsoleUsers": list(users)})


def as_list(*users):
    return plistlib.dumps([{"IOConsoleUsers": list(users)}])


class Guard(unittest.TestCase):
    def code(self, raw):
        return g.state(raw, uid=UID)[0]

    def test_unlocked_in_both_shapes(self):
        self.assertEqual(self.code(as_dict(user())), g.UNLOCKED)
        self.assertEqual(self.code(as_list(user())), g.UNLOCKED)

    def test_locked(self):
        self.assertEqual(self.code(as_dict(user(CGSSessionScreenIsLocked=True))), g.LOCKED)

    def test_switched_away_is_locked(self):
        self.assertEqual(self.code(as_dict(user(kCGSSessionOnConsoleKey=False))), g.LOCKED)

    def test_other_users_session_does_not_count(self):
        self.assertEqual(self.code(as_dict(user(kCGSSessionUserIDKey=999))), g.UNKNOWN)

    def test_garbage_is_unknown_not_unlocked(self):
        self.assertEqual(self.code(b"not a plist"), g.UNKNOWN)
        self.assertEqual(self.code(plistlib.dumps("x")), g.UNKNOWN)

    def test_login_not_done_is_unknown(self):
        self.assertEqual(self.code(as_dict(user(kCGSessionLoginDoneKey=False))), g.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
