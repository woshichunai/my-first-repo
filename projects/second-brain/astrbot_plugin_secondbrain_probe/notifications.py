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


def push(key, title, body):
    payload = json.dumps({"title": title, "body": body,
                          "group": "第二大脑", "level": "active"}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request("https://api.day.app/" + key, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            reply = json.loads(response.read(16384))
        return reply.get("code") == 200
    except Exception:
        # Network exceptions can contain the device URL. Never display or log them.
        return False



def send_saved(title, body):
    keyfile = ROOT / "device.dpapi"
    if not keyfile.exists():
        return False
    try:
        return push(protect(keyfile.read_bytes(), decrypt=True).decode("utf-8"), title, body)
    except Exception:
        return False
