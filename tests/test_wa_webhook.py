"""WA-0: тесты webhook-приёмника WhatsApp Cloud API.

Покрывает:
  1. verify-handshake (GET) — ок / неверный токен / неверный mode
  2. HMAC-подпись (POST) — валид / невалид / отсутствует
  3. Нормализация — text / media / echo / history / status-update
  4. Дедуп — повторный wamid пропускается (INSERT OR IGNORE)
  5. Батч — несколько сообщений в одном payload

Всё без сети и без реального .env (monkey-patch os.environ).
"""

import sys
import os
import json
import time
import hmac
import hashlib
import sqlite3
import tempfile
import threading

sys.path.insert(0, "/root/turbobaby-manager-bot")

# Мок .env до импорта модуля
os.environ.setdefault("WA_VERIFY_TOKEN",   "test_verify_token")
os.environ.setdefault("WA_APP_SECRET",     "test_secret")
os.environ.setdefault("WA_PHONE_NUMBER_ID","66999000111")

import wa_webhook as wh

res = []

def ok(cond, label):
    mark = "  PASS " if cond else "  FAIL "
    print(mark + label)
    res.append(bool(cond))
    return bool(cond)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _sign(body: bytes, secret: str = "test_secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _tmp_db() -> wh.WAQueueDB:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return wh.WAQueueDB(path)


def _make_text_payload(
    sender: str = "66812345678",
    body_text: str = "Hello",
    ts: int = None,
    our_phone: str = "",
    wamid: str = "wamid.aaa001",
) -> dict:
    ts = ts or int(time.time())
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA_1", "changes": [{
            "field": "messages",
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {
                    "display_phone_number": our_phone,
                    "phone_number_id": "PHID",
                },
                "contacts": [{"wa_id": sender, "profile": {"name": "TestUser"}}],
                "messages": [{
                    "from": sender,
                    "id":   wamid,
                    "timestamp": str(ts),
                    "type": "text",
                    "text": {"body": body_text},
                }],
            },
        }]}],
    }
    return payload


def _make_image_payload(sender="66812345678", media_id="MEDIAID123") -> dict:
    ts = int(time.time())
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "W", "changes": [{
            "field": "messages",
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": "", "phone_number_id": ""},
                "contacts": [{"wa_id": sender, "profile": {"name": "Pic"}}],
                "messages": [{
                    "from": sender, "id": "wamid.img001",
                    "timestamp": str(ts), "type": "image",
                    "image": {"id": media_id, "mime_type": "image/jpeg"},
                }],
            },
        }]}],
    }


def _make_status_payload(recipient="66812345678", status_val="delivered") -> dict:
    ts = int(time.time())
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "W", "changes": [{
            "field": "messages",
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": "", "phone_number_id": ""},
                "statuses": [{
                    "id": "wamid.status001",
                    "status": status_val,
                    "timestamp": str(ts),
                    "recipient_id": recipient,
                }],
            },
        }]}],
    }


# ─── Fake HTTP request/response infrastructure ────────────────────────────────

class _FakeRFile:
    def __init__(self, data: bytes):
        self._data = data

    def read(self, n=None):
        if n is None:
            return self._data
        result, self._data = self._data[:n], self._data[n:]
        return result


class _FakeWFile:
    def __init__(self):
        self._buf = b""

    def write(self, data):
        self._buf += data

    def flush(self):  # called by do_POST after _send(200) to push bytes before processing
        pass


class _FakeHandler(wh.WAWebhookHandler):
    """Minimal BaseHTTPRequestHandler subclass for unit tests (no real socket)."""

    def __init__(self, method, path, body=b"", headers=None):
        self.command     = method
        self.path        = path
        self.headers     = _Headers(headers or {})
        self.rfile       = _FakeRFile(body)
        self._wfile      = _FakeWFile()
        self._resp_code  = None
        self._resp_body  = b""

    def send_response(self, code):
        self._resp_code = code

    def send_header(self, *_):
        pass

    def end_headers(self):
        pass

    @property
    def wfile(self):
        return self._wfile

    @wfile.setter
    def wfile(self, v):
        self._wfile = v

    def _send(self, code, body="", content_type="text/plain"):
        self._resp_code = code
        self._resp_body = body.encode() if isinstance(body, str) else body
        # replicate parent: write raw body (tests read _resp_body)
        enc = body.encode() if isinstance(body, str) else body
        self._wfile.write(enc)


class _Headers(dict):
    def get(self, key, default=None):
        # case-insensitive lookup
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


def _dispatch(handler: _FakeHandler):
    if handler.command == "GET":
        handler.do_GET()
    elif handler.command == "POST":
        handler.do_POST()


def _make_handler(method, path, body=b"", headers=None,
                  verify_token="test_verify_token",
                  app_secret="test_secret",
                  our_phone="",
                  db=None,
                  d360_path_secret="",
                  pull_secret=""):
    h = _FakeHandler(method, path, body, headers)
    _FakeHandler.verify_token     = verify_token
    _FakeHandler.app_secret       = app_secret
    _FakeHandler.our_phone        = our_phone
    _FakeHandler.db               = db
    _FakeHandler.d360_path_secret = d360_path_secret
    # Сбрасывается КАЖДЫЙ раз намеренно: атрибуты живут на классе, и секрет, забытый прошлым
    # тестом, открыл бы дверь следующему — тест «неверный секрет → 404» врал бы зелёным.
    _FakeHandler.pull_secret      = pull_secret
    return h


# ─────────────────────────────────────────────────────────────────────────────
# 1. verify-handshake (GET)
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_handshake_ok():
    h = _make_handler("GET",
        "/wa-webhook?hub.mode=subscribe&hub.verify_token=test_verify_token&hub.challenge=CHAL_XYZ")
    _dispatch(h)
    ok(h._resp_code == 200, "handshake OK → 200")
    ok(b"CHAL_XYZ" in h._wfile._buf, "challenge echoed in body")


def test_verify_handshake_bad_token():
    h = _make_handler("GET",
        "/wa-webhook?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=C")
    _dispatch(h)
    ok(h._resp_code == 403, "bad token → 403")


def test_verify_handshake_bad_mode():
    h = _make_handler("GET",
        "/wa-webhook?hub.mode=unsubscribe&hub.verify_token=test_verify_token&hub.challenge=C")
    _dispatch(h)
    ok(h._resp_code == 403, "bad mode → 403")


def test_verify_handshake_wrong_path():
    h = _make_handler("GET", "/other-path")
    _dispatch(h)
    ok(h._resp_code == 404, "wrong path → 404")


# ─────────────────────────────────────────────────────────────────────────────
# 2. HMAC signature (POST)
# ─────────────────────────────────────────────────────────────────────────────

def test_signature_valid():
    db = _tmp_db()
    payload = _make_text_payload()
    body = json.dumps(payload).encode()
    sig = _sign(body)
    h = _make_handler("POST", "/wa-webhook", body,
                      headers={"Content-Length": str(len(body)),
                               "X-Hub-Signature-256": sig},
                      db=db)
    _dispatch(h)
    ok(h._resp_code == 200, "valid signature → 200")
    ok(db.count_pending() == 1, "event enqueued after valid signature")


def test_signature_invalid():
    db = _tmp_db()
    payload = _make_text_payload()
    body = json.dumps(payload).encode()
    h = _make_handler("POST", "/wa-webhook", body,
                      headers={"Content-Length": str(len(body)),
                               "X-Hub-Signature-256": "sha256=deadbeef"},
                      db=db)
    _dispatch(h)
    ok(h._resp_code == 403, "invalid signature → 403")
    ok(db.count_pending() == 0, "nothing enqueued on bad signature")


def test_signature_missing():
    db = _tmp_db()
    payload = _make_text_payload()
    body = json.dumps(payload).encode()
    h = _make_handler("POST", "/wa-webhook", body,
                      headers={"Content-Length": str(len(body))},
                      db=db)
    _dispatch(h)
    ok(h._resp_code == 403, "missing signature → 403")


def test_signature_skipped_when_no_secret():
    """If WA_APP_SECRET is empty → dev mode → accept without signature."""
    db = _tmp_db()
    payload = _make_text_payload()
    body = json.dumps(payload).encode()
    h = _make_handler("POST", "/wa-webhook", body,
                      headers={"Content-Length": str(len(body))},
                      app_secret="",
                      db=db)
    _dispatch(h)
    ok(h._resp_code == 200, "empty secret → dev mode → accepted")
    ok(db.count_pending() == 1, "event enqueued in dev mode")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Normalisation
# ─────────────────────────────────────────────────────────────────────────────

def test_normalize_text():
    payload = _make_text_payload(sender="66812345678", body_text="สวัสดี", wamid="wamid.n001")
    events = wh.normalize_wa_payload(payload)
    ok(len(events) == 1, "text payload → 1 event")
    ev = events[0]
    ok(ev["channel"] == "wa",         "channel=wa")
    ok(ev["from"] == "66812345678",    "from=sender")
    ok(ev["name"] == "TestUser",       "name from contacts")
    ok(ev["type"] == "text",           "type=text")
    ok(ev["text"] == "สวัสดี",         "text body preserved (Unicode)")
    ok(ev["media_id"] is None,         "media_id=None for text")
    ok(ev["ts"] > 0,                   "ts populated")
    ok(ev["echo"] is False,            "echo=False (from != our_phone)")
    ok(ev["history"] is False,         "history=False (recent)")
    ok(ev["wamid"] == "wamid.n001",    "wamid set")


def test_normalize_media_image():
    payload = _make_image_payload(media_id="MID_IMG")
    events = wh.normalize_wa_payload(payload)
    ok(len(events) == 1, "image payload → 1 event")
    ev = events[0]
    ok(ev["type"] == "image",          "type=image")
    ok(ev["media_id"] == "MID_IMG",    "media_id extracted")
    ok(ev["text"] is None,             "text=None for image")
    ok(ev["wamid"] == "wamid.img001",  "wamid from id field")


def test_normalize_echo():
    """Message FROM our own phone number → echo=True."""
    our_phone = "66999000111"
    payload = _make_text_payload(sender=our_phone, our_phone=our_phone, wamid="wamid.echo001")
    events = wh.normalize_wa_payload(payload, our_phone_number=our_phone)
    ok(len(events) == 1, "echo payload → 1 event")
    ev = events[0]
    ok(ev["echo"] is True, "echo=True when sender == our_phone")


def test_normalize_history():
    """Message with timestamp older than 24h → history=True."""
    old_ts = int(time.time()) - 86401  # 1 second beyond threshold
    payload = _make_text_payload(ts=old_ts, wamid="wamid.hist001")
    events = wh.normalize_wa_payload(payload)
    ok(len(events) == 1, "history payload → 1 event")
    ev = events[0]
    ok(ev["history"] is True, "history=True for old timestamp")
    ok(ev["ts"] == old_ts,    "original ts preserved")


def test_normalize_recent_not_history():
    """Message with current timestamp → history=False."""
    payload = _make_text_payload(ts=int(time.time()), wamid="wamid.new001")
    events = wh.normalize_wa_payload(payload)
    ev = events[0]
    ok(ev["history"] is False, "history=False for current timestamp")


def test_normalize_status():
    payload = _make_status_payload(recipient="66812345678", status_val="read")
    events = wh.normalize_wa_payload(payload)
    ok(len(events) == 1, "status payload → 1 event")
    ev = events[0]
    ok(ev["type"] == "status",          "type=status")
    ok(ev["from"] == "66812345678",     "from=recipient for status")
    ok(ev["text"] == "read",            "text=status value")
    ok(ev["echo"] is True,              "echo=True for status (we sent it)")
    ok(ev["wamid"] == "wamid.status001","wamid from status id")


def test_normalize_unknown_field_skipped():
    """Changes with field != 'messages' must be silently skipped."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "W", "changes": [
            {"field": "account_review", "value": {"some": "data"}},
        ]}],
    }
    events = wh.normalize_wa_payload(payload)
    ok(len(events) == 0, "non-messages field → 0 events")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Queue deduplication
# ─────────────────────────────────────────────────────────────────────────────

def test_queue_dedup_same_wamid():
    db = _tmp_db()
    ev = {"channel": "wa", "from": "123", "name": "", "type": "text",
          "text": "hi", "media_id": None, "ts": int(time.time()),
          "echo": False, "history": False, "wamid": "wamid.dup001", "raw": {}}
    n1 = db.enqueue([ev])
    n2 = db.enqueue([ev])  # exact duplicate
    ok(n1 == 1, "first enqueue → 1 inserted")
    ok(n2 == 0, "second enqueue with same wamid → 0 inserted (dedup)")
    ok(db.count_pending() == 1, "only 1 row in db")


def test_queue_null_wamid_not_deduped():
    """Events without wamid (e.g. status events with None) are not deduplicated."""
    db = _tmp_db()
    ev = {"channel": "wa", "from": "123", "name": "", "type": "status",
          "text": "delivered", "media_id": None, "ts": int(time.time()),
          "echo": True, "history": False, "wamid": None, "raw": {}}
    db.enqueue([ev])
    db.enqueue([ev])
    # NULL is not equal to NULL in UNIQUE index → two rows allowed
    ok(db.count_pending() == 2, "null wamid → not deduplicated (two rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Batch (multiple messages in one payload)
# ─────────────────────────────────────────────────────────────────────────────

def test_normalize_batch_multiple_messages():
    ts = int(time.time())
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "W", "changes": [{
            "field": "messages",
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": "", "phone_number_id": ""},
                "contacts": [
                    {"wa_id": "AAA", "profile": {"name": "Alice"}},
                    {"wa_id": "BBB", "profile": {"name": "Bob"}},
                ],
                "messages": [
                    {"from": "AAA", "id": "wamid.b001", "timestamp": str(ts),
                     "type": "text", "text": {"body": "hi"}},
                    {"from": "BBB", "id": "wamid.b002", "timestamp": str(ts),
                     "type": "text", "text": {"body": "hello"}},
                ],
                "statuses": [
                    {"id": "wamid.b003", "status": "sent", "timestamp": str(ts),
                     "recipient_id": "CCC"},
                ],
            },
        }]}],
    }
    events = wh.normalize_wa_payload(payload)
    ok(len(events) == 3, "batch: 2 messages + 1 status → 3 events")
    types = [e["type"] for e in events]
    ok("text" in types, "batch includes text events")
    ok("status" in types, "batch includes status event")
    names = {e["name"] for e in events if e["type"] == "text"}
    ok(names == {"Alice", "Bob"}, "contact names resolved correctly")


def test_batch_enqueue_and_count():
    db = _tmp_db()
    ts = int(time.time())
    events = [
        {"channel": "wa", "from": "A", "name": "A", "type": "text",
         "text": "1", "media_id": None, "ts": ts, "echo": False,
         "history": False, "wamid": "wamid.e001", "raw": {}},
        {"channel": "wa", "from": "B", "name": "B", "type": "text",
         "text": "2", "media_id": None, "ts": ts, "echo": False,
         "history": False, "wamid": "wamid.e002", "raw": {}},
    ]
    n = db.enqueue(events)
    ok(n == 2, "2 distinct events → 2 inserted")
    ok(db.count_pending() == 2, "count_pending == 2")


# ─────────────────────────────────────────────────────────────────────────────
# 6. verify_signature standalone tests
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_signature_correct():
    body = b'{"test":1}'
    sig = _sign(body, "mysecret")
    ok(wh.verify_signature(body, sig, "mysecret"), "correct HMAC accepted")


def test_verify_signature_wrong_secret():
    body = b'{"test":1}'
    sig = _sign(body, "wrongsecret")
    ok(not wh.verify_signature(body, sig, "mysecret"), "wrong secret rejected")


def test_verify_signature_tampered_body():
    body = b'{"test":1}'
    sig = _sign(body, "sec")
    ok(not wh.verify_signature(b'{"test":2}', sig, "sec"), "tampered body rejected")


def test_verify_signature_empty_secret_dev_mode():
    ok(wh.verify_signature(b"anything", "", ""), "empty secret → dev mode → True")
    ok(wh.verify_signature(b"anything", "sha256=bad", ""), "empty secret → True even w/ bad sig")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Concurrency — ThreadingHTTPServer
# ─────────────────────────────────────────────────────────────────────────────

def test_make_server_is_threaded():
    """make_server() returns ThreadingHTTPServer with daemon_threads=True."""
    from http.server import ThreadingHTTPServer
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    env = {"verify_token": "tok", "app_secret": "", "phone_id": "",
           "port": 0, "queue_db": db_path}
    server = wh.make_server(env)
    try:
        ok(isinstance(server, ThreadingHTTPServer), "make_server → ThreadingHTTPServer")
        ok(getattr(server, "daemon_threads", False) is True, "daemon_threads=True")
    finally:
        server.server_close()
        try:
            os.remove(db_path)
        except Exception:
            pass


def test_200_before_db_write():
    """200 is sent and flushed before db.enqueue(); an enqueue error doesn't change the 200."""
    class _FailDB:
        def enqueue(self, events):
            raise RuntimeError("simulated db failure")
        def count_pending(self):
            return 0

    payload = _make_text_payload()
    body = json.dumps(payload).encode()
    sig = _sign(body)
    h = _make_handler("POST", "/wa-webhook", body,
                      headers={"Content-Length": str(len(body)),
                               "X-Hub-Signature-256": sig},
                      db=_FailDB())
    _dispatch(h)
    ok(h._resp_code == 200, "200 sent even when db.enqueue raises after response")
    ok(b"ok" in h._wfile._buf, "response body 'ok' in buffer before db error")


def test_parallel_requests_no_blocking():
    """ThreadingHTTPServer: fast GET completes while a slow POST enqueue runs in its thread."""
    import urllib.request as _ur
    from http.server import ThreadingHTTPServer

    fast_done = threading.Event()
    slow_started = threading.Event()

    class _SlowDB:
        def enqueue(self, events):
            slow_started.set()
            fast_done.wait(timeout=4)  # block until GET completes
            return 1
        def count_pending(self):
            return 0

    class _H(wh.WAWebhookHandler):
        pass
    _H.verify_token = "tok"
    _H.app_secret = ""
    _H.our_phone = ""
    _H.db = _SlowDB()

    server = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    server.daemon_threads = True
    port = server.server_address[1]
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()

    payload = _make_text_payload()
    body = json.dumps(payload).encode()

    post_status = {}
    def _post():
        try:
            req = _ur.Request(
                "http://127.0.0.1:" + str(port) + "/wa-webhook",
                data=body,
                method="POST",
                headers={"Content-Length": str(len(body))}
            )
            with _ur.urlopen(req, timeout=8) as resp:
                post_status["code"] = resp.status
        except Exception as e:
            post_status["err"] = str(e)

    post_t = threading.Thread(target=_post, daemon=True)
    post_t.start()

    slow_started.wait(timeout=3)  # wait for slow enqueue to start

    # Now send a fast GET while slow POST enqueue is blocking
    get_status = {}
    t0 = time.time()
    try:
        url = ("http://127.0.0.1:" + str(port)
               + "/wa-webhook?hub.mode=subscribe&hub.verify_token=tok&hub.challenge=FAST42")
        with _ur.urlopen(url, timeout=5) as resp:
            gbody = resp.read().decode()
            get_status["code"] = resp.status
            get_status["body"] = gbody
    except Exception as e:
        get_status["err"] = str(e)
    get_elapsed = time.time() - t0

    fast_done.set()      # release slow enqueue
    post_t.join(timeout=5)
    server.shutdown()

    ok(get_status.get("code") == 200,
       "fast GET returns 200 while slow enqueue blocks in its thread (code=" + str(get_status.get("code")) + ")")
    ok("FAST42" in get_status.get("body", ""),
       "fast GET challenge echoed: " + repr(get_status.get("body", "")[:20]))
    ok(get_elapsed < 2.0,
       "fast GET completed in " + ("%.2f" % get_elapsed) + "s (parallel, not waiting for enqueue)")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Health probe + watchdog
# ─────────────────────────────────────────────────────────────────────────────

import urllib.parse as _up

def test_wa_probe_ok():
    """_wa_probe returns True when a real server responds with the challenge."""
    import urllib.parse as _up2
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
    import health as _health

    class _MockH(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args): pass
        def do_GET(self):
            q = _up2.parse_qs(_up2.urlparse(self.path).query)
            ch = (q.get("hub.challenge") or [""])[0]
            mode = (q.get("hub.mode") or [""])[0]
            tok = (q.get("hub.verify_token") or [""])[0]
            if mode == "subscribe" and tok == "tok":
                enc = ch.encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(enc)))
                self.end_headers()
                self.wfile.write(enc)
            else:
                self.send_response(403)
                self.end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _MockH)
    srv.daemon_threads = True
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    result, detail = _health._wa_probe(port, "tok", timeout=3)
    srv.shutdown()

    ok(result is True, "probe OK when server responds to handshake: " + detail)


def test_wa_probe_hung():
    """_wa_probe returns False when server accepts TCP but never sends HTTP response."""
    import socket as _sk

    srv = _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM)
    srv.setsockopt(_sk.SOL_SOCKET, _sk.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _absorb():
        try:
            conn, _ = srv.accept()
            time.sleep(2)   # accept but don't reply
            conn.close()
        except Exception:
            pass

    threading.Thread(target=_absorb, daemon=True).start()

    import health as _health
    result, detail = _health._wa_probe(port, "tok", timeout=0.5)
    srv.close()

    ok(result is False, "probe fails when server accepts TCP but doesn't respond: " + detail)


def test_watchdog_count_and_reset():
    """_wa_watchdog_count/_set/_reset manage the state file correctly."""
    import health as _health

    orig_file = _health._WA_PROBE_FAIL_FILE
    fd, tmp = tempfile.mkstemp(suffix=".wdog")
    os.close(fd)
    os.remove(tmp)
    _health._WA_PROBE_FAIL_FILE = tmp
    try:
        ok(_health._wa_watchdog_count() == 0, "fresh state: count=0 (file absent)")
        _health._wa_watchdog_set(1)
        ok(_health._wa_watchdog_count() == 1, "count=1 after _wa_watchdog_set(1)")
        _health._wa_watchdog_reset()
        ok(_health._wa_watchdog_count() == 0, "count=0 after _wa_watchdog_reset()")
    finally:
        _health._WA_PROBE_FAIL_FILE = orig_file
        try:
            os.remove(tmp)
        except Exception:
            pass


def test_watchdog_increments_on_consecutive_failures():
    """Watchdog state file increments on each probe failure, resets on success."""
    import health as _health

    orig_file = _health._WA_PROBE_FAIL_FILE
    fd, tmp = tempfile.mkstemp(suffix=".wdog2")
    os.close(fd)
    os.remove(tmp)
    _health._WA_PROBE_FAIL_FILE = tmp
    try:
        _health._wa_watchdog_reset()
        fails1 = _health._wa_watchdog_count() + 1
        _health._wa_watchdog_set(fails1)
        ok(fails1 == 1, "first failure: count=1")

        fails2 = _health._wa_watchdog_count() + 1
        _health._wa_watchdog_set(fails2)
        ok(fails2 == 2, "second failure: count=2 (= threshold)")

        _health._wa_watchdog_reset()
        ok(_health._wa_watchdog_count() == 0, "after reset (simulate restart): count=0")
    finally:
        _health._WA_PROBE_FAIL_FILE = orig_file
        try:
            os.remove(tmp)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 9. 360dialog v1 — webhook path + payload normalisation
# ─────────────────────────────────────────────────────────────────────────────

_D360_SECRET = "teststest1234abcd"  # fixed test secret


def _make_d360_text_payload(
    sender: str = "66812345678",
    body_text: str = "Hello 360",
    ts: int = None,
    wamid: str = "d360.msg001",
) -> dict:
    """360dialog v1 flat format — no entry/changes wrapper."""
    ts = ts or int(time.time())
    return {
        "contacts": [{"wa_id": sender, "profile": {"name": "D360User"}}],
        "messages": [{
            "from":      sender,
            "id":        wamid,
            "timestamp": str(ts),
            "type":      "text",
            "text":      {"body": body_text},
        }],
    }


def _make_d360_image_payload(sender="66812345678", media_id="MEDIA456") -> dict:
    ts = int(time.time())
    return {
        "contacts": [{"wa_id": sender, "profile": {"name": "D360Img"}}],
        "messages": [{
            "from": sender, "id": "d360.img001", "timestamp": str(ts),
            "type": "image", "image": {"id": media_id, "mime_type": "image/jpeg"},
        }],
    }


def _make_d360_status_payload(recipient="66812345678", status_val="delivered") -> dict:
    ts = int(time.time())
    return {
        "statuses": [{
            "id":           "d360.st001",
            "status":       status_val,
            "timestamp":    str(ts),
            "recipient_id": recipient,
        }],
    }


def test_d360_correct_secret_200():
    """Correct secret in path → 200, event enqueued."""
    db = _tmp_db()
    payload = _make_d360_text_payload()
    body = json.dumps(payload).encode()
    path = f"/wa-webhook/d360/{_D360_SECRET}"
    h = _make_handler("POST", path, body,
                      headers={"Content-Length": str(len(body))},
                      app_secret="",
                      db=db,
                      d360_path_secret=_D360_SECRET)
    _dispatch(h)
    ok(h._resp_code == 200, "d360 correct secret → 200")
    ok(db.count_pending() == 1, "d360 event enqueued")


def test_d360_wrong_secret_404():
    """Wrong secret in path → 404 (not 401 — don't reveal endpoint)."""
    db = _tmp_db()
    payload = _make_d360_text_payload()
    body = json.dumps(payload).encode()
    path = "/wa-webhook/d360/wrong_secret_xyz"
    h = _make_handler("POST", path, body,
                      headers={"Content-Length": str(len(body))},
                      app_secret="",
                      db=db,
                      d360_path_secret=_D360_SECRET)
    _dispatch(h)
    ok(h._resp_code == 404, "d360 wrong secret → 404")
    ok(db.count_pending() == 0, "nothing enqueued on wrong secret")


def test_d360_no_secret_configured_404():
    """If server has no d360_path_secret set, any d360 path → 404."""
    db = _tmp_db()
    payload = _make_d360_text_payload()
    body = json.dumps(payload).encode()
    path = f"/wa-webhook/d360/{_D360_SECRET}"
    h = _make_handler("POST", path, body,
                      headers={"Content-Length": str(len(body))},
                      app_secret="",
                      db=db,
                      d360_path_secret="")   # not configured
    _dispatch(h)
    ok(h._resp_code == 404, "d360 path → 404 when server has no secret configured")


def test_meta_path_still_needs_hmac():
    """Meta path /wa-webhook still requires HMAC even when d360 is active."""
    db = _tmp_db()
    # Post a payload to the Meta path WITHOUT a signature
    payload = _make_text_payload()
    body = json.dumps(payload).encode()
    h = _make_handler("POST", "/wa-webhook", body,
                      headers={"Content-Length": str(len(body))},
                      app_secret="test_secret",
                      db=db,
                      d360_path_secret=_D360_SECRET)
    _dispatch(h)
    ok(h._resp_code == 403, "meta path still rejects POST without HMAC when d360 is configured")
    ok(db.count_pending() == 0, "nothing enqueued on missing HMAC for meta path")


def test_d360_dedup_same_wamid():
    """360dialog events deduplicate by wamid just like Meta events."""
    db = _tmp_db()
    payload = _make_d360_text_payload(wamid="d360.dup999")
    body = json.dumps(payload).encode()
    path = f"/wa-webhook/d360/{_D360_SECRET}"
    h1 = _make_handler("POST", path, body,
                       headers={"Content-Length": str(len(body))},
                       app_secret="", db=db, d360_path_secret=_D360_SECRET)
    h2 = _make_handler("POST", path, body,
                       headers={"Content-Length": str(len(body))},
                       app_secret="", db=db, d360_path_secret=_D360_SECRET)
    _dispatch(h1)
    _dispatch(h2)
    ok(db.count_pending() == 1, "d360 duplicate wamid → only 1 row in db")


# ── normalize_d360_v1_payload unit tests ──────────────────────────────────────

def test_normalize_d360_v1_text():
    payload = _make_d360_text_payload(sender="66812345678",
                                      body_text="สวัสดี 360", wamid="d360.n001")
    events = wh.normalize_d360_v1_payload(payload)
    ok(len(events) == 1,               "d360 text payload → 1 event")
    ev = events[0]
    ok(ev["channel"] == "wa",          "d360: channel=wa")
    ok(ev["from"] == "66812345678",    "d360: from=sender")
    ok(ev["name"] == "D360User",       "d360: name from contacts")
    ok(ev["type"] == "text",           "d360: type=text")
    ok(ev["text"] == "สวัสดี 360",     "d360: text body (Unicode)")
    ok(ev["wamid"] == "d360.n001",     "d360: wamid set")
    ok(ev["echo"] is False,            "d360: echo=False (sandbox = real user)")
    ok(ev["media_id"] is None,         "d360: media_id=None for text")


def test_normalize_d360_v1_image():
    payload = _make_d360_image_payload(media_id="MEDIA456")
    events = wh.normalize_d360_v1_payload(payload)
    ok(len(events) == 1,               "d360 image payload → 1 event")
    ev = events[0]
    ok(ev["type"] == "image",          "d360: type=image")
    ok(ev["media_id"] == "MEDIA456",   "d360: media_id extracted")
    ok(ev["text"] is None,             "d360: text=None for image")


def test_normalize_d360_v1_status():
    payload = _make_d360_status_payload(status_val="read")
    events = wh.normalize_d360_v1_payload(payload)
    ok(len(events) == 1,                    "d360 status payload → 1 event")
    ev = events[0]
    ok(ev["type"] == "status",              "d360: type=status")
    ok(ev["text"] == "read",                "d360: text=status value")
    ok(ev["echo"] is True,                  "d360: echo=True for status")
    ok(ev["wamid"] == "d360.st001",         "d360: wamid from status id")
    ok(ev["from"] == "66812345678",         "d360: from=recipient_id")


def test_normalize_d360_v1_empty():
    """Empty payload → 0 events, no crash."""
    events = wh.normalize_d360_v1_payload({})
    ok(len(events) == 0, "d360 empty payload → 0 events")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Bind — слушаем loopback, наружу только через Caddy
# ─────────────────────────────────────────────────────────────────────────────

def test_bind_default_is_loopback():
    ok(wh.bind_host(None) == "127.0.0.1", "переменной нет → 127.0.0.1")
    ok(wh.bind_host("") == "127.0.0.1", "пусто → 127.0.0.1")
    ok(wh.bind_host("   ") == "127.0.0.1", "пробелы → 127.0.0.1 (опечатка не публикует порт)")


def test_bind_explicit_is_honoured():
    """Явно названный адрес уважается — иначе ручки отката не было бы вовсе."""
    ok(wh.bind_host("0.0.0.0") == "0.0.0.0", "явный 0.0.0.0 → 0.0.0.0")
    ok(wh.bind_host(" 10.0.0.5 ") == "10.0.0.5", "адрес с пробелами по краям очищается")


def test_make_server_binds_loopback():
    """Живой сокет: сервер без WA_BIND_HOST поднимается на петле, а не на всех интерфейсах."""
    fd, dbp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    env = {"verify_token": "t", "app_secret": "", "phone_id": "", "port": 0,
           "queue_db": dbp, "d360_path_secret": "", "pull_secret": ""}
    srv = wh.make_server(env)
    try:
        ok(srv.server_address[0] == "127.0.0.1",
           "make_server слушает 127.0.0.1, а не 0.0.0.0 (адрес=" + str(srv.server_address[0]) + ")")
    finally:
        srv.server_close()
        os.remove(dbp)


def test_no_hardcoded_wildcard_bind():
    """Регресс: адрес всех интерфейсов не вшит в код — он приходит только из окружения."""
    src = open("/root/turbobaby-manager-bot/wa_webhook.py", encoding="utf-8").read()
    ok('ThreadingHTTPServer(("0.0.0.0"' not in src,
       "жёстко вшитого 0.0.0.0 в make_server больше нет")


# ─────────────────────────────────────────────────────────────────────────────
# 11. Очередь для ПК — pull / ack
# ─────────────────────────────────────────────────────────────────────────────

_PULL_SECRET = "a1b2c3d4e5f60718"          # фиксированный тестовый секрет


def _seed(db, n, source="meta", start=1):
    evs = [{"channel": "wa", "from": "6681000000" + str(i % 10), "name": "Кли",
            "type": "text", "text": "msg" + str(i), "media_id": None,
            "ts": 1700000000 + i, "echo": False, "history": False,
            "wamid": "wamid.seed%d.%d" % (start, i), "raw": {"i": i}}
           for i in range(start, start + n)]
    return db.enqueue(evs, source=source)


def _pull_http(db, secret_in_path, configured=_PULL_SECRET):
    h = _make_handler("GET", "/wa-queue/pull/" + secret_in_path, db=db,
                      pull_secret=configured)
    _dispatch(h)
    return h


def _ack_http(db, ids, secret_in_path=_PULL_SECRET, configured=_PULL_SECRET):
    body = json.dumps({"ids": ids}).encode()
    h = _make_handler("POST", "/wa-queue/ack/" + secret_in_path, body=body,
                      headers={"Content-Length": str(len(body))},
                      db=db, pull_secret=configured)
    _dispatch(h)
    return h


def test_pull_returns_rows_and_fields():
    db = _tmp_db()
    _seed(db, 3)
    h = _pull_http(db, _PULL_SECRET)
    ok(h._resp_code == 200, "верный секрет → 200")
    data = json.loads(h._resp_body.decode())
    ok(data["ok"] is True and data["count"] == 3, "отдано 3 записи")
    row = data["items"][0]
    for field in ("id", "from", "name", "type", "text", "ts", "source"):
        ok(field in row, "в записи есть поле " + field)
    ok(row["source"] == "meta", "источник записан: meta")


def test_pull_limit_20():
    db = _tmp_db()
    _seed(db, 25)
    data = json.loads(_pull_http(db, _PULL_SECRET)._resp_body.decode())
    ok(data["count"] == 20, "за раз отдаётся не больше 20 (отдано " + str(data["count"]) + ")")


def test_pull_wrong_secret_404_and_nothing_leased():
    db = _tmp_db()
    _seed(db, 2)
    h = _pull_http(db, "0000000000000000")
    ok(h._resp_code == 404, "неверный секрет → 404")
    ok(b"Not found" in h._resp_body, "тело как у неизвестного URL — эндпоинт себя не выдаёт")
    # и главное: отказ не пометил записи выданными
    data = json.loads(_pull_http(db, _PULL_SECRET)._resp_body.decode())
    ok(data["count"] == 2, "после отказа записи по-прежнему доступны (аренда не ставилась)")


def test_pull_no_secret_configured_404():
    db = _tmp_db()
    _seed(db, 1)
    h = _pull_http(db, "anything", configured="")
    ok(h._resp_code == 404, "секрет не настроен → 404 всегда (fail-closed)")
    h2 = _pull_http(db, "", configured="")
    ok(h2._resp_code == 404, "пустой секрет в пути тоже 404")


def test_ack_wrong_secret_404():
    db = _tmp_db()
    _seed(db, 1)
    h = _ack_http(db, [1], secret_in_path="deadbeefdeadbeef")
    ok(h._resp_code == 404, "ack с неверным секретом → 404")
    ok(db.pull()[0]["id"] == 1, "и запись НЕ помечена обработанной")


def test_pull_ack_then_not_returned():
    db = _tmp_db()
    _seed(db, 2)
    items = json.loads(_pull_http(db, _PULL_SECRET)._resp_body.decode())["items"]
    ids = [i["id"] for i in items]
    h = _ack_http(db, ids)
    ok(h._resp_code == 200, "ack → 200")
    ok(json.loads(h._resp_body.decode())["acked"] == 2, "подтверждено 2 записи")
    later = db.pull(now=int(time.time()) + 10_000)
    ok(len(later) == 0, "подтверждённые не выдаются больше НИКОГДА, даже после аренды")


def test_unacked_reappear_after_lease():
    db = _tmp_db()
    _seed(db, 2)
    t0 = 1_700_000_000
    first = db.pull(now=t0)
    ok(len(first) == 2, "первая выдача: 2")
    ok(len(db.pull(now=t0 + 60)) == 0,
       "через минуту без ack — НЕ выдаются повторно (аренда держит)")
    ok(len(db.pull(now=t0 + wh.LEASE_SECS - 1)) == 0, "за секунду до конца аренды — молчим")
    again = db.pull(now=t0 + wh.LEASE_SECS + 1)
    ok(len(again) == 2, "через 5 минут без ack — снова доступны (ПК умер, кто-то должен забрать)")


def test_ack_partial_leaves_rest():
    db = _tmp_db()
    _seed(db, 3)
    t0 = 1_700_000_000
    items = db.pull(now=t0)
    db.ack([items[0]["id"]], now=t0)
    back = db.pull(now=t0 + wh.LEASE_SECS + 1)
    ok(len(back) == 2, "подтверждена одна — возвращаются ровно две остальные")
    ok(items[0]["id"] not in [b["id"] for b in back], "подтверждённой среди них нет")


def test_ack_is_idempotent_and_junk_safe():
    db = _tmp_db()
    _seed(db, 1)
    t0 = 1_700_000_000
    i = db.pull(now=t0)[0]["id"]
    ok(db.ack([i], now=t0) == 1, "первый ack меняет строку")
    ok(db.ack([i], now=t0) == 0, "повторный ack ничего не меняет и не падает")
    ok(db.ack([99999], now=t0) == 0, "ack несуществующего id безвреден")
    ok(db.ack(["мусор", None, {}], now=t0) == 0, "мусорные id игнорируются без исключения")
    ok(db.ack([], now=t0) == 0, "пустой список — ноль")


def test_ack_bad_body():
    db = _tmp_db()
    _seed(db, 1)
    body = b"{not json"
    h = _make_handler("POST", "/wa-queue/ack/" + _PULL_SECRET, body=body,
                      headers={"Content-Length": str(len(body))},
                      db=db, pull_secret=_PULL_SECRET)
    _dispatch(h)
    ok(h._resp_code == 400, "нечитаемый JSON → 400 (секрет-то верный, врать про 404 незачем)")

    body2 = json.dumps({"ids": "1,2"}).encode()
    h2 = _make_handler("POST", "/wa-queue/ack/" + _PULL_SECRET, body=body2,
                       headers={"Content-Length": str(len(body2))},
                       db=db, pull_secret=_PULL_SECRET)
    _dispatch(h2)
    ok(h2._resp_code == 400, "ids не список → 400")
    ok(db.pull()[0]["id"] == 1, "и ничего не подтверждено")


def test_pull_deletes_nothing():
    db = _tmp_db()
    _seed(db, 4)
    with db._conn() as c:
        before = c.execute("SELECT COUNT(*) FROM wa_inbox").fetchone()[0]
    t0 = 1_700_000_000
    items = db.pull(now=t0)
    db.ack([i["id"] for i in items], now=t0)
    db.pull(now=t0 + 10_000)
    with db._conn() as c:
        after = c.execute("SELECT COUNT(*) FROM wa_inbox").fetchone()[0]
    ok(before == after == 4, "ни одна строка не удалена: было %d, стало %d" % (before, after))

    # Страж судит ДЕЙСТВИЕ, а не слово: разбираем модуль и смотрим SQL, который реально уходит
    # в execute/executemany. Наивный поиск подстроки «DELETE» краснел бы на комментарии,
    # который как раз и объясняет, почему удаления здесь нет, — тот самый класс «красное встаёт
    # на слово», закрытый в этом репозитории для гарда (40c8425).
    import ast as _ast
    src = open("/root/turbobaby-manager-bot/wa_webhook.py", encoding="utf-8").read()
    destructive = []
    for node in _ast.walk(_ast.parse(src)):
        if not isinstance(node, _ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, _ast.Attribute) and fn.attr in ("execute", "executemany")):
            continue
        if node.args and isinstance(node.args[0], _ast.Constant) \
                and isinstance(node.args[0].value, str):
            for stmt in node.args[0].value.split(";"):
                head = stmt.strip().upper().split()[:1]
                if head and head[0] in ("DELETE", "DROP", "TRUNCATE"):
                    destructive.append(stmt.strip()[:40])
    ok(not destructive,
       "ни один исполняемый SQL не удаляет и не роняет: " + (str(destructive) or "таких нет"))


def test_pull_marks_source_d360():
    db = _tmp_db()
    _seed(db, 1, source="d360")
    data = json.loads(_pull_http(db, _PULL_SECRET)._resp_body.decode())
    ok(data["items"][0]["source"] == "d360", "источник второй двери записан: d360")


def test_pull_concurrent_no_double_handout():
    """Две выдачи подряд не отдают одну строку дважды — иначе ПК ответил бы клиенту дважды."""
    db = _tmp_db()
    _seed(db, 30)
    t0 = 1_700_000_000
    a = [i["id"] for i in db.pull(now=t0)]
    b = [i["id"] for i in db.pull(now=t0)]
    ok(len(a) == 20 and len(b) == 10, "первая выдача 20, вторая — оставшиеся 10")
    ok(not (set(a) & set(b)), "пересечения между выдачами нет ни одной строки")


def test_legacy_rows_get_empty_source():
    """Строки, лежавшие до миграции, получают source='' — и это НЕ выдаётся за 'meta'."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    # таблица СТАРОЙ формы, без новых колонок
    with sqlite3.connect(path) as c:
        c.execute("""CREATE TABLE wa_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
            channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT,
            text TEXT, media_id TEXT, ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0,
            history INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'new',
            raw TEXT, wamid TEXT)""")
        c.execute("""INSERT INTO wa_inbox (ts_queued, from_number, msg_type, text, wamid)
                     VALUES (1700000000,'66811112222','text','старая строка','wamid.old')""")
        c.commit()
    db = wh.WAQueueDB(path)          # миграция ALTER TABLE происходит здесь
    items = db.pull()
    ok(len(items) == 1, "старая строка пережила миграцию и выдаётся")
    ok(items[0]["source"] == "", "у неё источник пуст — не записан, а не угадан")
    ok(items[0]["text"] == "старая строка", "её содержимое цело")
    os.remove(path)


def test_queue_paths_are_404_for_unknown_verbs():
    db = _tmp_db()
    h = _make_handler("GET", "/wa-queue/drop/" + _PULL_SECRET, db=db, pull_secret=_PULL_SECRET)
    _dispatch(h)
    ok(h._resp_code == 404, "неизвестный глагол очереди → 404")
    h2 = _make_handler("GET", "/wa-queue/pull", db=db, pull_secret=_PULL_SECRET)
    _dispatch(h2)
    ok(h2._resp_code == 404, "путь без секрета → 404")


def test_webhook_paths_still_work_next_to_queue():
    """Регресс: новые маршруты не увели у вебхука его собственные."""
    h = _make_handler("GET",
        "/wa-webhook?hub.mode=subscribe&hub.verify_token=test_verify_token&hub.challenge=STILL",
        pull_secret=_PULL_SECRET)
    _dispatch(h)
    ok(h._resp_code == 200 and b"STILL" in h._resp_body,
       "рукопожатие Meta работает как работало")


# ─── runner ───────────────────────────────────────────────────────────────────

def _run_all():
    tests = [
        test_verify_handshake_ok,
        test_verify_handshake_bad_token,
        test_verify_handshake_bad_mode,
        test_verify_handshake_wrong_path,
        test_signature_valid,
        test_signature_invalid,
        test_signature_missing,
        test_signature_skipped_when_no_secret,
        test_normalize_text,
        test_normalize_media_image,
        test_normalize_echo,
        test_normalize_history,
        test_normalize_recent_not_history,
        test_normalize_status,
        test_normalize_unknown_field_skipped,
        test_queue_dedup_same_wamid,
        test_queue_null_wamid_not_deduped,
        test_normalize_batch_multiple_messages,
        test_batch_enqueue_and_count,
        test_verify_signature_correct,
        test_verify_signature_wrong_secret,
        test_verify_signature_tampered_body,
        test_verify_signature_empty_secret_dev_mode,
        # 7. Concurrency
        test_make_server_is_threaded,
        test_200_before_db_write,
        test_parallel_requests_no_blocking,
        # 8. Health probe + watchdog
        test_wa_probe_ok,
        test_wa_probe_hung,
        test_watchdog_count_and_reset,
        test_watchdog_increments_on_consecutive_failures,
        # 9. 360dialog v1
        test_d360_correct_secret_200,
        test_d360_wrong_secret_404,
        test_d360_no_secret_configured_404,
        test_meta_path_still_needs_hmac,
        test_d360_dedup_same_wamid,
        test_normalize_d360_v1_text,
        test_normalize_d360_v1_image,
        test_normalize_d360_v1_status,
        test_normalize_d360_v1_empty,
        # 10. Bind — loopback
        test_bind_default_is_loopback,
        test_bind_explicit_is_honoured,
        test_make_server_binds_loopback,
        test_no_hardcoded_wildcard_bind,
        # 11. Очередь для ПК — pull/ack
        test_pull_returns_rows_and_fields,
        test_pull_limit_20,
        test_pull_wrong_secret_404_and_nothing_leased,
        test_pull_no_secret_configured_404,
        test_ack_wrong_secret_404,
        test_pull_ack_then_not_returned,
        test_unacked_reappear_after_lease,
        test_ack_partial_leaves_rest,
        test_ack_is_idempotent_and_junk_safe,
        test_ack_bad_body,
        test_pull_deletes_nothing,
        test_pull_marks_source_d360,
        test_pull_concurrent_no_double_handout,
        test_legacy_rows_get_empty_source,
        test_queue_paths_are_404_for_unknown_verbs,
        test_webhook_paths_still_work_next_to_queue,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:
            ok(False, f"{t.__name__}: EXCEPTION {e}")
    passed = sum(res)
    total  = len(res)
    print(f"\n{'OK' if passed == total else 'FAIL'} {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(_run_all())
