#!/usr/bin/env python3
"""Дверь приёма Telegram на сервере (TGDOOR0510, задание Штаба 012b4-7e8.0510; план TGPLAN0510 п. 3 и З1):
маршрут POST /tg-queue/push в wa_webhook.py, очередь tg_queue.db тем же классом WAQueueDB.

Живой сервер на петле (порт 0), настоящий HTTP и настоящий SQLite во временном каталоге — без сети наружу,
без .env и без окружения: настройки двери передаются словарём в make_server. Секрет — выдуманная строка, в
вывод не печатается. Временные каталоги (`tempfile.mkdtemp`, префикс `tgdoor_`) не удаляются намеренно.

Семь отрицательных случаев TGPLAN0510 п. 3: неверный секрет → 404 и tg_queue.db без изменений · настройки нет →
404 · 257 КиБ → 413 · тот же (chat_id, msg_id, dir) дважды → оба раза в accepted, ряд один · после пачки TG
wa_queue.db не изменилась ни на байт · /wa-queue/pull рядов TG не отдаёт · channel='tg'. Плюс отсечка истории
(ряд старше момента включения → history=1), перевод видов в имена WA, кривое тело 400, сбой базы 500 без
accepted, и контракт против КОПИИ parse_accepted/row_key/http_transport пушера ПК (tg_feed_push.py ветки
tg-feed-0310 = 31a68f92, строки 110–129, 259–270, 299–321 — копия дословная, см. ниже)."""
import hashlib
import http.client
import inspect
import json
import logging
import os
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import wa_kind  # noqa: E402
import wa_webhook as W  # noqa: E402

SECRET = "tgdoor-vydumannyj-sekret-0510-q7"      # выдуманная строка, не боевая
PULL = "pull-vydumannyj-0510"
WRONG = "chuzhoj-tokin-0510"                      # чужой токен (заголовок HTTP — только latin-1)
SINCE = 1790000000                                # момент включения канала (секунды UTC)
LIVE = SINCE + 3600
OLD = SINCE - 86400


# ─── копия контракта пушера ПК (tg_feed_push.py @ 31a68f92), дословно ─────────────────────

DIRS = ("in", "out")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Редирект → HTTPError с 3xx: заголовок с токеном не уходит на другой адрес."""

    def redirect_request(self, *a, **k):
        return None


def http_transport(url, body, headers, timeout):
    """POST → (код, тело-байты). HTTPError — это ответ, а не исключение; сеть/таймаут — исключение."""
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            data = e.read()
        except Exception:                       # noqa: BLE001 — тело ошибки не обязательно
            data = b""
        return e.code, data


def row_key(rec):
    """Ключ ряда (chat_id, msg_id, dir) или None, если ряд не по контракту."""
    if not isinstance(rec, dict):
        return None
    cid, mid, d = rec.get("chat_id"), rec.get("msg_id"), rec.get("dir")
    if not isinstance(cid, int) or isinstance(cid, bool):
        return None
    if not isinstance(mid, int) or isinstance(mid, bool):
        return None
    if d not in DIRS:
        return None
    return (cid, mid, d)


def parse_accepted(status, body):
    """Ответ двери → множество ключей или (None, причина). Строго: любой кривой элемент —
    не подтверждено НИЧЕГО (повтор безвреден, ложное подтверждение — потеря ряда)."""
    if status != 200:
        return None, "ответ %s" % status
    try:
        data = json.loads((body or b"").decode("utf-8"))
    except Exception as e:                      # noqa: BLE001
        return None, "ответ не JSON (%s)" % type(e).__name__
    if not isinstance(data, dict) or "accepted" not in data:
        return None, "в ответе нет ключа accepted"
    acc = data["accepted"]
    if not isinstance(acc, list):
        return None, "accepted не список"
    keys = set()
    for it in acc:
        if not isinstance(it, (list, tuple)) or len(it) != 3:
            return None, "кривой элемент accepted"
        k = row_key({"chat_id": it[0], "msg_id": it[1], "dir": it[2]})
        if k is None:
            return None, "кривой элемент accepted"
        keys.add(k)
    return keys, ""


# ─── мир теста ─────────────────────────────────────────────────────────────────────────

def _tmp():
    return tempfile.mkdtemp(prefix="tgdoor_")


def _env(tmp, **over):
    env = {
        "verify_token": "vt-test", "app_secret": "", "phone_id": "", "port": 0,
        "bind_host": "127.0.0.1", "queue_db": os.path.join(tmp, "wa_queue.db"),
        "d360_path_secret": "", "pull_secret": PULL,
        "tg_push_secret": SECRET, "tg_channel_since": str(SINCE),
        "tg_queue_db": os.path.join(tmp, "tg_queue.db"),
    }
    env.update(over)
    return env


class Door:
    """Живой сервер на петле; `stop()` гасит его (файлы не трогает)."""

    def __init__(self, tmp, **over):
        self.tmp = tmp
        self.env = _env(tmp, **over)
        self.srv = W.make_server(self.env)
        self.port = self.srv.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()

    def post(self, path, body, auth=None, timeout=30):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        headers = {"Content-Type": "application/json"}
        if auth is not None:
            headers["Authorization"] = auth
        try:
            conn.request("POST", path, body=body, headers=headers)
            r = conn.getresponse()
            return r.status, r.read()
        finally:
            conn.close()

    def get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request("GET", path)
            r = conn.getresponse()
            return r.status, r.read()
        finally:
            conn.close()

    def push(self, rows, token=SECRET, bid="tgp-0-1"):
        """Ровно как пушер: тело и заголовки tg_feed_push._tick_locked, транспорт — его копия."""
        body = json.dumps({"batch_id": bid, "rows": rows}, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + token}
        return http_transport(self.base + W.TG_PUSH_PATH if hasattr(W, "TG_PUSH_PATH")
                              else self.base + "/tg-queue/push", body, headers, 30)


def _row(cid, mid, d="in", ts=LIVE, kind="text", text="Здравствуйте, сколько стоит PCX на неделю?"):
    return {"chat_id": cid, "msg_id": mid, "dir": d, "ts": ts, "kind": kind, "text": text,
            "reply_to": None, "sender_id": cid if d == "in" else 777000}


def _rows(path):
    if not os.path.exists(path):
        return None
    c = sqlite3.connect(path)
    try:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM wa_inbox ORDER BY id")]
    finally:
        c.close()


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _tgdb(door):
    return door.env["tg_queue_db"]


def _wadb(door):
    return door.env["queue_db"]


# ─── положительный путь и контракт ──────────────────────────────────────────────────────

def test_push_writes_then_answers_keys():
    d = Door(_tmp())
    try:
        rows = [_row(6879003264, 101), _row(6879003264, 102, d="out", text="Добрый день! 7 суток — 2 800 ฿"),
                _row(5550001, 7, kind="photo", text="вот царапина")]
        st, body = d.push(rows)
        keys, why = parse_accepted(st, body)
        assert st == 200 and keys is not None, (st, why)
        assert keys == {(6879003264, 101, "in"), (6879003264, 102, "out"), (5550001, 7, "in")}, keys
        got = _rows(_tgdb(d))                       # читаем СРАЗУ после ответа: всё принятое уже на диске
        assert {r["wamid"] for r in got} == {"tg:6879003264:101:in", "tg:6879003264:102:out",
                                             "tg:5550001:7:in"}, [r["wamid"] for r in got]
        by = {r["wamid"]: r for r in got}
        assert by["tg:6879003264:101:in"]["from_number"] == "tg:6879003264"
        assert by["tg:6879003264:101:in"]["text"].startswith("Здравствуйте")
        assert by["tg:5550001:7:in"]["msg_type"] == "image" and by["tg:5550001:7:in"]["caption"] == "вот царапина"
        assert by["tg:5550001:7:in"]["text"] is None
        assert all(r["source"] == "tg_push" for r in got)
    finally:
        d.stop()


def test_contract_copy_parse_accepted_on_every_answer():
    d = Door(_tmp())
    try:
        st, body = d.push([_row(42, 1), _row(42, 2)])
        keys, _ = parse_accepted(st, body)
        assert keys == {(42, 1, "in"), (42, 2, "in")}, (st, body[:200])
        data = json.loads(body.decode("utf-8"))
        assert all(type(x[0]) is int and type(x[1]) is int and x[2] in DIRS for x in data["accepted"]), data
        for status, raw in [d.push([_row(42, 3)], token=WRONG),                    # 404
                            d.post(W.TG_PUSH_PATH, b"{not json", auth="Bearer " + SECRET),   # 400
                            d.post(W.TG_PUSH_PATH, b"x" * (W.TG_PUSH_MAX_BYTES + 1), auth="Bearer " + SECRET)]:
            k, why = parse_accepted(status, raw)
            assert k is None and status != 200, (status, why)
    finally:
        d.stop()


# ─── семь отрицательных случаев TGPLAN0510 п. 3 ─────────────────────────────────────────

def test_neg1_wrong_secret_404_tg_queue_unchanged():
    d = Door(_tmp())
    try:
        before = _sha(_tgdb(d))
        st_unknown, body_unknown = d.post("/tg-queue/nope", b"{}", auth="Bearer " + SECRET)
        for auth in ("Bearer " + SECRET[:-1] + "X", "Bearer " + SECRET + "x", "Basic " + SECRET,
                     "Bearer ", "", None, "Bearer éé"):
            st, body = d.post(W.TG_PUSH_PATH, json.dumps({"rows": [_row(1, 1)]}).encode(), auth=auth)
            assert (st, body) == (404, b"Not found") == (st_unknown, body_unknown), (auth is None, st, body)
        assert _sha(_tgdb(d)) == before and _rows(_tgdb(d)) == []
    finally:
        d.stop()


def test_neg2_no_setting_404_door_closed():
    for over in ({"tg_push_secret": ""}, {"tg_channel_since": ""}, {"tg_channel_since": "вчера"},
                 {"tg_channel_since": "-5"}):
        tmp = _tmp()
        d = Door(tmp, **over)
        try:
            st, body = d.push([_row(1, 1)])
            assert (st, body) == (404, b"Not found"), (sorted(over), st, body)
            assert not os.path.exists(os.path.join(tmp, "tg_queue.db")), sorted(over)
        finally:
            d.stop()


def test_neg2b_same_file_as_wa_queue_refused():
    tmp = _tmp()
    d = Door(tmp, tg_queue_db=os.path.join(tmp, "wa_queue.db"))
    try:
        st, body = d.push([_row(1, 1)])
        assert (st, body) == (404, b"Not found"), (st, body)
        assert _rows(os.path.join(tmp, "wa_queue.db")) == []
    finally:
        d.stop()


def test_neg3_257kib_413_and_secret_first():
    d = Door(_tmp())
    try:
        big = b" " * (257 * 1024)
        st, body = d.post(W.TG_PUSH_PATH, big, auth="Bearer " + SECRET)
        assert st == 413, (st, body[:120])
        try:
            st2, _ = d.post(W.TG_PUSH_PATH, big, auth="Bearer " + WRONG)
        except (ConnectionError, OSError):
            st2 = "обрыв"                       # дверь закрылась, не прочитав тело — тоже «не 413»
        assert st2 in (404, "обрыв"), st2
        edge = json.dumps({"rows": [_row(9, 9, text="ж" * 10)]}).encode("utf-8")
        edge = edge[:-1] + b" " * (W.TG_PUSH_MAX_BYTES - len(edge)) + b"}"
        assert len(edge) == 256 * 1024
        st3, body3 = d.post(W.TG_PUSH_PATH, edge, auth="Bearer " + SECRET)
        assert st3 == 200 and parse_accepted(st3, body3)[0] == {(9, 9, "in")}, (st3, body3[:200])
        assert [r["wamid"] for r in _rows(_tgdb(d))] == ["tg:9:9:in"]
    finally:
        d.stop()


def test_neg4_same_key_twice_accepted_twice_one_row():
    d = Door(_tmp())
    try:
        r = _row(31337, 5)
        k1, _ = parse_accepted(*d.push([r]))
        k2, _ = parse_accepted(*d.push([r, dict(r)]))
        assert k1 == k2 == {(31337, 5, "in")}, (k1, k2)
        assert len(_rows(_tgdb(d))) == 1
    finally:
        d.stop()


def test_neg5_wa_queue_not_changed_by_a_byte():
    d = Door(_tmp())
    try:
        before = _sha(_wadb(d))
        keys, why = parse_accepted(*d.push([_row(11, 1), _row(11, 2, d="out"), _row(12, 1, ts=OLD)]))
        assert keys and len(keys) == 3, why
        assert _sha(_wadb(d)) == before
        assert _rows(_wadb(d)) == [] and len(_rows(_tgdb(d))) == 3
    finally:
        d.stop()


def test_neg6_wa_pull_gives_no_tg_rows():
    d = Door(_tmp())
    try:
        assert parse_accepted(*d.push([_row(21, 1), _row(21, 2)]))[0]
        st, body = d.get("/wa-queue/pull/" + PULL)
        data = json.loads(body.decode("utf-8"))
        assert st == 200 and data["count"] == 0 and data["items"] == [], (st, data)
    finally:
        d.stop()


def test_neg7_channel_tg():
    d = Door(_tmp())
    try:
        assert parse_accepted(*d.push([_row(1, 1), _row(1, 2, d="out"), _row(2, 1, kind="voice", text="")]))[0]
        got = _rows(_tgdb(d))
        assert len(got) == 3 and {r["channel"] for r in got} == {"tg"}, [r["channel"] for r in got]
    finally:
        d.stop()


# ─── отсечка истории, эхо, виды ─────────────────────────────────────────────────────────

def test_history_cutoff_and_echo():
    d = Door(_tmp())
    try:
        rows = [_row(50, 1, ts=SINCE - 1), _row(50, 2, ts=SINCE), _row(50, 3, ts=LIVE),
                _row(50, 4, d="out", ts=LIVE), _row(50, 5, d="out", ts=OLD)]
        assert len(parse_accepted(*d.push(rows))[0]) == 5
        by = {r["wamid"]: r for r in _rows(_tgdb(d))}
        flags = {w: (r["history"], r["echo"]) for w, r in by.items()}
        assert flags == {"tg:50:1:in": (1, 0), "tg:50:2:in": (0, 0), "tg:50:3:in": (0, 0),
                         "tg:50:4:out": (0, 1), "tg:50:5:out": (1, 1)}, flags
        kinds = {w: wa_kind.kind_of(r["msg_type"], r["echo"], r["history"]) for w, r in by.items()}
        assert kinds == {"tg:50:1:in": "history", "tg:50:2:in": "inbound", "tg:50:3:in": "inbound",
                         "tg:50:4:out": "echo", "tg:50:5:out": "echo"}, kinds
    finally:
        d.stop()


def test_kinds_renamed_to_wa_names():
    expect = {"text": "text", "photo": "image", "voice": "audio", "file": "document", "video": "video",
              "sticker": "sticker", "location": "location", "other": "other", "poll": "other"}
    for kind, wa in expect.items():
        key, ev = W.tg_row_event(_row(7, 1, kind=kind, text="подпись"), SINCE)
        assert key == (7, 1, "in") and ev["type"] == wa, (kind, ev and ev["type"])
        if wa in ("image", "audio", "video", "document", "sticker"):
            assert ev["caption"] == "подпись" and ev["text"] is None, kind
        else:
            assert ev["text"] == "подпись" and ev["caption"] is None, kind
        assert ev["wamid"] == "tg:7:1:in" and ev["channel"] == "tg" and ev["from"] == "tg:7"
    assert wa_kind.kind_of("other", 0, 0) == "unknown"          # неопознанное видно, карточки нет
    for kind in ("image", "audio", "document"):
        assert wa_kind.kind_of(kind, 0, 0) == "inbound", kind


# ─── кривое тело, кривые ряды, сбой базы ────────────────────────────────────────────────

def test_bad_body_400_nothing_written():
    d = Door(_tmp())
    try:
        for raw in (b"{not json", b"[1,2]", json.dumps({"rows": {"a": 1}}).encode(), b"\xff\xfe", b"{}"):
            st, body = d.post(W.TG_PUSH_PATH, raw, auth="Bearer " + SECRET)
            assert st == 400 and b'"accepted"' not in body, (raw[:20], st, body)
        assert _rows(_tgdb(d)) == []
    finally:
        d.stop()


def test_malformed_rows_not_accepted():
    d = Door(_tmp())
    try:
        good = _row(60, 1)
        bad = [dict(good, chat_id=True), dict(good, msg_id="2"), dict(good, dir="x"), dict(good, ts="вчера"),
               dict(good, ts=None), dict(good, kind=None), dict(good, text=5), "строка", None]
        st, body = d.push([good] + bad)
        keys, why = parse_accepted(st, body)
        assert keys == {(60, 1, "in")}, (st, why, body[:200])
        assert json.loads(body.decode("utf-8"))["malformed"] == len(bad)
        assert [r["wamid"] for r in _rows(_tgdb(d))] == ["tg:60:1:in"]
    finally:
        d.stop()


class _FailingDB:
    def __init__(self, real):
        self.real = real
        self.db_path = real.db_path

    def enqueue_confirmed(self, events, source=""):
        raise sqlite3.OperationalError("disk I/O error (подделка теста)")

    def enqueue_stats(self, events, source=""):
        raise sqlite3.OperationalError("disk I/O error (подделка теста)")


def test_db_failure_500_nothing_accepted():
    d = Door(_tmp())
    try:
        real = d.srv.RequestHandlerClass.tg_db
        d.srv.RequestHandlerClass.tg_db = _FailingDB(real)
        st, body = d.push([_row(70, 1), _row(70, 2)])
        assert st == 500, (st, body)
        assert b'"accepted"' not in body and parse_accepted(st, body)[0] is None, body
        assert _rows(_tgdb(d)) == []
    finally:
        d.stop()


def test_db_locked_500_then_retry_accepted():
    d = Door(_tmp())
    lock = sqlite3.connect(_tgdb(d), timeout=1, isolation_level=None)
    try:
        lock.execute("BEGIN EXCLUSIVE")
        t0 = time.time()
        st, body = d.push([_row(80, 1)])
        assert st == 500 and parse_accepted(st, body)[0] is None, (st, body)
        assert time.time() - t0 >= 5, "запись не ждала замка — ответ мог уйти раньше записи"
        lock.execute("ROLLBACK")
        assert _rows(_tgdb(d)) == []
        keys, why = parse_accepted(*d.push([_row(80, 1)]))       # повтор пушера после 500 — принят
        assert keys == {(80, 1, "in")}, why
    finally:
        lock.close()
        d.stop()


# ─── секрет: постоянное время, своё имя, не в журнале ───────────────────────────────────

def test_secret_check_constant_time_and_own_setting():
    assert W.bearer_secret_ok(SECRET, "Bearer " + SECRET) is True
    assert W.bearer_secret_ok(SECRET, "bearer  " + SECRET + " ") is True
    for cfg, hdr in (("", "Bearer x"), (SECRET, None), (SECRET, ""), (SECRET, "Bearer"), (SECRET, "Token " + SECRET),
                     (SECRET, "Bearer жж"), (SECRET, "Bearer " + PULL)):
        assert W.bearer_secret_ok(cfg, hdr) is False, (bool(cfg), hdr and hdr[:6])
    assert "compare_digest" in inspect.getsource(W.bearer_secret_ok)
    assert "bearer_secret_ok(" in inspect.getsource(W.WAWebhookHandler._do_tg_push)
    d = Door(_tmp(), tg_push_secret="", pull_secret=SECRET)     # секрет выдачи двери TG не открывает
    try:
        assert d.push([_row(1, 1)])[0] == 404
    finally:
        d.stop()


def test_log_has_counts_not_secret_or_text():
    seen = []

    class H(logging.Handler):
        def emit(self, rec):
            seen.append(rec.getMessage())

    h = H()
    logging.getLogger("wa_webhook").addHandler(h)
    d = Door(_tmp())
    try:
        d.push([_row(90, 1, text="мой паспорт AB123")])
        d.push([_row(90, 2)], token=WRONG)
    finally:
        d.stop()
        logging.getLogger("wa_webhook").removeHandler(h)
    joined = "\n".join(seen)
    assert "TG push: 1 rows, 1 accepted, 0 malformed" in joined, joined[-300:]
    assert SECRET not in joined and "паспорт" not in joined and WRONG not in joined


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL %s %s: %s" % (name, type(e).__name__, str(e)[:300]))
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
