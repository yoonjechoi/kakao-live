import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import session_guard

class Safety(unittest.TestCase):
    def test_session_shapes(self):
        user={'kCGSSessionOnConsoleKey':True,'kCGSessionLoginDoneKey':True,'kCGSSessionUserIDKey':os.getuid()}
        for root in [{'IOConsoleUsers':[user]},[{'IOConsoleUsers':[user]}]]:
            with self.subTest(root=root), patch.object(session_guard.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout=plistlib.dumps(root))):
                self.assertTrue(session_guard.unlocked())
        with patch.object(session_guard.subprocess,'run',side_effect=OSError):
            self.assertFalse(session_guard.unlocked())
        with patch.object(session_guard.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout=plistlib.dumps({'IOConsoleLocked':True,'IOConsoleUsers':[user]}))):
            self.assertFalse(session_guard.unlocked())

    def test_attempt_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/'ksend.sh').write_text(Path(__file__).with_name('ksend.sh').read_text())
            (root/'session_guard.py').write_text('raise SystemExit(0)')
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

if __name__=='__main__':
    unittest.main()
