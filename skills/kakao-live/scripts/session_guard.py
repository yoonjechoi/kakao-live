#!/usr/bin/env python3
"""Fail closed when the current GUI login is locked or cannot be inspected."""
import os
import plistlib
import subprocess


def unlocked():
    try:
        p = subprocess.run(['/usr/sbin/ioreg', '-n', 'Root', '-d1', '-a'], capture_output=True, timeout=10, check=True)
        root = plistlib.loads(p.stdout)
        if isinstance(root, list):
            root = root[0] if root else {}
        if root.get('IOConsoleLocked', False):
            return False
        users = root.get('IOConsoleUsers', [])
        return any(u.get('kCGSSessionOnConsoleKey') and u.get('kCGSessionLoginDoneKey')
                   and u.get('kCGSSessionUserIDKey') == os.getuid()
                   and not u.get('CGSSessionScreenIsLocked', False) for u in users)
    except Exception:
        return False


if __name__ == '__main__':
    raise SystemExit(0 if unlocked() else 1)
