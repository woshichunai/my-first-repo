"""Private receipts and bounded attachment storage. No model or shell execution."""
import datetime as dt
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import urllib.parse
import urllib.request
import uuid
import zipfile

TZ = dt.timezone(dt.timedelta(hours=8), "Asia/Shanghai")
MAX_BYTES = 20 * 1024 * 1024


def stamp():
    return dt.datetime.now(TZ).isoformat()


def safe_name(value):
    name = str(value or "attachment").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    if not name or len(name) > 180:
        raise ValueError("文件名为空或过长")
    return name


def file_type(name, content):
    if not content or len(content) > MAX_BYTES:
        raise ValueError("附件为空或超过 20 MB")
    suffix = Path(name).suffix.lower()
    if content.startswith(b"%PDF-") and suffix == ".pdf":
        return "pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n") and suffix in (".png", ""):
        return "png"
    if content.startswith(b"\xff\xd8\xff") and suffix in (".jpg", ".jpeg", ""):
        return "jpg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP" and suffix in (".webp", ""):
        return "webp"
    if suffix == ".pptx" and content.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                names = {f.filename for f in members}
                if (len(members) > 2000 or sum(f.file_size for f in members) > 100 * 1024 * 1024
                        or not {"[Content_Types].xml", "ppt/presentation.xml"}.issubset(names)):
                    raise ValueError("PPTX 结构或解压大小不符合限制")
        except zipfile.BadZipFile:
            raise ValueError("PPTX 文件损坏") from None
        return "pptx"
    raise ValueError("不支持的附件类型或文件名与内容不符；当前支持 PDF、PPTX、PNG、JPEG、WebP")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download(url):
    """Only QQ attachment URLs from message components, never URLs found in text."""
    parsed = urllib.parse.urlsplit(str(url))
    host = parsed.hostname or ""
    allowed = ("qq.com", "qq.com.cn", "qpic.cn", "qlogo.cn", "gtimg.cn", "gtimg.com")
    if (len(str(url)) > 8192 or parsed.scheme not in ("https", "http") or parsed.username
            or parsed.password or parsed.port not in (None, 443)
            or not any(host == domain or host.endswith("." + domain) for domain in allowed)):
        raise ValueError("附件下载地址不在已支持的 QQ 官方域名范围")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("附件下载地址解析到非公网地址")
    secure_url = urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))
    try:
        with urllib.request.build_opener(NoRedirect).open(secure_url, timeout=20) as response:
            size = response.headers.get("Content-Length")
            if size and int(size) > MAX_BYTES:
                raise ValueError("附件超过 20 MB")
            content = response.read(MAX_BYTES + 1)
        if not content or len(content) > MAX_BYTES:
            raise ValueError("附件为空或超过 20 MB")
        return content
    except Exception:
        # Exception messages may include signed URLs; never expose them in replies/logs.
        raise ValueError("附件下载失败或超过限制；请重新转发文件以重试") from None


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "receipts.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS inbox(
          id TEXT PRIMARY KEY, message_key TEXT UNIQUE NOT NULL, text TEXT NOT NULL,
          received_at TEXT NOT NULL, source_time TEXT, kinds TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS blobs(
          sha TEXT PRIMARY KEY, relative_path TEXT NOT NULL, size INTEGER NOT NULL, kind TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attachments(
          id TEXT PRIMARY KEY, inbox_id TEXT NOT NULL, original_name TEXT NOT NULL,
          state TEXT NOT NULL, sha TEXT, detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS extractions(
          inbox_id TEXT PRIMARY KEY, state TEXT NOT NULL, output TEXT,
          error TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
        """)

    def setting(self, key):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def pairing(self):
        if self.setting("owner"):
            return None
        token = secrets.token_urlsafe(18)
        expires = (dt.datetime.now(TZ) + dt.timedelta(minutes=15)).isoformat()
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO settings VALUES(?,?)",
                                [("pair_hash", hashlib.sha256(token.encode()).hexdigest()),
                                 ("pair_expires", expires)])
        # This onboarding command is private and never packaged with source code.
        (self.root / "PAIRING.txt").write_text(
            "仅在自己的 QQ 机器人私聊发送以下整行。15 分钟有效；不要发到群里。\n\n"
            + "/sb_bind " + token + "\n", encoding="utf-8")
        return token

    def authorize(self, identity, text, private):
        if not private or not all(identity) or len(identity) != 3:
            return "denied"
        encoded = json.dumps(list(identity), ensure_ascii=False)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            owner = self.setting("owner")
            if owner:
                return "owner" if secrets.compare_digest(owner.encode(), encoded.encode()) else "denied"
            command = text[1:] if text.startswith("/") else text
            if not command.startswith("sb_bind "):
                return "denied"
            token = command[len("sb_bind "):].strip()
            expected = self.setting("pair_hash")
            expires = self.setting("pair_expires")
            if (not expected or not expires or expires < stamp()
                    or not secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(), expected)):
                return "denied"
            self.db.execute("INSERT INTO settings VALUES('owner',?)", (encoded,))
            self.db.execute("DELETE FROM settings WHERE key IN ('pair_hash','pair_expires')")
        return "bound"

    def capture(self, key, text, kinds, source_time=None):
        if not key or len(text) > 64000:
            raise ValueError("来源 ID 缺失或文本超过 64000 字符，未保存")
        previous = self.db.execute("SELECT id FROM inbox WHERE message_key=?", (key,)).fetchone()
        if previous:
            return previous[0], False
        receipt = uuid.uuid4().hex[:12]
        with self.db:
            self.db.execute("INSERT INTO inbox VALUES(?,?,?,?,?,?)",
                            (receipt, key, text, stamp(), source_time, json.dumps(kinds)))
        return receipt, True

    def archive(self, receipt, name, content):
        name = safe_name(name)
        kind = file_type(name, content)
        sha = hashlib.sha256(content).hexdigest()
        relative = Path("files") / "待分类" / "未识别章节" / (sha + "." + kind)
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != sha:
                raise ValueError("已有归档文件校验失败，请检查本机存储")
        else:
            temporary = target.with_suffix(".partial-" + uuid.uuid4().hex)
            try:
                temporary.write_bytes(content)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        attachment_id = uuid.uuid4().hex[:12]
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO blobs VALUES(?,?,?,?)",
                            (sha, relative.as_posix(), len(content), kind))
            self.db.execute("INSERT INTO attachments VALUES(?,?,?,'archived',?,'')",
                            (attachment_id, receipt, name, sha))
        return attachment_id

    def failed(self, receipt, name, detail):
        try:
            name = safe_name(name)
        except ValueError:
            name = "无法识别文件名"
        with self.db:
            self.db.execute("INSERT INTO attachments VALUES(?,?,?,'failed',NULL,?)",
                            (uuid.uuid4().hex[:12], receipt, name, detail))

    def retrieve(self, attachment_id):
        if not re.fullmatch(r"[0-9a-f]{12}", attachment_id):
            raise ValueError("请使用回执中的 12 位文件编号")
        row = self.db.execute("SELECT a.original_name,b.* FROM attachments a JOIN blobs b ON a.sha=b.sha "
                              "WHERE a.id=? AND a.state='archived'", (attachment_id,)).fetchone()
        if not row:
            raise ValueError("未找到已下载的文件")
        target = (self.root / row["relative_path"]).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError("文件索引路径无效")
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != row["sha"]:
            raise ValueError("归档原件缺失或校验失败")
        return target, row["original_name"] if Path(row["original_name"]).suffix else row["original_name"] + "." + row["kind"]

    def files(self, receipt):
        return self.db.execute("SELECT id,original_name,state,detail FROM attachments WHERE inbox_id=?",
                               (receipt,)).fetchall()

    def extraction(self, receipt, state, output=None, error=""):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO extractions VALUES(?,?,?,?,?)",
                            (receipt, state, json.dumps(output, ensure_ascii=False) if output else None,
                             error, stamp()))
