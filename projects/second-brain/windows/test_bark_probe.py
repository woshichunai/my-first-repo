import datetime as dt
from pathlib import Path
import tempfile
import unittest
from bark_probe import Queue, TZ, parse_address, protect


class BarkProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.sqlite3"
        self.queue = Queue(self.path)
        self.time = dt.datetime(2026, 11, 3, 12, tzinfo=TZ)

    def tearDown(self):
        self.queue.db.close()
        self.tmp.cleanup()

    def test_completion_cancels_third(self):
        run = self.queue.create(self.time)
        sent = []
        sender = lambda body: sent.append(body) is None
        self.queue.tick(self.time + dt.timedelta(seconds=30), sender)
        self.queue.tick(self.time + dt.timedelta(seconds=90), sender)
        self.queue.complete(run, self.time + dt.timedelta(seconds=91))
        self.queue.tick(self.time + dt.timedelta(seconds=181), sender)
        self.assertEqual(len(sent), 2)
        self.assertEqual([r["state"] for r in self.queue.summary()["reminders"]],
                         ["accepted", "accepted", "cancelled"])
        self.assertEqual(self.queue.latest()["phone_confirmed"], 0)

    def test_restart_coalesces_missed_and_retains_cancellation(self):
        run = self.queue.create(self.time)
        self.queue.db.close()
        self.queue = Queue(self.path)
        sent = []
        self.queue.tick(self.time + dt.timedelta(seconds=100), lambda body: sent.append(body) is None)
        self.assertEqual(len(sent), 1)
        self.assertIn("合并 2 条", sent[0])
        self.queue.complete(run, self.time + dt.timedelta(seconds=101))
        self.queue.db.close()
        self.queue = Queue(self.path)
        self.queue.tick(self.time + dt.timedelta(seconds=200), lambda body: sent.append(body) is None)
        self.assertEqual(len(sent), 1)

    def test_uncertain_delivery_not_retried_and_duplicate_run_rejected(self):
        self.queue.create(self.time)
        with self.assertRaises(ValueError):
            self.queue.create(self.time)
        sent = []
        self.queue.tick(self.time + dt.timedelta(seconds=30), lambda body: sent.append(body) and False)
        self.queue.tick(self.time + dt.timedelta(seconds=31), lambda body: sent.append(body) and False)
        self.assertEqual(len(sent), 1)
        self.assertEqual(self.queue.summary()["reminders"][0]["state"], "unknown")

    def test_local_secret_round_trip_and_address_validation(self):
        value = b"SYNTHETIC-TEST-ONLY"
        encrypted = protect(value)
        self.assertNotIn(value, encrypted)
        self.assertEqual(protect(encrypted, decrypt=True), value)
        self.assertEqual(parse_address("https://api.day.app/SYNTHETIC-TEST-ONLY/test"), value.decode())
        for invalid in ("http://api.day.app/fakekey1", "https://api.day.app.evil.invalid/fakekey1",
                        "https://evil.invalid@api.day.app/fakekey1"):
            with self.assertRaises(ValueError):
                parse_address(invalid)


if __name__ == "__main__":
    unittest.main()
