"""Local-only Bark connection test; no real assignments and no model calls."""
import ctypes
from ctypes import wintypes
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import urllib.parse
import urllib.request
import uuid

TZ = dt.timezone(dt.timedelta(hours=8), "Asia/Shanghai")
ROOT = Path(os.environ.get("LOCALAPPDATA", ".")) / "SecondBrain/bark-probe"


def now():
    return dt.datetime.now(TZ)


def parse_address(value):
    url = urllib.parse.urlsplit(value.strip())
    parts = url.path.strip("/").split("/")
    if (url.scheme != "https" or url.netloc != "api.day.app" or not parts
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,200}", parts[0])):
        raise ValueError("请粘贴 Bark 中以 https://api.day.app/ 开头的设备推送地址。")
    return parts[0]


def protect(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("设备密钥仅支持 Windows 当前用户加密存储。")

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    func.restype = wintypes.BOOL
    if not func(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError("Windows 设备密钥加密/解密失败。")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel.LocalFree(output.pbData)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def push(key, body):
    payload = json.dumps({"title": "第二大脑连接测试", "body": body,
                          "group": "第二大脑连接测试", "level": "active"}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request("https://api.day.app/" + key, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            reply = json.loads(response.read(16384))
        return reply.get("code") == 200
    except Exception:
        # Network exceptions can contain the device URL. Never display or log them.
        return False


class Queue:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runs(
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, state TEXT NOT NULL,
          phone_confirmed INTEGER NOT NULL DEFAULT 0, completed_at TEXT);
        CREATE TABLE IF NOT EXISTS reminders(
          id TEXT PRIMARY KEY, run_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
          due_at TEXT NOT NULL, state TEXT NOT NULL, sent_at TEXT);
        """)
        # A crash after sending may have delivered the push. Avoid blind duplicate retries.
        with self.db:
            self.db.execute("UPDATE reminders SET state='unknown' WHERE state='sending'")

    def latest(self):
        return self.db.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()

    def create(self, timestamp):
        if self.db.execute("SELECT 1 FROM runs WHERE state='active'").fetchone():
            raise ValueError("已有测试进行中，请先完成或取消剩余提醒。")
        run_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO runs(id,created_at,state) VALUES(?,?,'active')",
                            (run_id, timestamp.isoformat()))
            self.db.executemany("INSERT INTO reminders VALUES(?,?,?,?,'pending',NULL)",
                                [(uuid.uuid4().hex, run_id, i,
                                  (timestamp + dt.timedelta(seconds=seconds)).isoformat())
                                 for i, seconds in enumerate((30, 90, 180), 1)])
        return run_id

    def complete(self, run_id, timestamp):
        with self.db:
            self.db.execute("UPDATE runs SET state='completed',completed_at=? WHERE id=?",
                            (timestamp.isoformat(), run_id))
            self.db.execute("UPDATE reminders SET state='cancelled' WHERE run_id=? AND state='pending'",
                            (run_id,))

    def confirm_phone(self, run_id):
        with self.db:
            self.db.execute("UPDATE runs SET phone_confirmed=1 WHERE id=?", (run_id,))

    def tick(self, timestamp, sender):
        run = self.latest()
        if not run or run["state"] != "active":
            return
        due = self.db.execute("SELECT * FROM reminders WHERE run_id=? AND state='pending' "
                              "AND due_at<=? ORDER BY ordinal", (run["id"], timestamp.isoformat())).fetchall()
        if not due:
            return
        ids = [r["id"] for r in due]
        with self.db:
            self.db.executemany("UPDATE reminders SET state='sending' WHERE id=?", [(i,) for i in ids])
        body = (f"第 {due[0]['ordinal']} 条测试通知。仅用于连接验证，不是真实作业。"
                if len(due) == 1 else f"合并 {len(due)} 条错过的连接测试提醒，避免连续弹窗。")
        accepted = sender(body)
        with self.db:
            self.db.executemany("UPDATE reminders SET state=?,sent_at=? WHERE id=?",
                                [("accepted" if accepted else "unknown", timestamp.isoformat(), i) for i in ids])

    def summary(self):
        run = self.latest()
        return {"run": dict(run) if run else None,
                "reminders": [dict(r) for r in self.db.execute(
                    "SELECT * FROM reminders WHERE run_id=? ORDER BY ordinal", (run["id"],))] if run else []}


def main():
    import tkinter as tk
    from tkinter import ttk, messagebox

    ROOT.mkdir(parents=True, exist_ok=True)
    queue = Queue(ROOT / "tests.sqlite3")
    keyfile = ROOT / "device.dpapi"
    key = ""
    if keyfile.exists():
        key = protect(keyfile.read_bytes(), decrypt=True).decode("utf-8")
    app = tk.Tk()
    app.title("第二大脑 · iPhone 连接测试")
    app.geometry("760x440")
    ttk.Label(app, text="iPhone 通知连接测试", font=("Microsoft YaHei UI", 18)).pack(pady=16)
    ttk.Label(app, text="在 iPhone 安装 Bark、允许通知。将设备推送地址粘贴在下方，仅在本机加密保存。\n"
              "点击开始后，30 / 90 / 180 秒各安排一条“第二大脑连接测试”。\n"
              "收到第二条后点击完成，取消第三条。关闭 ChatGPT、锁屏并使用日常网络核对。",
              justify="left").pack(pady=8)
    entry = ttk.Entry(app, show="•", width=78)
    entry.pack(pady=8)
    status = tk.StringVar(value="设备已配置；尚未开始新的测试。" if key else "等待本机输入 Bark 地址；尚未发送任何通知。")
    details = tk.StringVar()
    ttk.Label(app, textvariable=status, wraplength=700).pack(pady=8)
    ttk.Label(app, textvariable=details, wraplength=700, justify="left").pack(pady=8)
    buttons = ttk.Frame(app)
    buttons.pack(pady=8)

    def guarded(fn):
        def call():
            try:
                fn()
                render()
            except ValueError as exc:
                messagebox.showerror("请检查", str(exc))
            except Exception:
                messagebox.showerror("未完成", "本地操作失败，未显示设备地址。请保留窗口以便检查。")
        return call

    def start():
        nonlocal key
        if entry.get().strip():
            new_key = parse_address(entry.get())
            encrypted = protect(new_key.encode("utf-8"))
            temporary = keyfile.with_suffix(".tmp")
            temporary.write_bytes(encrypted)
            temporary.replace(keyfile)
            key = new_key
            entry.delete(0, "end")
        if not key:
            raise ValueError("先在此窗口粘贴 Bark 设备推送地址，不要发到聊天中。")
        queue.create(now())
        status.set("已安排三条合成测试提醒。请保持此测试窗口运行。")

    def complete():
        run = queue.latest()
        if run:
            queue.complete(run["id"], now())
            status.set("测试已完成，未发出的提醒已取消。")

    def confirm():
        run = queue.latest()
        if run:
            queue.confirm_phone(run["id"])
            status.set("已记录：用户确认在手机锁屏、日常网络下收到测试通知。")

    labels = {"pending": "等待发送", "sending": "发送中", "accepted": "服务已接受（不等于手机收到）",
              "cancelled": "已取消", "unknown": "投递结果未知，未自动重发"}

    def render():
        report = queue.summary()
        lines = [f"第 {r['ordinal']} 条 {r['due_at'][11:19]}：{labels[r['state']]}" for r in report["reminders"]]
        details.set("\n".join(lines) or "尚无测试计划。此工具仅验证连接，不是正式提醒服务。")
        (ROOT / "RESULT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def tick():
        if key:
            queue.tick(now(), lambda body: push(key, body))
        render()
        app.after(1000, tick)

    ttk.Button(buttons, text="保存并开始三条测试", command=guarded(start)).pack(side="left", padx=5)
    ttk.Button(buttons, text="标记完成 / 取消剩余", command=guarded(complete)).pack(side="left", padx=5)
    ttk.Button(buttons, text="手机锁屏已收到", command=guarded(confirm)).pack(side="left", padx=5)
    ttk.Label(app, text="密钥不会出现在聊天、命令参数或日志中。测试结束后可关闭窗口。\n"
              "重新打开可恢复未完成队列；漏发项合并，不连续补发。", justify="center").pack(pady=8)
    tick()
    app.mainloop()
    queue.db.close()


if __name__ == "__main__":
    main()
