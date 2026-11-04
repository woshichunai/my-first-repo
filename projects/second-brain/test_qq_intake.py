import datetime as dt
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from astrbot_plugin_secondbrain_probe.storage import Store, MAX_BYTES, TZ, download, file_type


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root)

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def test_pairing_owner_private_and_instance_scope(self):
        token = self.store.pairing()
        identity = ("测试机器人", "private-session", "opaque-openid")
        command = "/sb_bind " + token
        self.assertEqual(self.store.authorize(identity, command, False), "denied")
        self.assertEqual(self.store.authorize(identity, "/sb_bind wrong", True), "denied")
        self.assertEqual(self.store.authorize(identity, command, True), "bound")
        self.assertEqual(self.store.authorize(identity, "测试通知", True), "owner")
        self.assertEqual(self.store.authorize(("other-bot", *identity[1:]), command, True), "denied")
        self.assertEqual(self.store.authorize((*identity[:2], "someone-else"), command, True), "denied")
        self.assertIsNone(self.store.pairing())

    def test_expired_pairing_not_accepted(self):
        token = self.store.pairing()
        with self.store.db:
            self.store.db.execute("UPDATE settings SET value=? WHERE key='pair_expires'",
                                  ((dt.datetime.now(TZ) - dt.timedelta(minutes=1)).isoformat(),))
        self.assertEqual(self.store.authorize(("bot", "session", "openid"), "/sb_bind " + token, True), "denied")

    def test_pairing_after_astrbot_strips_wake_prefix(self):
        token = self.store.pairing()
        identity = ("bot", "session", "opaque-openid")
        self.assertEqual(self.store.authorize(identity, "sb_bind " + token, True), "bound")

    def test_source_and_blob_dedup_and_restart_retrieval(self):
        receipt, fresh = self.store.capture("bot:message1", "测试资料", ["File"])
        self.assertTrue(fresh)
        self.assertEqual(self.store.capture("bot:message1", "测试资料", ["File"]), (receipt, False))
        content = b"%PDF-1.4\nSYNTHETIC-TEST-DATA\n%%EOF"
        first = self.store.archive(receipt, "../../chapter.pdf", content)
        self.store.archive(receipt, "copy.pdf", content)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM blobs").fetchone()[0], 1)
        self.store.db.close()
        self.store = Store(self.root)
        path, name = self.store.retrieve(first)
        self.assertEqual(name, "chapter.pdf")
        self.assertTrue(path.is_relative_to(self.root))
        self.assertEqual(path.read_bytes(), content)
        path.write_bytes(b"corrupted")
        with self.assertRaises(ValueError):
            self.store.retrieve(first)

    def test_size_and_types_rejected(self):
        for name, content in (("bad.pdf", b"<html>not pdf</html>"), ("file.exe", b"MZ"),
                              ("empty.pdf", b""), ("huge.pdf", b"%PDF-" + b"a" * MAX_BYTES)):
            with self.assertRaises(ValueError):
                file_type(name, content)
        ppt = io.BytesIO()
        with zipfile.ZipFile(ppt, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("ppt/presentation.xml", "<presentation/>")
        self.assertEqual(file_type("test.pptx", ppt.getvalue()), "pptx")
        self.assertEqual(file_type("screenshot", b"\x89PNG\r\n\x1a\nSYNTHETIC"), "png")

    def test_download_cannot_read_local_or_untrusted_urls(self):
        for url in ("file:///C:/private.txt", "http://127.0.0.1/test.pdf",
                    "https://qq.com.evil.invalid/test.pdf", "https://evil@qpic.cn/test.pdf"):
            with self.assertRaises(ValueError):
                download(url)
        with patch("astrbot_plugin_secondbrain_probe.storage.socket.getaddrinfo",
                   return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ValueError):
                download("https://qpic.cn/test.pdf")


if __name__ == "__main__":
    unittest.main()
