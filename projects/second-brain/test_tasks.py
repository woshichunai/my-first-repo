import datetime as dt
from pathlib import Path
import tempfile
import unittest
from astrbot_plugin_secondbrain_probe.tasks import Tasks
from astrbot_plugin_secondbrain_probe.storage import TZ


class TaskTests(unittest.TestCase):
    def test_restart_merge_complete_and_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tasks.db'
            queue = Tasks(path)
            result = dict(title='合成测试', due_at=None, is_test=True, needs_confirmation=False)
            queue.save('test', result)
            future = dt.datetime.now(TZ) + dt.timedelta(hours=1)
            queue.plan('test', [future.isoformat(), (future + dt.timedelta(hours=1)).isoformat()])
            queue.db.close()
            queue = Tasks(path)
            self.assertEqual(len(queue.summary('test')['reminders']), 2)
            queue.db.execute("UPDATE reminders SET due_at='2000-01-01T00:00:00+08:00'")
            queue.db.commit()
            sent = []
            queue.tick(lambda title, body: sent.append((title, body)) or True)
            queue.tick(lambda *a: self.fail('duplicate push'))
            self.assertEqual(len(sent), 1)
            queue.plan('test', [future.isoformat()])
            queue.plan('test', [(future + dt.timedelta(hours=3)).isoformat()])
            self.assertEqual([r['state'] for r in queue.summary('test')['reminders']], ['accepted','accepted','cancelled','pending'])
            queue.complete('test')
            self.assertEqual(queue.summary('test')['reminders'][-1]['state'], 'cancelled')
            queue.db.close()

    def test_unknown_not_retried_and_invalid_plan_retains_old(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = Tasks(Path(directory) / 'tasks.db')
            queue.save('test', dict(title='测试', due_at=None, is_test=True, needs_confirmation=False))
            queue.plan('test', [(dt.datetime.now(TZ) + dt.timedelta(hours=1)).isoformat()])
            with self.assertRaises(ValueError):
                queue.plan('test', ['2000-01-01T00:00:00+08:00'])
            self.assertEqual(queue.summary('test')['reminders'][0]['state'], 'pending')
            queue.db.execute("UPDATE reminders SET state='sending'")
            queue.db.commit()
            queue.db.close()
            queue = Tasks(Path(directory) / 'tasks.db')
            queue.tick(lambda *a: self.fail('unknown delivery retried'))
            self.assertEqual(queue.summary('test')['reminders'][0]['state'], 'unknown')
            queue.db.close()

if __name__ == '__main__':
    unittest.main()
