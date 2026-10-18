from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import ham_bot_answers as answers
import ham_bot_rooms as rooms


class Questions(unittest.TestCase):
    def test_three_calls_per_minute_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = rooms.direct_bot({'alias':'friend','name':'Friend','chatId':123456789,'questions':True}, Path(tmp))
            db = bot.connect()
            bot.collect(db,123456789)
            bot.query = Mock(return_value=[[i,time.time()+1,'햄봇 질문'] for i in range(1,5)])
            with patch.object(answers,'answer',return_value='답') as generate:
                bot.collect(db,123456789)
                self.assertEqual(generate.call_count,3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE state='rate_limited'").fetchone()[0],1)
            db.close()

    def test_only_calls_not_bot_replies(self):
        for text in ['햄봇 2+3은?', '햄봇아 안녕', '누가 햄봇 불렀어?']:
            self.assertTrue(answers.called(text))
        for text in ['안녕하세요', '🤖 햄봇이라고 부르면 답해요', '햄봇테스트']:
            self.assertFalse(answers.called(text))

    def test_no_backlog_and_answer_saved_before_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = rooms.direct_bot({'alias':'friend','name':'Friend','chatId':123456789,'questions':True}, Path(tmp))
            db = bot.connect()
            bot.query = Mock()
            bot.collect(db, 123456789)
            bot.query.assert_not_called()
            floor = db.execute("SELECT value FROM meta WHERE key='questions_floor'").fetchone()[0]
            bot.query.return_value = [[1, floor-1, '햄봇 예전 질문'], [2, time.time()+1, '햄봇 2+3은?'], [3, time.time()+1, '🤖 햄봇 5야']]
            with patch.object(answers, 'answer', return_value='5입니다.') as generate:
                bot.collect(db, 123456789)
                bot.collect(db, 123456789)
                self.assertEqual(generate.call_count, 1)
            self.assertEqual(db.execute('SELECT id,state,answer FROM events').fetchall(), [('2','pending','5입니다.')])
            db.close()

    def test_failed_generation_never_sends_or_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = rooms.direct_bot({'alias':'friend','name':'Friend','chatId':123456789,'questions':True}, Path(tmp))
            db = bot.connect()
            bot.collect(db, 123456789)
            bot.query = Mock(return_value=[[9,time.time()+1,'햄봇 질문']])
            with patch.object(answers,'answer',side_effect=RuntimeError) as generate:
                bot.collect(db,123456789);bot.collect(db,123456789)
                self.assertEqual(generate.call_count,1)
            self.assertEqual(db.execute('SELECT state FROM events').fetchone()[0],'answer_failed')
            db.close()


if __name__ == '__main__':
    unittest.main()
