#!/usr/bin/env python3
"""«✅ Отправить» на карточке канала Telegram — ответ клиенту уходит через userbot ПК (TGSEND1310).

Всё на подделках и временных базах: очередь отправки `tg_outbox.db`, очередь канала и база агента — во временном
каталоге (`tempfile.mkdtemp`, префикс `tgsend_`, не удаляются намеренно); вход `wa_webhook` — живой сервер на петле
(порт 0) с выдуманным секретом; «ПК» — подделка, которая забирает и подтверждает ряды (напрямую через очередь или по
HTTP так же, как userbot). Сети наружу нет, Telegram не зовётся (Bot API — подделка каркаса `test_tg_core`), модель —
подделка, .env и окружение процесса не читаются.

Что стережём:
  1. очередь: queued → claimed → sent|failed|unknown; отмена только из queued; отменённое не выдаётся ни одной
     дорогой; повторная выдача claimed — только до срока и пока дверь ждёт; подтверждение идемпотентно;
     гонка «выдача против отмены» на одном файле из двух соединений — каждый ряд ровно одно;
  2. дверь: подтвердил «ушло» → sent и wamid = ключ эха ленты (`wa_webhook.tg_wamid(…,'out')`); отказ → not_sent;
     не забрал за N с → ряд отменён, not_sent «ПК не забрал за N с», поздней выдачи нет; забрал без ответа →
     unknown «проверьте чат перед повтором»; бюджет не превышен; закрытая дверь — байт-в-байт прежняя;
  3. вход: GET /tg-queue/outbox и POST /tg-queue/ack — тот же Bearer, что у push; флаг выключен — 404 как
     неизвестный адрес, файла очереди нет, модуль очереди даже не импортирован; ack идемпотентен;
     цепочка «дверь ↔ HTTP ↔ ПК» целиком;
  4. ядро и карточка: при открытой двери на карточке TG есть «✅ Отправить», подсказка «Исправить» обещает
     отправку; нажатие уходит дверью TG (дверь WA не зовётся ни разу), карточка несёт причину двери;
  5. своё эхо: по ключу из подтверждения, по позднему подтверждению (id), по тексту при неизвестном id (одно эхо на
     одну отправку) — паузы нет, черновики живы; эхо человека с телефона — пауза, как было;
  6. флаг выключен: строка старта канала и слова WA_AGENT_TG — байт-в-байт прежние (формула старой строки — копия
     дословная), ядро прежнего класса, файла очереди нет, карточка без «Отправить»."""
import http.client
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import test_tg_core as K  # noqa: E402
import tg_outbox as O  # noqa: E402
import wa_agent as A  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import wa_webhook as W  # noqa: E402

SECRET = "tgsend-vydumannyj-sekret-1310-z9"        # выдуманная строка, не боевая
SINCE = 1790000000
CHAT = 6879003264                                   # = K.TGNUM без «tg:»
T0 = K.T0
TG_SEND = dict(K.TG_ON, WA_AGENT_TG_SEND="1")


def _tmp():
    return tempfile.mkdtemp(prefix="tgsend_")


# ═══ подделка ПК: забирает и подтверждает ряды очереди ════════════════════════════════════

class FakePC:
    """mode: send — подтвердить «ушло» (msg_id растёт) · fail — отказ · unknown — «не уверен» · claim — забрать и
    молчать · silent — не забирать вовсе · late — забрать, подтвердить «ушло» только по `late_ack()`."""

    def __init__(self, outbox, mode="send", msg_id=555, error="UserIsBlockedError"):
        self.outbox, self.mode, self.msg_id, self.error = outbox, mode, msg_id, error
        self.claimed, self.acks = [], []

    def step(self):
        if self.mode == "silent":
            return
        for it in self.outbox.claim():
            self.claimed.append(it)
            if self.mode == "send":
                self.acks.append(self.outbox.ack(it["id"], it["token"], O.SENT, msg_id=self.msg_id))
                self.msg_id += 1
            elif self.mode == "fail":
                self.acks.append(self.outbox.ack(it["id"], it["token"], O.FAILED, error=self.error))
            elif self.mode == "unknown":
                self.acks.append(self.outbox.ack(it["id"], it["token"], O.UNKNOWN, error="ConnectionError"))

    def late_ack(self, msg_id):
        it = self.claimed[-1]
        return self.outbox.ack(it["id"], it["token"], O.SENT, msg_id=msg_id)


class Ticker:
    """Часы двери: монотонные = часы мира; пауза двигает их и даёт ПК сделать шаг."""

    def __init__(self, clock, pc=None):
        self.clock, self.pc, self.sleeps = clock, pc, []

    def sleep(self, s):
        self.sleeps.append(s)
        self.clock.t += float(s)
        if self.pc is not None:
            self.pc.step()

    def kw(self):
        return {"mono": self.clock, "sleep": self.sleep}


def door(mode="send", wait=20):
    clock = K.Clock(T0)
    ob = O.Outbox(os.path.join(_tmp(), "tg_outbox.db"), clock=clock)
    pc = FakePC(ob, mode)
    tk = Ticker(clock, pc)
    return S.TgDoor(ob, wait=wait, clock=clock, **tk.kw()), ob, pc, tk, clock


def rows(ob):
    c = sqlite3.connect(ob.path)
    try:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM tg_out ORDER BY id")]
    finally:
        c.close()


# ═══ 1. очередь ═══════════════════════════════════════════════════════════════════════════

def test_outbox_lifecycle_and_idempotent_ack():
    clock = K.Clock(T0)
    ob = O.Outbox(os.path.join(_tmp(), "tg_outbox.db"), clock=clock)
    rid, tok = ob.put(CHAT, "Байк свободен, 350 бат в сутки", 20)
    assert ob.get(tok)["state"] == O.QUEUED and rid == 1
    got = ob.claim()
    assert [(g["id"], g["chat_id"], g["text"], g["handed"]) for g in got] == \
        [(1, CHAT, "Байк свободен, 350 бат в сутки", 1)], got
    assert ob.get(tok)["state"] == O.CLAIMED
    again = ob.claim()                                  # ответа нет — выдаётся снова, пока срок не вышел
    assert [(g["id"], g["handed"]) for g in again] == [(1, 2)], again
    assert ob.cancel_queued(tok, "x") is False and ob.get(tok)["state"] == O.CLAIMED   # забранное не отменить
    r = ob.ack(rid, tok, O.SENT, msg_id=777)
    assert r == {"ok": True, "state": O.SENT, "dup": False, "msg_id": 777}, r
    assert ob.claim() == []                             # решённое не выдаётся
    dup = ob.ack(rid, tok, O.SENT, msg_id=777)
    assert dup["ok"] and dup["dup"] and dup["same"] and dup["state"] == O.SENT, dup
    other = ob.ack(rid, tok, O.FAILED, error="поздно")
    assert other["ok"] and other["dup"] and not other["same"] and ob.get(tok)["state"] == O.SENT, other
    assert ob.get(tok)["msg_id"] == 777 and ob.get(tok)["error"] is None
    assert ob.ack(rid, "чужой", O.SENT, msg_id=1) == {"ok": False, "error": "token_mismatch"}
    assert ob.ack(99, tok, O.SENT, msg_id=1) == {"ok": False, "error": "not_found"}
    for bad in (0, -1, True, "5", None, 1.5):
        assert ob.ack(rid, tok, O.SENT, msg_id=bad) == {"ok": False, "error": "bad_msg_id"}, bad
    assert ob.ack(rid, tok, "maybe") == {"ok": False, "error": "bad_outcome"}
    assert ob.sent_token(CHAT, 777) == tok and ob.sent_token(CHAT, 778) is None
    assert ob.counts() == {O.SENT: 1}


def test_cancel_only_queued_cancelled_never_handed():
    clock = K.Clock(T0)
    ob = O.Outbox(os.path.join(_tmp(), "tg_outbox.db"), clock=clock)
    rid, tok = ob.put(CHAT, "a", 20)
    assert ob.cancel_queued(tok, "дверь: ПК не забрал") is True
    assert ob.cancel_queued(tok, "ещё раз") is False
    assert ob.claim() == [] and ob.get(tok)["state"] == O.CANCELLED
    assert ob.ack(rid, tok, O.SENT, msg_id=5) == {"ok": False, "error": "cancelled", "state": O.CANCELLED}
    rid2, tok2 = ob.put(CHAT, "b", 20)
    assert ob.ack(rid2, tok2, O.SENT, msg_id=5) == {"ok": False, "error": "not_claimed", "state": O.QUEUED}


def test_expired_rows_are_never_handed_and_give_up_stops_rehanding():
    clock = K.Clock(T0)
    ob = O.Outbox(os.path.join(_tmp(), "tg_outbox.db"), clock=clock)
    _, tok = ob.put(CHAT, "служба упала посреди ожидания", 20)
    clock.t += 21                                       # срок вышел: дверь этого ряда уже не ждёт
    assert ob.claim() == [] and ob.get(tok)["state"] == O.CANCELLED, ob.get(tok)
    assert "срок вышел" in ob.get(tok)["cancel_why"]
    _, tok2 = ob.put(CHAT, "b", 20)
    assert len(ob.claim()) == 1
    assert ob.give_up(tok2) is True and ob.give_up(tok2) is False
    assert ob.claim() == [] and ob.get(tok2)["state"] == O.CLAIMED       # дверь не ждёт — не выдаётся снова
    rid3, tok3 = ob.put(CHAT, "c", 20)
    assert len(ob.claim()) == 1
    clock.t += 25
    assert ob.claim() == [] and ob.get(tok3)["state"] == O.CLAIMED       # срок вышел — не выдаётся снова
    # позднее подтверждение ПК записывается (сверка эха по id его увидит)
    assert ob.ack(rid3, tok3, O.SENT, msg_id=900)["state"] == O.SENT


def test_race_claim_versus_cancel_each_row_exactly_one():
    path = os.path.join(_tmp(), "tg_outbox.db")
    door_side, pc_side = O.Outbox(path), O.Outbox(path)     # два соединения на файл — как две службы
    toks = [door_side.put(CHAT, "r%d" % i, 30)[1] for i in range(60)]
    claimed, cancelled, errs = [], [], []

    def pc():
        try:
            for _ in range(40):
                claimed.extend(it["token"] for it in pc_side.claim(limit=3))
        except Exception as e:                                       # noqa: BLE001
            errs.append(e)

    def dr():
        try:
            for t in toks:
                if door_side.cancel_queued(t, "срок"):
                    cancelled.append(t)
        except Exception as e:                                       # noqa: BLE001
            errs.append(e)
    a, b = threading.Thread(target=pc), threading.Thread(target=dr)
    a.start(), b.start()
    a.join(), b.join()
    assert not errs, errs
    first = set(claimed)
    assert not (first & set(cancelled)), "ряд и отменён, и выдан"
    assert first | set(cancelled) == set(toks), (len(first), len(cancelled))
    for t in toks:
        st = door_side.get(t)["state"]
        assert (st == O.CLAIMED) == (t in first) and (st == O.CANCELLED) == (t in cancelled), (t, st)
    assert all(it["token"] in first for it in pc_side.claim()), "отменённый ряд выдан"
    print("   гонка: выдано %d, отменено %d из %d" % (len(first), len(cancelled), len(toks)))


def test_formulas_shared_with_the_feed_door():
    for c, m in ((1, 1), (CHAT, 555), (999999999999, 2 ** 31 + 7)):
        assert O.echo_wamid(c, m) == W.tg_wamid(c, m, "out"), (c, m)
        assert O.parse_echo(O.echo_wamid(c, m)) == (c, m)
    assert O.parse_echo(W.tg_wamid(CHAT, 5, "in")) is None and O.parse_echo("wamid.HBg") is None
    assert O.chat_of("tg:%d" % CHAT) == CHAT and O.chat_of("tg:-1001234") == -1001234
    assert O.chat_of("66812345678") is None and O.chat_of(None) is None
    assert O.wait_of(None) == (20, "20 с") and O.wait_of("15") == (15, "15 с")
    for bad in ("0", "4", "61", "abc", "-5", "1e3"):
        sec, words = O.wait_of(bad)
        assert sec == 20 and "битая" in words, (bad, words)
    assert O.tg_len("😀") == 2 and O.tg_len("ab") == 2
    assert O.flag_on("1") and O.flag_on(" ON ") and not O.flag_on("0") and not O.flag_on("") and not O.flag_on(None)
    assert O.path_of({}, "/x/y/tg_queue.db").replace("\\", "/").endswith("/x/y/tg_outbox.db")
    assert O.path_of({"TG_OUTBOX_DB": "/z/o.db"}, "/x/tg_queue.db") == "/z/o.db"


# ═══ 2. дверь ═════════════════════════════════════════════════════════════════════════════

def test_door_sent_wamid_is_feed_echo_key():
    d, ob, pc, tk, clock = door("send")
    res = d.send_text("tg:%d" % CHAT, "Байк свободен с 15-го")
    assert res["outcome"] == "sent" and res["wamid"] == W.tg_wamid(CHAT, 555, "out"), res
    assert "сообщение 555" in res["reason"]
    assert rows(ob)[0]["state"] == O.SENT and rows(ob)[0]["text"] == "Байк свободен с 15-го"
    assert clock.t - T0 <= 1.0 and len(tk.sleeps) <= 2, (clock.t - T0, tk.sleeps)   # ПК ответил — дверь не ждёт срока


def test_door_refusal_is_not_sent():
    d, ob, pc, tk, clock = door("fail")
    res = d.send_text("tg:%d" % CHAT, "x")
    assert res["outcome"] == "not_sent" and res["wamid"] is None and "UserIsBlockedError" in res["reason"], res


def test_door_pc_silent_row_cancelled_no_late_send():
    d, ob, pc, tk, clock = door("silent", wait=20)
    res = d.send_text("tg:%d" % CHAT, "x")
    assert res == {"outcome": "not_sent", "reason": "ПК не забрал за 20 с — не отправлено", "wamid": None}, res
    assert rows(ob)[0]["state"] == O.CANCELLED
    assert 20 <= clock.t - T0 <= 20 + S.TG_SEND_POLL, clock.t - T0                  # бюджет не превышен
    pc.mode = "send"
    pc.step()                                           # ПК проснулся — отменённое не выдаётся ни одной дорогой
    assert pc.claimed == [] and rows(ob)[0]["state"] == O.CANCELLED


def test_door_claimed_without_ack_is_unknown_and_not_rehanded():
    d, ob, pc, tk, clock = door("claim", wait=10)
    res = d.send_text("tg:%d" % CHAT, "x")
    assert res["outcome"] == "unknown" and res["wamid"] is None, res
    assert "ПК забрал, но не подтвердил за 10 с" in res["reason"] and "проверьте чат" in res["reason"], res
    r = rows(ob)[0]
    assert r["state"] == O.CLAIMED and r["door_gave_up"] is not None
    assert ob.claim() == [], "дверь не ждёт — ряд не выдаётся снова"
    assert 10 <= clock.t - T0 <= 10 + S.TG_SEND_POLL


def test_door_pc_unsure_is_unknown():
    d, ob, pc, tk, clock = door("unknown")
    res = d.send_text("tg:%d" % CHAT, "x")
    assert res["outcome"] == "unknown" and "проверьте чат" in res["reason"], res


def test_door_refuses_before_queue():
    d, ob, pc, tk, clock = door("send")
    for to, text, word in (("66812345678", "x", "ключ"), ("tg:-1001234567", "x", "не личный"),
                           ("tg:%d" % CHAT, "   ", "пустой"), ("tg:%d" % CHAT, "я" * 4097, "4096")):
        res = d.send_text(to, text)
        assert res["outcome"] == "not_sent" and word in res["reason"], (to, res)
    assert rows(ob) == [] and pc.claimed == []
    assert d.send_text("tg:%d" % CHAT, "я" * 4096)["outcome"] == "sent"        # ровно предел — уходит
    m = d.send_media("tg:%d" % CHAT, {"kind": "image"})
    assert m["outcome"] == "not_sent" and "медиа" in m["reason"]


def test_closed_door_byte_for_byte_old():
    d = S.TgDoor()
    old = {"outcome": "not_sent", "reason": "отправка в Telegram закрыта насовсем — ответьте клиенту сами",
           "wamid": None}
    assert d.is_open() is False and d.send_text("tg:%d" % CHAT, "x") == old and d.send_media("tg:1", {}) == old


# ═══ 3. вход wa_webhook ═══════════════════════════════════════════════════════════════════

class Hook:
    def __init__(self, tmp, **over):
        self.env = {"verify_token": "vt", "app_secret": "", "phone_id": "", "port": 0, "bind_host": "127.0.0.1",
                    "queue_db": os.path.join(tmp, "wa_queue.db"), "d360_path_secret": "", "pull_secret": "",
                    "tg_push_secret": SECRET, "tg_channel_since": str(SINCE),
                    "tg_queue_db": os.path.join(tmp, "tg_queue.db")}
        self.env.update(over)
        self.srv = W.make_server(self.env)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()

    def req(self, method, path, body=None, auth="Bearer " + SECRET):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = auth
        try:
            conn.request(method, path, body=body, headers=headers)
            r = conn.getresponse()
            return r.status, r.read()
        finally:
            conn.close()

    def ack(self, **payload):
        return self.req("POST", W.TG_ACK_PATH, json.dumps(payload).encode("utf-8"))


def test_hook_flag_off_doors_404_like_unknown_url_no_file():
    tmp = _tmp()
    for over in ({}, {"tg_send": "0"}, {"tg_send": ""}, {"tg_send": "no"}):
        h = Hook(tmp, **over)
        try:
            unknown = h.req("GET", "/no-such-door")
            assert h.req("GET", W.TG_OUTBOX_PATH) == unknown == (404, b"Not found"), over
            assert h.req("POST", W.TG_ACK_PATH, b"{}") == (404, b"Not found"), over
            assert h.srv.RequestHandlerClass.tg_outbox is None
        finally:
            h.stop()
    assert not os.path.exists(os.path.join(tmp, "tg_outbox.db")), "файл очереди заведён при выключенном флаге"
    # флаг выключен — модуль очереди даже не импортирован (отдельный процесс: этот набор его импортирует сам)
    probe = ("import sys; sys.path.insert(0, %r); import wa_webhook as W; "
             "W.make_server(dict(verify_token='v', app_secret='', phone_id='', port=0, bind_host='127.0.0.1', "
             "queue_db=%r, d360_path_secret='', pull_secret='', tg_push_secret='s', tg_channel_since='1', "
             "tg_queue_db=%r)).server_close(); print('tg_outbox' in sys.modules)"
             % (ROOT, os.path.join(tmp, "p_wa.db"), os.path.join(tmp, "p_tg.db")))
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip().splitlines()[-1] == "False", (out.stdout, out.stderr[-500:])


def test_hook_on_needs_push_door_and_own_file():
    tmp = _tmp()
    for over in ({"tg_send": "1", "tg_channel_since": ""},                    # дверь приёма закрыта
                 {"tg_send": "1", "tg_push_secret": ""},
                 {"tg_send": "1", "tg_outbox_db": os.path.join(tmp, "wa_queue.db")},   # файл WA
                 {"tg_send": "1", "tg_outbox_db": os.path.join(tmp, "tg_queue.db")}):  # файл очереди TG
        h = Hook(tmp, **over)
        try:
            assert h.srv.RequestHandlerClass.tg_outbox is None, over
            assert h.req("GET", W.TG_OUTBOX_PATH) == (404, b"Not found"), over
        finally:
            h.stop()


def test_hook_outbox_and_ack_contract():
    tmp = _tmp()
    h = Hook(tmp, tg_send="1")
    try:
        ob = h.srv.RequestHandlerClass.tg_outbox
        assert ob is not None and ob.path == os.path.join(tmp, "tg_outbox.db")
        assert h.req("GET", W.TG_OUTBOX_PATH, auth="Bearer chuzhoj") == (404, b"Not found")
        assert h.req("GET", W.TG_OUTBOX_PATH, auth=None) == (404, b"Not found")
        st, body = h.req("GET", W.TG_OUTBOX_PATH)
        assert st == 200 and json.loads(body)["items"] == [], body
        rid, tok = ob.put(CHAT, "Здравствуйте! Да, PCX свободен.", 20, now=time.time())
        st, body = h.req("GET", W.TG_OUTBOX_PATH)
        items = json.loads(body)["items"]
        assert st == 200 and [(i["id"], i["token"], i["chat_id"], i["text"], i["handed"]) for i in items] == \
            [(rid, tok, CHAT, "Здравствуйте! Да, PCX свободен.", 1)], items
        st, body = h.req("GET", W.TG_OUTBOX_PATH)           # ответ GET потерян — ПК получит ряд снова
        assert [i["handed"] for i in json.loads(body)["items"]] == [2]
        assert h.req("POST", W.TG_ACK_PATH, b"{not json")[0] == 400
        assert h.ack(id=rid, token=tok, outcome="maybe")[0] == 400
        assert h.ack(id=rid, token=tok, outcome="sent")[0] == 400                # sent без msg_id
        assert h.ack(id="1", token=tok, outcome="sent", msg_id=5)[0] == 400       # id не число
        st, body = h.ack(id=rid, token="chuzhoj", outcome="sent", msg_id=5)
        assert st == 200 and json.loads(body) == {"ok": False, "error": "token_mismatch"}
        st, body = h.ack(id=rid, token=tok, outcome="sent", msg_id=4242)
        assert st == 200 and json.loads(body)["ok"] and json.loads(body)["state"] == "sent", body
        st, body = h.ack(id=rid, token=tok, outcome="sent", msg_id=4242)          # повтор безвреден
        assert st == 200 and json.loads(body)["dup"] is True and ob.get(tok)["msg_id"] == 4242
        assert json.loads(h.req("GET", W.TG_OUTBOX_PATH)[1])["items"] == []
        assert h.req("POST", W.TG_ACK_PATH, b"{}", auth="Bearer chuzhoj") == (404, b"Not found")
        # прежние двери на месте: push принимает ряд, неизвестный адрес — 404
        row = {"chat_id": CHAT, "msg_id": 4242, "dir": "out", "ts": SINCE + 10, "kind": "text",
               "text": "Здравствуйте! Да, PCX свободен.", "reply_to": None, "sender_id": 777}
        st, body = h.req("POST", W.TG_PUSH_PATH, json.dumps({"batch_id": "b", "rows": [row]}).encode())
        assert st == 200 and json.loads(body)["accepted"] == [[CHAT, 4242, "out"]], body
    finally:
        h.stop()


def test_chain_door_http_pc_sent():
    """Целиком: дверь службы ждёт, «ПК» по HTTP забирает и подтверждает — как userbot (живые часы, короткий срок)."""
    tmp = _tmp()
    h = Hook(tmp, tg_send="1")
    stop = []
    got = []

    def pc():
        while not stop:
            st, body = h.req("GET", W.TG_OUTBOX_PATH)
            for it in json.loads(body).get("items", []):
                got.append(it)
                h.ack(id=it["id"], token=it["token"], outcome="sent", msg_id=31337)
            time.sleep(0.2)
    th = threading.Thread(target=pc, daemon=True)
    th.start()
    try:
        d = S.TgDoor(O.Outbox(os.path.join(tmp, "tg_outbox.db")), wait=8, poll=0.1)
        t0 = time.monotonic()
        res = d.send_text("tg:%d" % CHAT, "Цена 350 бат в сутки")
        assert res["outcome"] == "sent" and res["wamid"] == W.tg_wamid(CHAT, 31337, "out"), res
        assert time.monotonic() - t0 < 8 and len(got) == 1 and got[0]["text"] == "Цена 350 бат в сутки", got
    finally:
        stop.append(1)
        th.join(timeout=5)
        h.stop()


# ═══ 4–5. ядро, карточка, своё эхо ════════════════════════════════════════════════════════

class SendWorld:
    """Мир каркаса test_tg_core с открытой дверью TG; ПК — подделка на очереди мира, шаг — в паузе двери."""

    def __init__(self, mode="send", environ=None, wait=20):
        self.pc = FakePC(None, mode)
        self.sleeps = []
        w = K.World.__new__(K.World)            # часы мира заводит конструктор каркаса — дверь читает их при вызове
        environ = dict(environ or TG_SEND, WA_AGENT_TG_SEND_SEC=str(wait))
        K.World.__init__(w, environ, tg=True, tg_door_kw={"mono": lambda: w.clock.t, "sleep": self.sleep})
        self.w = w
        self.pc.outbox = getattr(w.tgc, "tg_outbox", None)

    def sleep(self, sec):
        """Пауза двери: часы мира вперёд, ПК делает шаг."""
        self.sleeps.append(sec)
        self.w.clock.t += float(sec)
        self.pc.step()

    def draft(self):
        """Первый старт ядра TG, входящее клиента, черновик и карточка."""
        self.w.tgc.tick(T0 - 1000)
        self.put(K.TGNUM, T0 - 200, echo=0, text="Сколько стоит PCX на неделю?")
        self.w.tgc.tick(T0)
        return self

    def put(self, number, ts, echo=0, text="x", wamid=None, msg_type="text"):
        q = sqlite3.connect(self.w.env["tg_queue_db"])
        rid = q.execute("INSERT INTO wa_inbox(ts_queued, channel, from_number, msg_type, text, ts_msg, echo, history, "
                        "wamid) VALUES(?,?,?,?,?,?,?,0,?)", (ts, "tg", number, msg_type, text, ts, echo, wamid)).lastrowid
        q.commit()
        q.close()
        return rid

    def client(self):
        return self.w.tgc.db.execute("SELECT paused, pause_no, done_upto, last_in_id FROM clients WHERE number=?",
                                     (K.TGNUM,)).fetchone()

    def no_echo_errors(self):
        bad = [ln for ln in self.w.lines if "сверка с очередью отправки не удалась" in ln]
        assert not bad, bad


def test_card_has_send_and_fix_hint_promises_send_when_door_open():
    sw = SendWorld().draft()
    w = sw.w
    assert isinstance(w.tgc, S.TgSendCore) and w.tgc.door.is_open() and w.tgc._door_open()
    (card, datas), = w.cards("tg")
    assert datas == ["tg:send:1:1", "tg:fix:1:1", "tg:no:1:1"], datas
    assert G.W_DOOR_CLOSED not in card["text"], card["text"]
    w.tg.handle(w.press("tg:fix:1:1"))
    assert w.answers()[-1] == K.GOLDEN_WA_FIX, w.answers()      # та же подсказка, что у WA: «Отправить» шлёт
    assert w.tg.peers["tg"]._send_shown() is True


def test_press_sends_through_pc_wa_door_untouched():
    sw = SendWorld("send").draft()
    w = sw.w
    w.tg.handle(w.press("tg:send:1:1"))
    d = K.draft(w.env["tg_agent_db"])
    assert d == (K.TGNUM, A.SENT, 1, "черновик TG"), d
    wamid = w.tgc.db.execute("SELECT wamid FROM drafts WHERE id=1").fetchone()[0]
    assert wamid == W.tg_wamid(CHAT, 555, "out"), wamid
    assert w.sends == [] and w.media == [], "дверь WA звана из канала TG"
    assert w.answers()[-1].startswith("sent — ушло через userbot на ПК (сообщение 555)"), w.answers()
    edits = [p for p in w.http.of("editMessageText") if "sent — ушло через userbot на ПК" in p.get("text", "")]
    assert edits, "карточка не получила исход с причиной"
    out = w.tgc.db.execute("SELECT wamid, text, via FROM outbox").fetchall()
    assert out == [(wamid, "черновик TG", A.VIA_AGENT)], out
    assert sw.pc.claimed and sw.pc.claimed[0]["chat_id"] == CHAT and sw.pc.claimed[0]["text"] == "черновик TG"
    # «уже решено» второму нажавшему; дверь второй раз не зовётся
    w.tg.handle(w.press("tg:send:1:1"))
    assert w.answers()[-1].startswith("уже решено") and len(sw.pc.claimed) == 1


def test_own_echo_by_key_no_pause_human_echo_pauses():
    sw = SendWorld("send").draft()
    w = sw.w
    w.tg.handle(w.press("tg:send:1:1"))
    before = sw.client()
    sw.put(K.TGNUM, T0 + 30, echo=1, text="черновик TG", wamid=W.tg_wamid(CHAT, 555, "out"))   # своё эхо лентой
    w.tgc.tick(T0 + 40)
    assert sw.client()[0] == 0 and sw.client()[1] == before[1], (sw.client(), before)
    assert not [p for p in w.http.of("sendMessage") if "Продолжить" in json.dumps(p, ensure_ascii=False)]
    # история агента: ушедшее — ОДНОЙ репликой «мы» (эхо очереди и outbox сведены по одному ключу)
    import wa_history
    items, _ = wa_history.read_history(K.TGNUM, w.env["tg_queue_db"], "", sent_db=w.env["tg_agent_db"])
    ours = [it for it in items if it["who"] == "мы" and it["text"] == "черновик TG"]
    assert len(ours) == 1 and ours[0]["key"] == W.tg_wamid(CHAT, 555, "out"), items
    # клиент пишет ещё — черновик рождается, как без эха
    sw.put(K.TGNUM, T0 + 50, echo=0, text="а шлем?")
    w.tgc.tick(T0 + 200)
    assert K.draft(w.env["tg_agent_db"], 2)[1] == A.PENDING, K.draft(w.env["tg_agent_db"], 2)
    # эхо человека с телефона (иной id, иной текст) — как было: черновик снят, пауза
    sw.put(K.TGNUM, T0 + 210, echo=1, text="Шлем дадим бесплатно", wamid=W.tg_wamid(CHAT, 560, "out"))
    w.tgc.tick(T0 + 220)
    assert sw.client()[0] == 1 and K.draft(w.env["tg_agent_db"], 2)[1] == A.SUPERSEDED, sw.client()


def test_late_ack_echo_by_id():
    sw = SendWorld("claim", wait=10).draft()
    w = sw.w
    w.tg.handle(w.press("tg:send:1:1"))
    assert K.draft(w.env["tg_agent_db"])[1] == A.UNSURE
    assert "проверьте чат" in w.answers()[-1], w.answers()
    assert sw.pc.late_ack(4101)["state"] == O.SENT                      # подтверждение после срока двери
    sw.put(K.TGNUM, T0 + 60, echo=1, text="черновик TG (Telegram мог изменить)", wamid=W.tg_wamid(CHAT, 4101, "out"))
    w.tgc.tick(T0 + 70)
    assert sw.client()[0] == 0, sw.client()
    assert w.tgc.db.execute("SELECT how FROM tg_own_echo").fetchall() == [("id",)]


def test_unknown_id_echo_by_text_once():
    sw = SendWorld("unknown").draft()
    w = sw.w
    w.tg.handle(w.press("tg:send:1:1"))
    assert K.draft(w.env["tg_agent_db"])[1] == A.UNSURE
    sw.put(K.TGNUM, T0 + 20, echo=1, text="  черновик TG\r\n", wamid=W.tg_wamid(CHAT, 7001, "out"))
    w.tgc.tick(T0 + 30)
    assert sw.client()[0] == 0, sw.client()
    assert w.tgc.db.execute("SELECT how FROM tg_own_echo").fetchall() == [("text",)]
    # тот же текст ещё раз (человек повторил с телефона) — одна отправка закрывает одно эхо: это ответ человека
    sw.put(K.TGNUM, T0 + 40, echo=1, text="черновик TG", wamid=W.tg_wamid(CHAT, 7002, "out"))
    w.tgc.tick(T0 + 50)
    assert sw.client()[0] == 1, sw.client()
    sw.no_echo_errors()


def test_unknown_id_other_text_or_far_time_is_human():
    for text, ts in (("совсем другой ответ", T0 + 20), ("черновик TG", T0 + 3600)):
        sw = SendWorld("unknown").draft()
        w = sw.w
        w.tg.handle(w.press("tg:send:1:1"))
        sw.put(K.TGNUM, ts, echo=1, text=text, wamid=W.tg_wamid(CHAT, 7001, "out"))
        w.tgc.tick(ts + 10)
        assert sw.client()[0] == 1, (text, ts, sw.client())
        assert w.tgc.db.execute("SELECT COUNT(*) FROM tg_own_echo").fetchone()[0] == 0
        sw.no_echo_errors()


def test_own_echo_through_real_feed_door():
    """Эхо приходит НАСТОЯЩЕЙ дверью ленты (POST /tg-queue/push → tg_queue.db схемой WAQueueDB): по ключу из
    подтверждения и по тексту при неизвестном id — паузы нет; ряд человека той же дверью — пауза."""
    for mode, mid in (("send", 555), ("unknown", 8100)):
        sw = SendWorld(mode).draft()
        w = sw.w
        w.tg.handle(w.press("tg:send:1:1"))
        h = Hook(w.dir, tg_queue_db=w.env["tg_queue_db"], tg_channel_since="1")
        try:
            ours = {"chat_id": CHAT, "msg_id": mid, "dir": "out", "ts": int(T0 + 5), "kind": "text",
                    "text": "черновик TG", "reply_to": None, "sender_id": 777000}
            st, body = h.req("POST", W.TG_PUSH_PATH, json.dumps({"batch_id": "b1", "rows": [ours]}).encode())
            assert st == 200 and json.loads(body)["accepted"] == [[CHAT, mid, "out"]], body
            w.tgc.tick(T0 + 30)
            assert sw.client()[0] == 0, (mode, sw.client())
            human = dict(ours, msg_id=mid + 1, ts=int(T0 + 40), text="Перезвоню через минуту")
            h.req("POST", W.TG_PUSH_PATH, json.dumps({"batch_id": "b2", "rows": [human]}).encode())
            w.tgc.tick(T0 + 60)
            assert sw.client()[0] == 1, (mode, sw.client())
        finally:
            h.stop()
        sw.no_echo_errors()


def test_pc_never_claims_press_through_service_loop():
    """Нажатие идёт тем же циклом службы (`serve`): ПК молчит — дверь ждёт свой срок, черновик not_sent, цикл жив,
    дверь WA не звана."""
    sw = SendWorld("silent", wait=20)
    w = sw.w
    w.core.tick(T0 - 1000)
    w.tgc.tick(T0 - 1000)
    sw.put(K.TGNUM, T0 - 200, text="есть байк?")
    w.http.updates = [[], [], [w.press("tg:send:1:1")], []]
    stats = w.serve(120)
    assert K.draft(w.env["tg_agent_db"])[1] == A.NOT_SENT, K.draft(w.env["tg_agent_db"])
    assert any("ПК не забрал за 20 с" in a for a in w.answers()), w.answers()
    assert sum(sw.sleeps) <= 20 + S.TG_SEND_POLL, sum(sw.sleeps)
    assert stats.get("ticks", 0) >= 3 and not stats.get("tg_tick_fail") and w.sends == [], stats
    assert O.Outbox(w.tgc.tg_outbox.path).counts() == {O.CANCELLED: 1}
    summ = [ln for ln in w.lines if ln.startswith("сводка TG:")]
    assert summ and "отправка через ПК" in summ[-1], summ


def test_wa_untouched_when_tg_send_on():
    sw = SendWorld("send")
    w = sw.w.two_drafts()
    (wcard, _), = w.cards("wa")
    assert wcard["reply_markup"] == K.GOLDEN_WA_KB, wcard
    w.tg.handle(w.press("wa:send:1:1"))
    assert w.sends == [(K.NUM, "черновик модели")] and w.answers()[-1] == "sent", (w.sends, w.answers())
    assert sw.pc.claimed == [] and K.draft(w.env["agent_db"])[1] == A.SENT
    assert type(w.core) is A.Core and w.core._door_words("sent", {"reason": "x"}) == "sent"


def test_start_words_and_clash():
    sw = SendWorld("send")
    w = sw.w
    words = w.words["WA_AGENT_TG"]
    assert " · отправка TG (WA_AGENT_TG_SEND): вкл — «Отправить» кладёт ответ в tg_outbox.db" in words, words
    line = S.tg_start_line(w.env, w.tgc, words)
    assert "отправка через userbot ПК открыта (WA_AGENT_TG_SEND): очередь tg_outbox.db, ждём подтверждения ПК до 20 с" \
        in line and S.TG_DOOR_SHUT_START not in line, line
    assert S.start_line(w.env, w.words) == K.GOLDEN_START
    # файл очереди совпал с файлом WA или агента TG — дверь закрыта, словами; флаг не запрошен — ничего
    env = w.env
    outbox, wait, words = S.tg_send_of(dict(TG_SEND, TG_OUTBOX_DB=env["queue_db"]), env)
    assert outbox is None and "совпал с файлом очереди WA" in words, words
    assert "совпал с файлом агента TG" in S.tg_send_of(dict(TG_SEND, TG_OUTBOX_DB=env["tg_agent_db"]), env)[2]
    assert S.tg_send_of(dict(K.TG_ON), env) == (None, 0, None)
    # через build: совпадение — канал собран прежним ядром, дверь закрыта, слова называют причину
    w2 = K.World(dict(TG_SEND, TG_OUTBOX_DB=os.path.join(_tmp(), "x.db")), tg=True)
    clash_env = dict(TG_SEND, TG_OUTBOX_DB=w2.env["agent_db"])
    w3 = K.World(clash_env, tg=True, env_over={"agent_db": w2.env["agent_db"]})
    assert type(w3.tgc) is A.Core and w3.tgc.door.is_open() is False, type(w3.tgc)
    assert "совпал с файлом агента WA — отправка закрыта" in w3.words["WA_AGENT_TG"], w3.words["WA_AGENT_TG"]
    assert S.TG_DOOR_SHUT_START in S.tg_start_line(w3.env, w3.tgc, w3.words["WA_AGENT_TG"])


def test_bad_wait_setting_named():
    sw = SendWorld("send", wait=999)
    assert sw.w.tgc.door.wait == 20 and "битая" in sw.w.words["WA_AGENT_TG"], sw.w.words["WA_AGENT_TG"]


# ═══ 6. флаг выключен — байт-в-байт прежнее ═══════════════════════════════════════════════

def old_tg_start_line(env, core, words):
    """Копия ДОСЛОВНАЯ `wa_agent_svc.tg_start_line` дерева e57313b (до TGSEND1310)."""
    return ("wa-agent: канал TG (%s): %s · база агента %s (своя) · очередь %s (только чтение) · отправка закрыта "
            "насовсем (is_open всегда False) · ритм, напоминание, ожидание, уроки, показ, тема → клиенту и реакции "
            "выкл · кнопки %s:… — этому ядру, читатель getUpdates — один (руки WA)"
            % (S.F_TG, words, os.path.basename(str(env.get("tg_agent_db") or "")),
               "есть" if os.path.exists(str(env.get("tg_queue_db") or "")) else "нет", S.TG_PREFIX)
            if core is not None else "wa-agent: канал TG (%s): %s" % (S.F_TG, words))


OLD_TG_WORDS = ("вкл — черновики вкл, карточки вкл · приветствие TG: эхо ≤ 10 с после первого входящего (до него 7 "
                "сут тишины) — автоприветствие, вопрос открыт")


def test_flag_off_start_line_words_core_byte_for_byte():
    for environ in (K.TG_ON, dict(K.TG_ON, WA_AGENT_TG_SEND="0"), dict(K.TG_ON, WA_AGENT_TG_SEND=""),
                    dict(K.TG_ON, WA_AGENT_TG_SEND="no"), dict(K.TG_ON, WA_AGENT_TG_SEND_SEC="5")):
        w = K.World(environ, tg=True)
        assert w.words["WA_AGENT_TG"] == OLD_TG_WORDS, (environ, w.words["WA_AGENT_TG"])
        assert S.tg_start_line(w.env, w.tgc, w.words["WA_AGENT_TG"]) == \
            old_tg_start_line(w.env, w.tgc, w.words["WA_AGENT_TG"])
        assert S.tg_start_line(w.env, None, "x") == old_tg_start_line(w.env, None, "x")
        assert S.start_line(w.env, w.words) == K.GOLDEN_START
        assert type(w.tgc) is A.Core and isinstance(w.tgc.door, S.TgDoor) and w.tgc.door.is_open() is False
        assert not os.path.exists(os.path.join(w.dir, "tg_outbox.db")), "файл очереди при выключенном флаге"
        assert not [ln for ln in w.lines if "TG_SEND" in ln or "отправка через" in ln], w.lines
        line = S.tg_summary(w.tgc, {})
        assert "отправка через ПК" not in line and S.tg_send_words(w.tgc) == ""
        w.two_drafts()
        assert w.cards("tg")[0][1] == ["tg:fix:1:1", "tg:no:1:1"]
        assert G.W_DOOR_CLOSED in w.cards("tg")[0][0]["text"]
        w.tg.handle(w.press("tg:send:1:1"))
        assert w.answers()[-1] == "отправка выключена — черновик ждёт, кнопки живы", w.answers()
        assert K.draft(w.env["tg_agent_db"])[1] == A.PENDING


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            import traceback
            print("FAIL %s %s: %s" % (name, type(e).__name__, str(e)[:400]))
            traceback.print_exc(limit=3)
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
