import json
from pathlib import Path
import tempfile
import unittest
from brain import Brain


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.brain = Brain(self.home)
        self.brain.capture('测试通知：高数作业；截止时间需确认')
        self.source = self.brain.db.execute('SELECT id FROM inbox').fetchone()[0]

    def tearDown(self):
        self.brain.db.close()
        self.tmp.cleanup()

    def task(self, **updates):
        row = dict(title='测试高数作业', due=None, course='高数', next_action='确认截止时间', source=self.source)
        row.update(updates)
        return row

    def test_idempotent_and_persistent(self):
        raw = json.dumps([self.task()])
        self.assertEqual(self.brain.import_tasks(raw), 1)
        self.assertEqual(self.brain.import_tasks(raw), 0)
        other = Brain(self.home)
        self.assertEqual(len(other.tasks()), 1)
        other.db.close()

    def test_invalid_batch_is_atomic(self):
        for bad in [self.task(due='2026-02-30'), self.task(source='invented'), self.task(title='')]:
            with self.assertRaises(ValueError):
                self.brain.import_tasks(json.dumps([self.task(), bad]))
            self.assertEqual(len(self.brain.tasks()), 0)

    def test_calendar_unknown_dates_completion_and_backup(self):
        self.brain.import_tasks(json.dumps([self.task(), self.task(title='中文,任务;' * 30, due='2026-11-04')]))
        path = self.home / 'tasks.ics'
        self.brain.calendar(path)
        data = path.read_bytes()
        self.assertEqual(data.count(b'BEGIN:VEVENT'), 1)
        self.assertIn(b'DTSTART;VALUE=DATE:20261104', data)
        self.assertIn(b'DTEND;VALUE=DATE:20261105', data)
        self.assertTrue(all(len(line) <= 75 for line in data.split(b'\r\n')))
        self.brain.complete(self.brain.tasks()[0]['id'])
        self.brain.calendar(path)
        self.assertNotIn(b'BEGIN:VEVENT', path.read_bytes())
        self.brain.export(self.home / 'backup.json')
        backup = json.loads((self.home / 'backup.json').read_text())
        self.assertEqual(len(backup['inbox']), 1)
        self.assertEqual(len(backup['tasks']), 2)
        self.assertIn(self.source, self.brain.prompt())


if __name__ == '__main__':
    unittest.main()
