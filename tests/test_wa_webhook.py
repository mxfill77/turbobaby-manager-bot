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
                  db=None):
    h = _FakeHandler(method, path, body, headers)
    _FakeHandler.verify_token = verify_token
    _FakeHandler.app_secret   = app_secret
    _FakeHandler.our_phone    = our_phone
    _FakeHandler.db           = db
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
