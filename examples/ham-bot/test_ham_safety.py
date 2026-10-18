import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/kakao-live/scripts"))
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / 'skills/kakao-live/scripts'

class Safety(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = patch('time.sleep')
        self.sleep_patch.start()
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['KAKAO_HOME'] = self.tmp.name
        spec = importlib.util.spec_from_file_location('ham', Path(__file__).with_name('ham_bot_runtime.py'))
        self.ham = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ham)
        self.db = self.ham.connect()
        self.db.execute("INSERT INTO meta VALUES ('cursor', ?)", (time.time()-1,))
        self.db.commit()

    def tearDown(self):
        self.sleep_patch.stop()
        self.db.close()
        self.tmp.cleanup()

    def event(self, state='pending'):
        self.db.execute('INSERT INTO events VALUES (?, ?, ?, ?)', ('123', time.time(), state, self.ham.REPLY))
        self.db.commit()

    def test_crash_after_claim_never_retries(self):
        self.event('sending')
        other = self.ham.connect()
        self.assertEqual(other.execute('SELECT state FROM events').fetchone()[0], 'uncertain')
        other.close()

    def test_locked_does_not_attempt(self):
        self.event()
        with patch.object(self.ham,'discover',return_value=1), patch.object(self.ham,'query',return_value=[]), patch.object(self.ham,'unlocked',return_value=False), patch.object(self.ham.subprocess,'run') as send:
            self.ham.tick(self.db)
            send.assert_not_called()
        self.assertEqual(self.db.execute('SELECT state FROM events').fetchone()[0], 'pending')

    def test_uncertain_stays_uncertain(self):
        self.event('uncertain')
        with patch.object(self.ham,'discover',return_value=1), patch.object(self.ham,'query',return_value=[]), patch.object(self.ham,'unlocked',return_value=True), patch.object(self.ham.subprocess,'run') as send:
            self.ham.tick(self.db)
            self.ham.tick(self.db)
            send.assert_not_called()

    def test_no_db_confirmation_never_retries(self):
        self.event()
        with patch.object(self.ham,'discover',return_value=1), patch.object(self.ham,'query',return_value=[]), patch.object(self.ham,'unlocked',return_value=True), patch.object(self.ham.subprocess,'run') as send:
            self.ham.tick(self.db)
            self.ham.tick(self.db)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[0][0], str(SCRIPTS/'ksend.sh'))
        self.assertEqual(self.db.execute('SELECT state FROM events').fetchone()[0], 'uncertain')

    def test_preflight_block_returns_pending(self):
        self.event()
        with patch.object(self.ham,'discover',return_value=1), patch.object(self.ham,'query',return_value=[]), patch.object(self.ham,'unlocked',return_value=True), patch.object(self.ham.subprocess,'run',return_value=subprocess.CompletedProcess([],1)) as send:
            self.ham.tick(self.db)
            self.assertEqual(send.call_count,1)
            self.assertEqual(send.call_args.kwargs['env']['KSEND_NO_RETRY'],'1')
        self.assertEqual(self.db.execute('SELECT state FROM events').fetchone()[0],'pending')

    def test_delayed_db_confirmation_does_not_resend(self):
        self.event()
        with patch.object(self.ham,'discover',return_value=1), patch.object(self.ham,'query',side_effect=[[],[],[[456]]]), patch.object(self.ham,'unlocked',return_value=True), patch.object(self.ham.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as send:
            self.ham.tick(self.db)
            self.assertEqual(send.call_count,1)
        self.assertEqual(self.db.execute('SELECT state FROM events').fetchone()[0],'replied')

    def test_discover_preserves_registry(self):
        path=Path(self.tmp.name)/'rooms.json'
        path.write_text(json.dumps({'me':123,'default':'other','rooms':{'other':{'chatId':2}}}))
        with patch.object(self.ham,'query',return_value=[[1,1]]):
            self.ham.discover()
        data=json.loads(path.read_text())
        self.assertEqual(data['me'],123)
        self.assertIn('other',data['rooms'])

    def test_multi_member_room_blocked(self):
        with patch.object(self.ham,'query',return_value=[[1,2]]):
            with self.assertRaises(RuntimeError):
                self.ham.discover()

    def test_unknown_session_blocks(self):
        import session_guard
        with patch.object(session_guard.subprocess, 'run', side_effect=OSError):
            self.assertFalse(session_guard.unlocked())

    def test_explicit_locked_session_blocks(self):
        import plistlib
        import session_guard
        users = [{'kCGSSessionOnConsoleKey': True, 'kCGSessionLoginDoneKey': True,
                  'kCGSSessionUserIDKey': os.getuid(), 'CGSSessionScreenIsLocked': True}]
        result = subprocess.CompletedProcess([], 0, stdout=plistlib.dumps([{'IOConsoleUsers': users}]))
        with patch.object(session_guard.subprocess, 'run', return_value=result):
            self.assertFalse(session_guard.unlocked())

    def test_dictionary_session_format(self):
        import plistlib
        import session_guard
        user = {'kCGSSessionOnConsoleKey': True, 'kCGSessionLoginDoneKey': True,
                'kCGSSessionUserIDKey': os.getuid()}
        result = subprocess.CompletedProcess([], 0, stdout=plistlib.dumps({'IOConsoleLocked': False, 'IOConsoleUsers': [user]}))
        with patch.object(session_guard.subprocess, 'run', return_value=result):
            self.assertTrue(session_guard.unlocked())

    def test_ksend_only_one_ui_attempt(self):
        root=Path(self.tmp.name)
        (root/'session_guard.py').write_text('raise SystemExit(0)')
        (root/'ksend.sh').write_text((SCRIPTS/'ksend.sh').read_text())
        (root/'klib.sh').write_text('''kroom_parse(){ KROOM_ALIAS=x; KROOM_ARGS=("$@"); }
kroom(){ echo x; }
kroom_verify(){ return "${VERIFY_FAIL:-0}"; }
klog(){ :; }
now_ms(){ echo 0; }
run_timeout(){ echo called >> "$CALLS"; return 124; }
''')
        env=dict(os.environ,KSEND_NO_RETRY='1',CALLS=str(root/'calls'))
        p=subprocess.run(['bash',str(root/'ksend.sh'),'test'],env=env,capture_output=True)
        self.assertEqual(p.returncode,2)
        self.assertEqual((root/'calls').read_text().splitlines(),['called'])
        (root/'calls').unlink()
        p=subprocess.run(['bash',str(root/'ksend.sh'),'test'],env=dict(env,VERIFY_FAIL='1'),capture_output=True)
        self.assertEqual(p.returncode,1)
        self.assertFalse((root/'calls').exists())

if __name__ == '__main__':
    unittest.main()
