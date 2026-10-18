import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('rooms', Path(__file__).with_name('ham_bot_rooms.py'))
rooms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rooms)


class DirectRooms(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bot = rooms.direct_bot({'alias': 'friend', 'name': 'Friend', 'chatId': 123456789}, Path(self.tmp.name))

    def test_identity_and_membership_fail_closed(self):
        for rows in [[], [[123456789, 3]], [[999999999, 2]], [[123456789, 2], [999999999, 2]]]:
            self.bot.query = Mock(return_value=rows)
            with self.assertRaises(RuntimeError):
                self.bot.discover()

    def test_selected_room_and_state_are_isolated(self):
        self.bot.query = Mock(return_value=[[123456789, 2]])
        self.bot.HOME.mkdir(parents=True)
        self.assertEqual(self.bot.discover(), 123456789)
        import json
        reg = json.loads((self.bot.HOME / 'rooms.json').read_text())
        self.assertEqual(reg['rooms']['friend']['chatId'], 123456789)
        self.assertEqual(reg['rooms']['friend']['search'], 'Friend')
        self.assertEqual(self.bot.HOME.parent.name, 'direct-rooms')

    def test_first_start_does_not_read_old_messages(self):
        db = self.bot.connect()
        self.addCleanup(db.close)
        self.bot.query = Mock(side_effect=AssertionError('old messages queried'))
        self.bot.collect(db, 123456789)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)

    def test_send_uses_configured_alias_and_no_retry(self):
        from unittest.mock import patch
        with patch.object(self.bot.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.bot.send('hello')
        args, kwargs = run.call_args
        self.assertEqual(args[0][1:3], ['-r', 'friend'])
        self.assertEqual(kwargs['env']['KSEND_NO_RETRY'], '1')


if __name__ == '__main__':
    unittest.main()
