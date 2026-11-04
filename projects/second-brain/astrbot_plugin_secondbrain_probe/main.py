"""QQ-only intake probe: owner pairing, fixed receipts, download and retrieval."""
import asyncio
import datetime as dt
import os
import json
import urllib.parse
import urllib.request
from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import File, Image
from astrbot.api.star import Context, Star
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .storage import Store, TZ, MAX_BYTES, download
from .codex_extract import extract, ExtractionUnavailable
from .tasks import Tasks
from .notifications import send_saved


class SecondBrainProbe(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        root = Path(os.environ.get("SECOND_BRAIN_HOME", str(Path(os.environ["LOCALAPPDATA"]) / "SecondBrain")))
        self.store = Store(root / "qq-intake")
        self.store.pairing()
        self.tasks = Tasks(root / "tasks.sqlite3")
        self.scheduler_task = None
        self.lock = asyncio.Lock()
        self.model_jobs = {}
        self.model_lock = asyncio.Lock()
        self.diagnostic_task = None
        self.qq_events = 0
        self.gateway_events = {}
        self.dispatch_original = None
        self.dispatch_state = None

    @filter.on_astrbot_loaded()
    async def connection_diagnostics(self):
        async def schedule():
            while True:
                self.tasks.tick(send_saved)
                await asyncio.sleep(2)
        self.scheduler_task = asyncio.create_task(schedule())
        async def observe():
            for _ in range(48):
                report = {"checked_at": dt.datetime.now(TZ).isoformat(), "received_qq_events": self.qq_events}
                platform = self.context.get_platform("qq_official")
                if platform is not None:
                    connection = getattr(platform.client, "_connection", None)
                    if connection and self.dispatch_original is None:
                        self.dispatch_state = connection.state
                        self.dispatch_original = connection.state._dispatch
                        def track(event_name, *args):
                            self.gateway_events[event_name] = self.gateway_events.get(event_name, 0) + 1
                            return self.dispatch_original(event_name, *args)
                        connection.state._dispatch = track
                    sockets = list(platform.client._active_websockets)
                    report["websockets"] = len(sockets)
                    report["connected"] = any(ws._conn is not None and not ws._conn.closed for ws in sockets)
                    report["identified"] = any(bool(ws._session.get("session_id")) for ws in sockets)
                    report["event_sequence"] = [ws._session.get("last_seq", 0) for ws in sockets]
                    report["gateway_events"] = dict(self.gateway_events)
                (self.store.root / "CONNECTION_STATUS.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                await asyncio.sleep(5)
        self.diagnostic_task = asyncio.create_task(observe())

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def receive(self, event: AstrMessageEvent):
        if event.get_platform_name() != "qq_official":
            return
        self.qq_events += 1
        # Block QQ events from downstream agents even if pairing/receipt handling fails.
        event.stop_event()
        if not event.is_private_chat():
            return
        async with self.lock:
            identity = (event.get_platform_id(), event.get_session_id(), event.get_sender_id())
            text = event.get_message_str().strip()
            status = self.store.authorize(identity, text, True)
            if status == "denied":
                return
            if status == "bound":
                await event.send(event.plain_result(
                    "第二大脑本人私聊已绑定。请发送测试文本、截图、PDF/PPTX，并单独测试合并转发。"
                    "当前仅收件与归档验证，尚未自动创建任务或提醒。"))
                return
            if text.startswith(("完成 ", "任务 ", "提醒 ", "连接测试 ")):
                try:
                    command, arguments = text.split(" ", 1)
                    parts = arguments.split()
                    task_id = parts[0]
                    if command == "完成":
                        self.tasks.complete(task_id)
                        reply = "任务已完成，尚未发出的提醒已取消。"
                    elif command == "任务":
                        reply = json.dumps(self.tasks.summary(task_id), ensure_ascii=False, indent=2)
                    elif command == "连接测试":
                        task = self.tasks.summary(task_id)["task"]
                        if not task or not task["is_test"]:
                            raise ValueError("连接测试仅可使用已提取的测试任务。")
                        start = dt.datetime.now(TZ)
                        self.tasks.plan(task_id, [(start + dt.timedelta(seconds=n)).isoformat() for n in (30,90,180)])
                        reply = "已安排 30、90、180 秒三条测试提醒。收到第二条后回复：完成 " + task_id + "。服务接受不等于手机已收到。"
                    else:
                        self.tasks.plan(task_id, parts[1:])
                        reply = "已保存本任务明确指定的提醒时间，旧的未发提醒已取消。"
                    await event.send(event.plain_result(reply))
                except (ValueError, IndexError):
                    await event.send(event.plain_result("操作未完成。请核对任务编号和未来北京时间；提醒格式：提醒 任务编号 2026-11-06T20:00:00+08:00。"))
                return
            if text.startswith("重试收件 "):
                receipt_id = text[len("重试收件 "):].strip()
                row = self.store.db.execute("SELECT id,text FROM inbox WHERE id=?", (receipt_id,)).fetchone()
                if row is None:
                    await event.send(event.plain_result("未找到该收件编号。"))
                else:
                    await event.send(event.plain_result("正在重试提取已有原文。"))
                    self.start_extraction(event, row["id"], row["text"])
                return
            if text.startswith("取回 "):
                try:
                    path, name = self.store.retrieve(text[3:].strip())
                    await event.send(event.chain_result([File(name=name, file=str(path))]))
                except Exception:
                    await event.send(event.plain_result(
                        "文件未成功取回。请核对 12 位编号；也可能是原件校验或 QQ 文件发送失败。"))
                return
            message_id = str(getattr(event.message_obj, "message_id", "") or "")
            if not message_id:
                await event.send(event.plain_result("已看到消息，但平台未提供消息 ID，暂未归档。"))
                return
            components = event.get_messages()
            kinds = [type(c).__name__ for c in components]
            source_time = None
            raw_time = getattr(event.message_obj, "timestamp", None)
            if isinstance(raw_time, (int, float)):
                try:
                    source_time = dt.datetime.fromtimestamp(raw_time, TZ).isoformat()
                except (ValueError, OSError, OverflowError):
                    pass
            try:
                receipt, fresh = self.store.capture(event.get_platform_id() + ":" + message_id,
                                                     text, kinds, source_time)
            except ValueError:
                await event.send(event.plain_result("文本过长或来源不完整，未保存；请分条转发。"))
                return
            if fresh:
                for component in components:
                    if not isinstance(component, (File, Image)):
                        continue
                    name = getattr(component, "name", "") or ("screenshot" if isinstance(component, Image) else "attachment")
                    # File.file can trigger an unbounded SDK download, so never access it.
                    url = getattr(component, "url", "") or getattr(component, "file_", "")
                    if isinstance(component, Image) and not url:
                        url = getattr(component, "file", "")
                    try:
                        if isinstance(component, Image) and (url.startswith("file:") or Path(url).is_absolute()):
                            path = Path(urllib.request.url2pathname(urllib.parse.urlsplit(url).path)) if url.startswith("file:") else Path(url)
                            path = path.resolve()
                            cache = Path(get_astrbot_temp_path()).resolve()
                            if not path.is_relative_to(cache) or not path.is_file() or path.stat().st_size > MAX_BYTES:
                                raise ValueError("SDK 图片缓存路径或大小不符合限制")
                            content = await asyncio.to_thread(path.read_bytes)
                        else:
                            content = await asyncio.to_thread(download, url)
                        self.store.archive(receipt, name, content)
                    except Exception:
                        self.store.failed(receipt, name, "下载、大小或类型检查未通过；可重新转发附件重试")
            replies = [f"原文已收到，收件编号 {receipt}。" if fresh else f"重复消息，已有收件编号 {receipt}。"]
            for item in self.store.files(receipt):
                if item["state"] == "archived":
                    replies.append(f"已下载并保存：{item['original_name']}；取回 {item['id']}。学科/章节待分类。")
                else:
                    replies.append(f"附件未归档：{item['original_name']}。{item['detail']}。")
            if any(k in ("Forward", "Node", "Nodes") for k in kinds):
                replies.append("检测到合并转发，但尚未展开处理；请另行转发其中的通知和附件。")
            replies.append("文本将自动提取任务字段，提醒时间仍待确认。图片 OCR 与课件内容解析待接入。")
            await event.send(event.plain_result("\n".join(replies)))
            if fresh and text and not any(isinstance(c, (File, Image)) for c in components):
                self.start_extraction(event, receipt, text)

    def start_extraction(self, event, receipt, text):
        if receipt in self.model_jobs:
            return
        async def run():
            try:
                async with self.model_lock:
                    await self.extract_receipt(event, receipt, text)
            finally:
                self.model_jobs.pop(receipt, None)
        self.model_jobs[receipt] = asyncio.create_task(run())

    async def extract_receipt(self, event, receipt, text):
        self.store.extraction(receipt, "pending")
        try:
            result = await asyncio.to_thread(extract, text, self.store.root / "codex")
            self.store.extraction(receipt, "parsed", result)
            self.tasks.save(receipt, result)
            answer = [f"已提取：{result['title']}"]
            if result["is_test"]:
                answer.append("这是测试数据。")
            if result["due_at"]:
                answer.append("截止时间：" + result["due_at"])
            else:
                answer.append("截止时间待确认。")
            answer.extend(result["questions"])
            answer.append(f"任务已保存，编号 {receipt}；提醒尚未排入队列。可回复：提醒 {receipt} 具体北京时间；完成 {receipt}。")
            await event.send(event.plain_result("\n".join(answer)))
        except ExtractionUnavailable as exc:
            self.store.extraction(receipt, "pending", error=str(exc))
            await event.send(event.plain_result(str(exc) + f"。可回复：重试收件 {receipt}"))

    async def terminate(self):
        for job in list(self.model_jobs.values()):
            job.cancel()
        if self.model_jobs:
            await asyncio.gather(*list(self.model_jobs.values()), return_exceptions=True)
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        self.tasks.db.close()
        if self.diagnostic_task:
            self.diagnostic_task.cancel()
            try:
                await self.diagnostic_task
            except asyncio.CancelledError:
                pass
        if self.dispatch_original and self.dispatch_state:
            self.dispatch_state._dispatch = self.dispatch_original
        self.store.db.close()
