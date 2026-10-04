#!/usr/bin/env python3
"""Граница транспорта двери (WAPARTFIX0410): ни одного второго HTTP-запроса после отправки, которую сервер мог принять.

Настоящий `wa_send._post`/`_open` против ЛОКАЛЬНОГО сервера на 127.0.0.1 (наружу сети нет): сервер принял запрос и
оборвал ответ · ответил 500 после исполнения · ответил дольше плеча → РОВНО один запрос и unknown; соединение
отклонено (заведомо не принят) → повтор есть, а до сервера не дошло ни одного запроса. Сбой ОТДАЧИ ТЕЛА после начала
запроса (сброс соединения, таймаут посреди тела — внутри `h.request`, urllib заворачивает в URLError) — тоже unknown и
один запрос: «до отправки» только неразрешённое имя и отклонённое соединение. Успешные текст и документ — голден
7b8610d8 (тот же ответ двери, то же тело запроса). Загрузка медиа — подделка (повтор загрузки клиенту не виден).

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import http.client
import http.server
import json
import os
import socket
import sqlite3
import struct
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])
os.environ["PRETOOL_NOPUSH"] = "1"

import wa_send as S  # noqa: E402

NUM = "66812345678"
NOW = 1_790_000_000.0
ENV = {"WA_SEND": "1", "WA_360_API_KEY": "real_key_abcdef0123456789"}
PDF = b"%PDF-1.4 signed contract bytes"


def _queue():
    d = tempfile.mkdtemp(prefix="wa_bound_t_")
    path = os.path.join(d, "q.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER, channel TEXT, "
                "from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT, ts_msg INTEGER, "
                "echo INTEGER DEFAULT 0, history INTEGER DEFAULT 0, status TEXT, raw TEXT, wamid TEXT)")
    con.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, ts_msg, echo) VALUES(?,?,?,?,0)",
                (int(NOW - 600), NUM, "text", int(NOW - 600)))
    con.commit()
    con.close()
    return path


QDB = _queue()


class Srv:
    """Локальный сервер: mode ok · abort (тело прочитано, ответа нет) · 500 · slow (ответ дольше плеча)."""

    def __init__(self, mode):
        self.mode, self.hits = mode, []
        srv = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                srv.hits.append((self.path, json.loads(body.decode("utf-8"))))
                if srv.mode == "abort":
                    return                                      # исполнено и оборвано: ответа нет вовсе
                if srv.mode == "slow":
                    time.sleep(1.5)
                code, out = ((500, {"error": {"message": "internal"}}) if srv.mode == "500" else
                             (200, {"messages": [{"id": "wamid.HTTP%d" % len(srv.hits)}]}))
                raw = json.dumps(out).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def __enter__(self):
        self._old = S.API_BASE
        S.API_BASE = self.base
        return self

    def __exit__(self, *a):
        S.API_BASE = self._old
        self.httpd.shutdown()
        self.httpd.server_close()


def _text():
    return S.send_text(NUM, "Здравствуйте", now=NOW, db_path=QDB, env=ENV, sleep=lambda s: None)


def _doc():
    up = []

    def upload(url, fields, file, key, timeout):
        up.append(file[0])
        return 200, '{"id":"MEDIA1"}', None

    media = {"kind": "document", "mime": "application/pdf", "size": len(PDF), "filename": "contract_41.pdf",
             "caption": "", "fetch": lambda cap: (PDF, "")}
    return S.send_media(NUM, media, now=NOW, db_path=QDB, env=ENV, upload=upload, sleep=lambda s: None), up


def _messages(srv):
    return [h for h in srv.hits if h[0] == S.SEND_PATH]


# ── разбор ответа: граница повтора ───────────────────────────────────────────────────────

def test_classify_boundary():
    cases = [((None, "", "timeout"), (S.UNKNOWN, False)), ((None, "", "RemoteDisconnected"), (S.UNKNOWN, False)),
             ((None, "", None), (S.UNKNOWN, False)), (("x", "", None), (S.UNKNOWN, False)),
             ((500, "{}", None), (S.UNKNOWN, False)), ((503, "{}", None), (S.UNKNOWN, False)),
             ((599, "{}", None), (S.UNKNOWN, False)), ((200, "не json", None), (S.UNKNOWN, False)),
             ((429, "{}", None), (S.NOT_SENT, True)), ((None, "", S.PRE_SEND + "gaierror"), (S.NOT_SENT, True)),
             ((400, "{}", None), (S.NOT_SENT, False)),
             ((200, '{"messages":[{"id":"wamid.A"}]}', None), (S.SENT, False))]
    for (st, body, err), want in cases:
        o, _why, _w, retry = S.classify_response(st, body, err)
        assert (o, retry) == want, ((st, body, err), (o, retry), want)


# ── локальный сервер: могло быть принято → один запрос ───────────────────────────────────

def test_text_abort_after_accept_one_request():
    with Srv("abort") as srv:
        r = _text()
    assert len(_messages(srv)) == 1, "HTTP-запросов %d" % len(srv.hits)
    assert r["outcome"] == S.UNKNOWN and r["attempts"] == 1 and r["verify"] is True, r


def test_text_500_after_execute_one_request():
    with Srv("500") as srv:
        r = _text()
    assert len(_messages(srv)) == 1 and r["outcome"] == S.UNKNOWN and r["attempts"] == 1, (srv.hits, r)


def test_text_slow_answer_one_request():
    old = S.LEG_TIMEOUT_SEC
    S.LEG_TIMEOUT_SEC = 0.4
    try:
        with Srv("slow") as srv:
            r = _text()
    finally:
        S.LEG_TIMEOUT_SEC = old
    assert len(_messages(srv)) == 1 and r["outcome"] == S.UNKNOWN, (srv.hits, r)


def test_document_abort_and_500_one_request():
    for mode in ("abort", "500"):
        with Srv(mode) as srv:
            r, up = _doc()
        assert len(_messages(srv)) == 1, (mode, srv.hits)
        assert r["outcome"] == S.UNKNOWN and r["attempts"] == 1 and up == ["contract_41.pdf"], (mode, r)


def test_refused_is_retried_and_never_reached():
    """Соединение отклонено — запрос заведомо не принят: повтор законен, до сервера не дошло ни одного."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    old = S.API_BASE
    S.API_BASE = "http://127.0.0.1:%d" % port
    try:
        r = _text()
    finally:
        S.API_BASE = old
    assert r["outcome"] == S.NOT_SENT and r["attempts"] == S.MAX_ATTEMPTS, r
    assert "не дошёл до сервера" in r["reason"], r


# ── сбой ОТДАЧИ ТЕЛА после начала запроса → unknown, один запрос ─────────────────────────

class Cut:
    """Сервер на сыром сокете: принял заголовки (запрос НАЧАТ — сервер его видит) и тела не дочитывает.

    Заголовки клиент отдаёт по-настоящему. Отдача тела (`HTTPConnection.send` второго куска — она внутри `h.request`):
      reset — ждёт, пока сервер сбросит соединение (RST, SO_LINGER 0), и шлёт тело в сброшенный сокет: отказ
              ConnectionResetError даёт само ядро;
      stall — стоит плечо и падает TimeoutError — так, как падает `sendall` на медленной сети. Настоящий застой на
              Windows не воспроизводится: ядро забирает тело целиком в буфер, таймаут приходит уже на чтении ответа.
    Оба сбоя urllib заворачивает в URLError — причина двери так его и называет."""

    def __init__(self, mode):
        self.mode, self.hits, self.held = mode, [], []
        self.reset_done = threading.Event()
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.stop = threading.Event()
        self.th = threading.Thread(target=self._serve, daemon=True)
        self.th.start()
        self.base = "http://127.0.0.1:%d" % self.sock.getsockname()[1]

    def _serve(self):
        while not self.stop.is_set():
            try:
                c, _ = self.sock.accept()
            except OSError:
                continue
            head = b""
            try:
                c.settimeout(5)
                while b"\r\n\r\n" not in head:
                    chunk = c.recv(1024)
                    if not chunk:
                        break
                    head += chunk
            except OSError:
                pass
            self.hits.append(head.split(b"\r\n", 1)[0].decode("latin-1"))
            if self.mode == "reset":
                c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("HH" if os.name == "nt" else "ii", 1, 0))
                c.close()                                    # SO_LINGER 0 → сброс, а не обычное закрытие
                self.reset_done.set()
            else:
                self.held.append(c)                          # не читаем и не отвечаем

    def __enter__(self):
        self._old, self._send = S.API_BASE, http.client.HTTPConnection.send
        S.API_BASE = self.base
        real, srv = self._send, self

        def send(conn, data):
            if not getattr(conn, "_cut_head", False):            # заголовки — по-настоящему, сервер их видит
                conn._cut_head = True
                return real(conn, data)
            if srv.mode == "reset":                              # тело — в уже сброшенное соединение
                srv.reset_done.wait(5)
                srv.reset_done.clear()
                time.sleep(0.1)
                return real(conn, data)
            time.sleep(conn.timeout)                             # тело стоит плечо …
            raise socket.timeout("timed out")                    # … и падает так, как падает sendall

        http.client.HTTPConnection.send = send
        return self

    def __exit__(self, *a):
        S.API_BASE, http.client.HTTPConnection.send = self._old, self._send
        self.stop.set()
        for c in self.held:
            c.close()
        self.sock.close()
        self.th.join(2)


def _cut_send(mode, leg):
    old = S.LEG_TIMEOUT_SEC
    S.LEG_TIMEOUT_SEC = leg
    try:
        with Cut(mode) as srv:
            t0 = time.monotonic()
            r = _text()
            dt = time.monotonic() - t0
            time.sleep(0.3)                                  # опоздавший второй запрос тоже был бы посчитан
            hits = list(srv.hits)
    finally:
        S.LEG_TIMEOUT_SEC = old
    return r, hits, dt


def test_body_reset_after_start_unknown_one_request():
    """Заголовки у сервера (запрос начат), посреди тела — сброс соединения (ConnectionResetError внутри h.request).
    Сервер мог начать исполнение: unknown, ровно один HTTP-запрос, второго POST нет."""
    r, hits, dt = _cut_send("reset", 5.0)
    assert hits == ["POST %s HTTP/1.1" % S.SEND_PATH], "HTTP-запросов %d: %s" % (len(hits), hits)
    assert r["outcome"] == S.UNKNOWN and r["attempts"] == 1 and r["verify"] is True, r
    assert "(URLError)" in r["reason"], "сбой не внутри h.request: " + r["reason"]
    assert "мог долететь" in r["reason"] and "повтора нет" in r["reason"], r
    assert dt < 4.0, "сбой пришёл таймаутом плеча, а не сбросом: %.1f с" % dt


def test_body_stall_timeout_unknown_one_request():
    """Заголовки у сервера, тело встало дольше плеча (таймаут внутри h.request): unknown, один запрос, без повтора."""
    r, hits, dt = _cut_send("stall", 0.5)
    assert hits == ["POST %s HTTP/1.1" % S.SEND_PATH], "HTTP-запросов %d: %s" % (len(hits), hits)
    assert r["outcome"] == S.UNKNOWN and r["attempts"] == 1 and r["verify"] is True, r
    assert "(URLError)" in r["reason"], "таймаут не внутри h.request: " + r["reason"]
    assert "мог долететь" in r["reason"], r
    assert dt >= 0.4, "плечо не истекло: %.2f с" % dt


# ── голден: успешные текст и документ как на 7b8610d8 ───────────────────────────────────

def test_golden_success_text_and_document():
    with Srv("ok") as srv:
        r = _text()
    assert r == {"outcome": "sent", "reason": "принято, id сообщения назван", "wamid": "wamid.HTTP1",
                 "window": "open", "attempts": 1, "verify": False}, r
    assert srv.hits == [(S.SEND_PATH, {"messaging_product": "whatsapp", "recipient_type": "individual", "to": NUM,
                                       "type": "text", "text": {"preview_url": False, "body": "Здравствуйте"}})]
    with Srv("ok") as srv:
        r, up = _doc()
    assert r == {"outcome": "sent", "reason": "принято, id сообщения назван", "wamid": "wamid.HTTP1",
                 "window": "open", "attempts": 1, "verify": False, "uploads": 1, "dropped_caption": False}, r
    assert srv.hits == [(S.SEND_PATH, {"messaging_product": "whatsapp", "recipient_type": "individual", "to": NUM,
                                       "type": "document", "document": {"id": "MEDIA1",
                                                                        "filename": "contract_41.pdf"}})]


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:200])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
