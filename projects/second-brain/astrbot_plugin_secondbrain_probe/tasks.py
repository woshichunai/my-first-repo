"""Durable explicit reminder plans. No model calls or implicit global policy."""
import datetime as dt
import json
import sqlite3
from .storage import TZ, stamp


class Tasks:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, title TEXT NOT NULL,
          due_at TEXT, is_test INTEGER NOT NULL, state TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, task_id TEXT NOT NULL,
          due_at TEXT NOT NULL, state TEXT NOT NULL, sent_at TEXT);
        ''')
        with self.db:
            self.db.execute("UPDATE reminders SET state='unknown' WHERE state='sending'")

    def save(self, receipt, result):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO tasks VALUES(?,?,?,?,?,?)",
                (receipt, result['title'], result['due_at'], int(result['is_test']),
                 'needs_confirmation' if result['needs_confirmation'] else 'ready', stamp()))

    def plan(self, task_id, times, due=None):
        row = self.db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if not row or row['state'] == 'completed':
            raise ValueError('未找到可安排的任务。')
        if not 1 <= len(times) <= 10:
            raise ValueError('每次请明确指定 1 至 10 个提醒时间。')
        checked = []
        for value in times:
            value = dt.datetime.fromisoformat(value)
            if value.utcoffset() != dt.timedelta(hours=8) or value <= dt.datetime.now(TZ):
                raise ValueError('提醒须为未来的北京时间，格式 2026-11-06T20:00:00+08:00。')
            checked.append(value.isoformat())
        with self.db:
            self.db.execute("UPDATE reminders SET state='cancelled' WHERE task_id=? AND state='pending'", (task_id,))
            self.db.executemany("INSERT INTO reminders(task_id,due_at,state) VALUES(?,?,'pending')",
                                [(task_id, value) for value in sorted(set(checked))])
            self.db.execute("UPDATE tasks SET state='active',due_at=COALESCE(?,due_at),updated_at=? WHERE id=?",
                            (due, stamp(), task_id))

    def complete(self, task_id):
        with self.db:
            changed = self.db.execute("UPDATE tasks SET state='completed',updated_at=? WHERE id=?", (stamp(), task_id)).rowcount
            self.db.execute("UPDATE reminders SET state='cancelled' WHERE task_id=? AND state='pending'", (task_id,))
        if not changed:
            raise ValueError('未找到该任务编号。')

    def tick(self, sender):
        due = self.db.execute("SELECT r.*,t.title,t.due_at AS deadline,t.is_test FROM reminders r JOIN tasks t ON t.id=r.task_id WHERE r.state='pending' AND t.state='active' AND r.due_at<=? ORDER BY r.due_at", (stamp(),)).fetchall()
        if not due:
            return
        with self.db:
            self.db.executemany("UPDATE reminders SET state='sending' WHERE id=?", [(r['id'],) for r in due])
        # One push for missed reminders, including after restart. Unknown delivery is never blindly retried.
        lines = [('[测试] ' if r['is_test'] else '') + r['title'] + '；任务 ' + r['task_id'] for r in due]
        accepted = sender('第二大脑提醒', '\n'.join(dict.fromkeys(lines)))
        with self.db:
            self.db.executemany('UPDATE reminders SET state=?,sent_at=? WHERE id=?',
                [('accepted' if accepted else 'unknown', stamp(), r['id']) for r in due])

    def summary(self, task_id):
        task = self.db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        return {'task': dict(task) if task else None, 'reminders': [dict(r) for r in self.db.execute('SELECT due_at,state,sent_at FROM reminders WHERE task_id=? ORDER BY id', (task_id,))]}
