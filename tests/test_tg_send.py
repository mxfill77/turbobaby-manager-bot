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
    """mode: send — подтвердить «ушло» (msg_id растёт) · fail — отказ · notstarted — отказ с признаком «отправка не
    начиналась» · unknown — «не уверен» · claim — забрать и молчать · silent — опрашивает (на связи), но не забирает ·
    dead — не опрашивает вовсе (ПК спит) · late — забрать, подтвердить «ушло» только по `late_ack()`.
    Опрос ПК отмечается в очереди (`pc_poll`) — так, как это делает вход wa_webhook на каждый GET."""

    def __init__(self, outbox, mode="send", msg_id=555, error="UserIsBlockedError"):
        self.outbox, self.mode, self.msg_id, self.error = outbox, mode, msg_id, error
        self.claimed, self.acks = [], []

    def poll(self):
        if self.mode != "dead" and self.outbox is not None:
            self.outbox.pc_poll()

    def step(self):
        self.poll()
        if self.mode in ("silent", "dead"):
            return
        for it in self.outbox.claim():
            self.claimed.append(it)
            if self.mode == "send":
                self.acks.append(self.outbox.ack(it["id"], it["token"], O.SENT, msg_id=self.msg_id))
                self.msg_id += 1
            elif self.mode == "fail":
                self.acks.append(self.outbox.ack(it["id"], it["token"], O.FAILED, error=self.error))
            elif self.mode == "notstarted":
                self.acks.append(self.outbox.ack(it["id"], it["token"], O.FAILED, not_started=True,
                                                 error="срок сервера на исходе (осталось 1.4 с) — отправку не начинаю"))
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
    pc.poll()                                           # ПК опрашивал очередь только что (dead — никогда)
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
    assert res == {"outcome": "not_sent", "reason": "ПК не забрал за 20 с — не отправлено", "wamid": None,
                   "retry": True}, res
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


def test_hook_push_door_closed_send_doors_404_and_no_file():
    """Двери отправки живут ровно тогда, когда дверь приёма: закрыта она — 404 как неизвестный адрес; файл
    очереди вход не заводит НИКОГДА и модуль очереди не грузит, пока файла нет."""
    tmp = _tmp()
    for over in ({"tg_channel_since": ""}, {"tg_push_secret": ""},
                 {"tg_outbox_db": os.path.join(tmp, "wa_queue.db")},           # путь очереди = файл WA
                 {"tg_outbox_db": os.path.join(tmp, "tg_queue.db")}):          # = файл очереди TG
        h = Hook(tmp, **over)
        try:
            unknown = h.req("GET", "/no-such-door")
            assert h.req("GET", W.TG_OUTBOX_PATH) == unknown == (404, b"Not found"), over
            assert h.req("POST", W.TG_ACK_PATH, b"{}") == (404, b"Not found"), over
            assert h.srv.RequestHandlerClass.tg_outbox_path == "" and h.srv.RequestHandlerClass.tg_outbox is None
        finally:
            h.stop()
    assert not os.path.exists(os.path.join(tmp, "tg_outbox.db")), "вход завёл файл очереди"
    assert W.TG_OUTBOX_FILE == O.FILE_NAME
    # дверь приёма открыта, файла нет — модуль очереди даже не импортирован (отдельный процесс: набор грузит его сам)
    probe = ("import sys, json, http.client, threading; sys.path.insert(0, %r); import wa_webhook as W; "
             "s = W.make_server(dict(verify_token='v', app_secret='', phone_id='', port=0, bind_host='127.0.0.1', "
             "queue_db=%r, d360_path_secret='', pull_secret='', tg_push_secret='s', tg_channel_since='1', "
             "tg_queue_db=%r)); threading.Thread(target=s.serve_forever, daemon=True).start(); "
             "c = http.client.HTTPConnection('127.0.0.1', s.server_address[1], timeout=30); "
             "c.request('GET', W.TG_OUTBOX_PATH, headers={'Authorization': 'Bearer s'}); r = c.getresponse(); "
             "print(r.status, json.loads(r.read())['send'], 'tg_outbox' in sys.modules); s.shutdown()"
             % (ROOT, os.path.join(tmp, "p_wa.db"), os.path.join(tmp, "p_tg.db")))
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip().splitlines()[-1] == "200 off False", (out.stdout, out.stderr[-500:])
    assert not os.path.exists(os.path.join(tmp, "tg_outbox.db"))


def test_hook_send_off_until_agent_pulse_one_switch():
    """ОДИН выключатель — у wa-agent: вход его не читает. Файла нет → «off», пусто; файл есть, пульса нет или он
    старше DOOR_FRESH → «off», и даже ряд queued НЕ выдаётся; свежий пульс → «on», ряд выдан; подтверждение
    принимается и при закрытой двери (исход ряда, взятого до закрытия, нужен сверке эха)."""
    tmp = _tmp()
    h = Hook(tmp)
    try:
        st, body = h.req("GET", W.TG_OUTBOX_PATH)
        d = json.loads(body)
        assert st == 200 and (d["send"], d["items"]) == ("off", []) and "не включалась" in d["why"], d
        assert h.req("POST", W.TG_ACK_PATH, json.dumps({"id": 1, "token": "t", "outcome": "sent",
                                                         "msg_id": 1}).encode()) == \
            (200, json.dumps({"ok": False, "error": "not_found"}).encode())
        assert not os.path.exists(os.path.join(tmp, "tg_outbox.db"))
        ob = O.Outbox(os.path.join(tmp, "tg_outbox.db"))                   # служба агента завела файл…
        c = sqlite3.connect(ob.path)
        c.execute("INSERT INTO tg_out(token, chat_id, text, state, created_at, expires_at) VALUES('q', ?, 'x', "
                  "'queued', ?, ?)", (CHAT, time.time(), time.time() + 60))    # …ряд без пульса (флаг выключили)
        c.commit()
        c.close()
        d = json.loads(h.req("GET", W.TG_OUTBOX_PATH)[1])
        assert (d["send"], d["items"]) == ("off", []) and "пульса" in d["why"], d
        ob.beat(time.time() - O.DOOR_FRESH - 5)                            # пульс протух — служба стоит
        assert json.loads(h.req("GET", W.TG_OUTBOX_PATH)[1])["send"] == "off"
        assert ob.get("q")["state"] == O.QUEUED, "при закрытой двери ряд выдан"
        ob.beat()                                                          # такт ядра с открытой дверью
        d = json.loads(h.req("GET", W.TG_OUTBOX_PATH)[1])
        assert d["send"] == "on" and [i["token"] for i in d["items"]] == ["q"], d
        ob.beat(time.time() - O.DOOR_FRESH - 5)                            # дверь закрылась после выдачи
        rid = ob.get("q")["id"]
        st, body = h.ack(id=rid, token="q", outcome="sent", msg_id=777)
        assert st == 200 and json.loads(body)["state"] == "sent", body
    finally:
        h.stop()


def test_outbox_door_pulse_rules():
    clock = K.Clock(T0)
    ob = O.Outbox(os.path.join(_tmp(), "tg_outbox.db"), clock=clock)
    assert ob.door() == (False, None)
    ob.beat()
    assert ob.door() == (True, 0.0)
    clock.t += O.DOOR_FRESH
    assert ob.door()[0] is True
    clock.t += 1
    assert ob.door()[0] is False
    ob.put(CHAT, "x", 20)                                                  # постановка — тоже пульс
    assert ob.door() == (True, 0.0)
    ob.beat(T0 + 10 ** 6)                                                  # пульс «из будущего» — незнание
    assert ob.door()[0] is False
    try:
        O.Outbox(os.path.join(_tmp(), "нет.db"), create=False)
        raise AssertionError("create=False завёл файл")
    except FileNotFoundError:
        pass


def test_hook_outbox_and_ack_contract():
    tmp = _tmp()
    h = Hook(tmp)
    try:
        ob = O.Outbox(os.path.join(tmp, "tg_outbox.db"))
        ob.beat()
        assert h.req("GET", W.TG_OUTBOX_PATH, auth="Bearer chuzhoj") == (404, b"Not found")
        assert h.req("GET", W.TG_OUTBOX_PATH, auth=None) == (404, b"Not found")
        st, body = h.req("GET", W.TG_OUTBOX_PATH)
        assert st == 200 and json.loads(body)["items"] == [] and json.loads(body)["send"] == "on", body
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
    h = Hook(tmp)
    stop = []
    got = []

    def pc():
        while not stop:
            st, body = h.req("GET", W.TG_OUTBOX_PATH)
            for it in json.loads(body).get("items", []):
                got.append(it)
                h.ack(id=it["id"], token=it["token"], outcome="sent", msg_id=31337)
            time.sleep(0.2)
    ob = O.Outbox(os.path.join(tmp, "tg_outbox.db"))
    th = threading.Thread(target=pc, daemon=True)
    th.start()
    try:
        d = S.TgDoor(ob, wait=8, poll=0.1)
        for _ in range(100):                            # ПК опросил вход — вход отметил «ПК на связи»
            if ob.pc()[0]:
                break
            time.sleep(0.05)
        assert ob.pc()[0], "вход не отметил опрос ПК"
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
        self.pc.poll()                                  # ПК на связи с первой минуты (dead — никогда)

    def pc_alive_always(self):
        """ПК опрашивает очередь всё время (цикл службы двигает часы на десятки секунд между нажатиями)."""
        self.pc.outbox.pc = lambda now=None, fresh=O.PC_FRESH: (True, 0.0)
        return self

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
    """Нажатие идёт тем же циклом службы (`serve`): ПК на связи, но ряд не забирает — дверь ждёт свой срок, ряд
    отменён, черновик ВОЗВРАЩАЕТСЯ ждать (круг 2: клиенту доказанно ничего не ушло), цикл жив, дверь WA не звана."""
    sw = SendWorld("silent", wait=20).pc_alive_always()
    w = sw.w
    w.core.tick(T0 - 1000)
    w.tgc.tick(T0 - 1000)
    sw.put(K.TGNUM, T0 - 200, text="есть байк?")
    w.http.updates = [[], [], [w.press("tg:send:1:1")], []]
    stats = w.serve(120)
    assert K.draft(w.env["tg_agent_db"])[1] == A.PENDING, K.draft(w.env["tg_agent_db"])
    assert any("ПК не забрал за 20 с" in a and "черновик ждёт, кнопки живы" in a for a in w.answers()), w.answers()
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


def test_core_tick_writes_door_pulse_flag_off_writes_nothing():
    sw = SendWorld("send")
    w = sw.w
    ob = w.tgc.tg_outbox
    assert ob.door(w.clock.t)[0] is True                                   # пульс при сборке
    w.clock.t += O.DOOR_FRESH + 30
    assert ob.door(w.clock.t)[0] is False                                  # служба «стоит» — дверь закрылась
    w.tgc.tick(w.clock.t)
    assert ob.door(w.clock.t) == (True, 0.0)                               # такт ядра — пульс
    two = S.TwoCores(w.core, w.tgc, w.lines.append, {})
    w.clock.t += O.DOOR_FRESH + 30
    two.tick(w.clock.t)                                                    # тем же путём, что в цикле службы
    assert ob.door(w.clock.t)[0] is True
    off = K.World(K.TG_ON, tg=True)                                        # флаг не запрошен — ни файла, ни пульса
    off.tgc.tick(T0)
    assert not os.path.exists(os.path.join(off.dir, "tg_outbox.db"))


def test_bad_wait_setting_named():
    sw = SendWorld("send", wait=999)
    assert sw.w.tgc.door.wait == 20 and "битая" in sw.w.words["WA_AGENT_TG"], sw.w.words["WA_AGENT_TG"]


# ═══ 7. круг правок 2 (ревью 5d9b415) ═════════════════════════════════════════════════════

def _st(w, did=1):
    return w.tgc.db.execute("SELECT state, decided_by FROM drafts WHERE id=?", (did,)).fetchone()


def test_r2_proven_not_sent_returns_draft_to_pending():
    """П.1: ПК на связи, но ряд не забрал за срок (ряд отменён — клиенту доказанно ничего не ушло): черновик назад в
    pending (decided_by пуст), done_upto не тронут, карточка не правилась — кнопки живы; ПК ожил — то же «Отправить»
    уходит. Отказ ПК с признаком «отправка не начиналась» — тоже назад ждать; отказ без признака — прежний конец."""
    sw = SendWorld("silent", wait=20).draft()
    w = sw.w
    before = sw.client()
    edits0 = len(w.http.of("editMessageText"))
    w.tg.handle(w.press("tg:send:1:1"))
    assert _st(w) == (A.PENDING, None), _st(w)
    assert sw.client()[2] == before[2] and sw.client()[3] == before[3] > before[2], (sw.client(), before)
    assert len(w.http.of("editMessageText")) == edits0, "карточку правили — кнопки сняты"
    assert w.answers()[-1] == "ПК не забрал за 20 с — не отправлено — черновик ждёт, кнопки живы", w.answers()
    assert O.Outbox(sw.pc.outbox.path).counts() == {O.CANCELLED: 1}
    sw.pc.mode = "send"                                                    # ПК ожил — то же «Отправить»
    w.tg.handle(w.press("tg:send:1:1"))
    assert K.draft(w.env["tg_agent_db"])[1] == A.SENT, K.draft(w.env["tg_agent_db"])
    assert w.answers()[-1].startswith("sent — ушло через userbot на ПК"), w.answers()
    sw2 = SendWorld("notstarted").draft()
    sw2.w.tg.handle(sw2.w.press("tg:send:1:1"))
    assert _st(sw2.w) == (A.PENDING, None), _st(sw2.w)
    assert "ПК не начинал отправку: срок сервера на исходе" in sw2.w.answers()[-1], sw2.w.answers()
    sw3 = SendWorld("fail").draft()
    sw3.w.tg.handle(sw3.w.press("tg:send:1:1"))
    assert _st(sw3.w)[0] == A.NOT_SENT, _st(sw3.w)                       # отказ Telegram — конец, как было


def test_r2_pc_offline_answered_at_once_without_capture():
    """П.1: ПК не опрашивал очередь дольше PC_FRESH — «Отправить» отвечает сразу «ПК не на связи», черновик не
    захвачен, ряда нет, дверь не ждала ни секунды (цикл службы не стоит 20 с); 16 с — не на связи, 14 с — на связи.
    Дверь сама (ПК пропал между нажатием и постановкой) — not_sent с признаком повтора, без ряда и ожидания."""
    sw = SendWorld("dead").draft()
    w = sw.w
    t0 = w.clock.t
    w.tg.handle(w.press("tg:send:1:1"))
    assert _st(w) == (A.PENDING, None), _st(w)
    assert w.answers()[-1] == "ПК не на связи (ещё не опрашивал очередь) — черновик ждёт, кнопки живы", w.answers()
    assert sw.sleeps == [] and w.clock.t == t0 and rows(sw.pc.outbox) == []
    sw.pc.outbox.pc_poll(w.clock.t - 16)
    w.tg.handle(w.press("tg:send:1:1"))
    assert "ПК не на связи (последний опрос 16 с назад" in w.answers()[-1] and _st(w)[0] == A.PENDING, w.answers()
    sw.pc.outbox.pc_poll(w.clock.t - 14)
    sw.pc.mode = "send"
    w.tg.handle(w.press("tg:send:1:1"))
    assert _st(w)[0] == A.SENT, (_st(w), w.answers())
    d, ob, pc, tk, clock = door("dead")
    res = d.send_text("tg:%d" % CHAT, "x")
    assert res["outcome"] == "not_sent" and res.get("retry") is True and res["reason"].startswith("ПК не на связи"), res
    assert rows(ob) == [] and tk.sleeps == []


def test_r2_hook_stamps_pc_poll_and_ack_contract():
    """Вход отмечает КАЖДЫЙ опрос ПК (и «off», и «on»); ack несёт not_started (только у failed, только true)."""
    tmp = _tmp()
    h = Hook(tmp)
    try:
        ob = O.Outbox(os.path.join(tmp, "tg_outbox.db"))
        assert ob.pc() == (False, None)
        assert json.loads(h.req("GET", W.TG_OUTBOX_PATH)[1])["send"] == "off"     # пульса агента нет — «off»…
        alive, age = ob.pc()
        assert alive and 0 <= age < 5, (alive, age)                             # …но ПК на связи
        ob.pc_poll(time.time() - O.PC_FRESH - 1)
        assert ob.pc()[0] is False
        ob.beat()
        assert json.loads(h.req("GET", W.TG_OUTBOX_PATH)[1])["send"] == "on" and ob.pc()[0] is True
        rows_ = []
        for _ in range(3):
            rows_.append(ob.put(CHAT, "x", 60, now=time.time()))
        items = json.loads(h.req("GET", W.TG_OUTBOX_PATH)[1])["items"]
        assert len(items) == 3
        (r1, t1), (r2, t2), (r3, t3) = rows_
        st, body = h.ack(id=r1, token=t1, outcome="failed", error="срок", not_started=True)
        assert st == 200 and ob.get(t1)["not_started"] == 1, body
        h.ack(id=r2, token=t2, outcome="failed", error="x", not_started="yes")      # не true — признака нет
        h.ack(id=r3, token=t3, outcome="sent", msg_id=11, not_started=True)        # у sent признака не бывает
        assert ob.get(t2)["not_started"] == 0 and ob.get(t3)["not_started"] == 0
        # файл очереди прежней схемы (до круга 2) получает столбец признака при открытии
        old = os.path.join(_tmp(), "old.db")
        c = sqlite3.connect(old)
        c.executescript("CREATE TABLE tg_out (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL UNIQUE, "
                        "chat_id INTEGER NOT NULL, text TEXT NOT NULL, state TEXT NOT NULL, created_at REAL NOT NULL, "
                        "expires_at REAL NOT NULL, claimed_at REAL, handed INTEGER NOT NULL DEFAULT 0, door_gave_up "
                        "REAL, acked_at REAL, msg_id INTEGER, error TEXT, cancel_why TEXT); CREATE TABLE meta (key "
                        "TEXT PRIMARY KEY, value TEXT NOT NULL);")
        c.close()
        ob_old = O.Outbox(old)
        assert ob_old.get(ob_old.put(CHAT, "x", 20)[1])["not_started"] == 0
    finally:
        h.stop()


def test_r2_give_up_race_returns_the_pc_outcome():
    """П.3: ПК подтвердил «ушло» между последним чтением двери и её отказом ждать — дверь отвечает sent, а не
    ложным «неизвестно»."""
    d, ob, pc, tk, clock = door("claim", wait=10)
    real = ob.give_up

    def racing(token, now=None):
        it = pc.claimed[-1]
        ob.ack(it["id"], it["token"], O.SENT, msg_id=4444)
        return real(token, now=now)
    ob.give_up = racing
    res = d.send_text("tg:%d" % CHAT, "x")
    assert res["outcome"] == "sent" and res["wamid"] == W.tg_wamid(CHAT, 4444, "out"), res


def test_r2_too_long_checked_before_capture():
    """П.4: текст длиннее 4096 (единиц UTF-16) — «Отправить» отвечает ДО захвата: черновик pending, кнопки живы,
    совет «сократите через Исправить» выполним; ряда нет. Ровно 4096 — уходит."""
    sw = SendWorld("send").draft()
    w = sw.w
    w.tgc.db.execute("UPDATE drafts SET text=? WHERE id=1", ("я" * 4097,))
    w.tg.handle(w.press("tg:send:1:1"))
    assert _st(w) == (A.PENDING, None), _st(w)
    a = w.answers()[-1]
    assert "4097 знаков" in a and "«Исправить»" in a and "черновик ждёт" in a, a
    assert rows(sw.pc.outbox) == [] and sw.sleeps == []
    w.tgc.db.execute("UPDATE drafts SET text=? WHERE id=1", ("я" * 4096,))
    w.tg.handle(w.press("tg:send:1:1"))
    assert _st(w)[0] == A.SENT, (_st(w), w.answers())


def _feed_row(cid, mid, d, ts, text="x"):
    return {"chat_id": cid, "msg_id": mid, "dir": d, "ts": ts, "kind": "text", "text": text, "reply_to": None,
            "sender_id": 1}


def _push(h, rows_, batch):
    st, body = h.req("POST", W.TG_PUSH_PATH, json.dumps({"batch_id": batch, "rows": rows_}).encode())
    assert st == 200, body
    return json.loads(body)


def test_r2_live_row_cancels_queued_rows_of_that_chat():
    """П.6 (перенос d767d2c): пока дверь ждёт, клиент написал или ответили с телефона — queued-ряды ЭТОГО чата
    отменяются (ответ агента устарел); забранный ПК ряд не трогаем; эхо НАШЕЙ отправки и ряд истории — не отменяют;
    дверь отвечает not_sent с признаком повтора и причиной."""
    tmp = _tmp()
    h = Hook(tmp)
    other = CHAT + 1

    def push(cid, mid, d, ts, text="x"):
        _push(h, [_feed_row(cid, mid, d, ts, text)], "b%d" % mid)
    try:
        ob = O.Outbox(os.path.join(tmp, "tg_outbox.db"))
        ob.beat()
        now = time.time()
        r3, t3 = ob.put(CHAT, "забранный", 60, now=now)
        ob.claim(now=now)
        _, t1 = ob.put(CHAT, "ждёт", 60, now=now)
        _, t2 = ob.put(other, "другой чат", 60, now=now)
        push(CHAT, 100, "in", SINCE + 10, "а ещё вопрос")
        assert ob.get(t1)["state"] == O.CANCELLED and ob.get(t1)["cancel_why"].startswith("клиент написал ещё")
        assert ob.get(t2)["state"] == O.QUEUED and ob.get(t3)["state"] == O.CLAIMED
        fin = S.TgDoor(ob, wait=20)._final(ob.get(t1))
        assert fin == {"outcome": "not_sent", "reason": "клиент написал ещё — не отправлено", "wamid": None,
                       "retry": True}, fin
        push(other, 101, "in", SINCE - 10)                                   # история — не живой ряд
        assert ob.get(t2)["state"] == O.QUEUED
        ob.ack(r3, t3, O.SENT, msg_id=4242)
        _, t5 = ob.put(CHAT, "ещё один", 60, now=time.time())
        push(CHAT, 4242, "out", SINCE + 20, "забранный")                     # эхо НАШЕЙ отправки
        assert ob.get(t5)["state"] == O.QUEUED and ob.get(t3)["state"] == O.SENT
        push(other, 9999, "out", SINCE + 30, "ответ с телефона")             # эхо не нашей отправки
        assert ob.get(t2)["state"] == O.CANCELLED and ob.get(t2)["cancel_why"].startswith("ответили с телефона")
        assert ob.get(t5)["state"] == O.QUEUED
    finally:
        h.stop()


def test_r2_resent_batch_cancels_nothing_receipt_unchanged():
    """R2B-3: пушер ПК повторяет УЖЕ принятую пачку (ответ потерян) — строка уже на диске, этим запросом не вставлена:
    свежий queued-ряд того же чата НЕ отменяется, ответ пачки (accepted) — тот же, что у первой; вход до нажатия
    ничего не отменяет. Действительно новая строка того же чата — отменяет."""
    tmp = _tmp()
    h = Hook(tmp)
    try:
        ob = O.Outbox(os.path.join(tmp, "tg_outbox.db"))
        ob.beat()
        old = _feed_row(CHAT, 100, "in", SINCE + 10, "вопрос, на который агент отвечает")
        phone_old = _feed_row(CHAT, 9001, "out", SINCE + 11, "давний ответ с телефона")
        first = _push(h, [old, phone_old], "b1")                            # вход ДО нажатия — отменять нечего
        assert first == {"ok": True, "accepted": [[CHAT, 100, "in"], [CHAT, 9001, "out"]], "malformed": 0}, first
        _, tok = ob.put(CHAT, "ответ агента на вопрос 100", 60, now=time.time())   # «Отправить» нажато
        again = _push(h, [old, phone_old], "b1")                            # та же пачка ещё раз
        assert again == first, (again, first)
        assert ob.get(tok)["state"] == O.QUEUED and ob.get(tok)["cancel_why"] is None, ob.get(tok)
        again2 = _push(h, [phone_old], "b1-tail")                           # повтор хвоста с «чужим» эхом
        assert again2["accepted"] == [[CHAT, 9001, "out"]] and ob.get(tok)["state"] == O.QUEUED
        c = sqlite3.connect(os.path.join(tmp, "tg_queue.db"))
        try:
            n = c.execute("SELECT COUNT(*) FROM wa_inbox WHERE wamid LIKE ?", ("tg:%d:%%" % CHAT,)).fetchone()[0]
        finally:
            c.close()
        assert n == 2, n                                                    # дубля входящего нет
        # то же сообщение клиента, но НОВОЕ (другой msg_id) — ответ устарел, отмена
        new = _push(h, [old, _feed_row(CHAT, 101, "in", SINCE + 12, "Уже не надо, нашёл байк у другого")], "b2")
        assert new["accepted"] == [[CHAT, 100, "in"], [CHAT, 101, "in"]], new
        assert ob.get(tok)["state"] == O.CANCELLED and ob.get(tok)["cancel_why"].startswith("клиент написал ещё")
    finally:
        h.stop()


def test_r2_foreign_chat_row_and_mixed_resend():
    """Чужой чат: новая строка чата Y не трогает queued чата X; пачка «повтор старой строки X + новая строка Y» отменяет
    ТОЛЬКО ряды Y. Группа (chat_id ≤ 0) не отменяет ничего."""
    tmp = _tmp()
    h = Hook(tmp)
    y = CHAT + 7
    try:
        ob = O.Outbox(os.path.join(tmp, "tg_outbox.db"))
        ob.beat()
        old_x = _feed_row(CHAT, 200, "in", SINCE + 10)
        _push(h, [old_x], "b1")
        _, tx = ob.put(CHAT, "ответ X", 60, now=time.time())
        _, ty = ob.put(y, "ответ Y", 60, now=time.time())
        _push(h, [_feed_row(-1001234, 5, "in", SINCE + 15, "группа")], "g")
        assert ob.get(tx)["state"] == O.QUEUED and ob.get(ty)["state"] == O.QUEUED
        got = _push(h, [old_x, _feed_row(y, 300, "in", SINCE + 20, "клиент Y написал")], "b2")
        assert got["accepted"] == [[CHAT, 200, "in"], [y, 300, "in"]], got
        assert ob.get(tx)["state"] == O.QUEUED, ob.get(tx)
        assert ob.get(ty)["state"] == O.CANCELLED and ob.get(ty)["cancel_why"].startswith("клиент написал ещё")
    finally:
        h.stop()


def test_r2_cancel_failure_keeps_the_push_receipt():
    """Сбой отмены (исключение в очереди отправки) — приём пачки не страдает: 200, accepted прежний, строка на диске;
    queued-ряд остаётся (дверь доживёт свой срок как прежде)."""
    tmp = _tmp()
    h = Hook(tmp)

    class Broken(O.Outbox):
        def cancel_chat(self, chat_id, why):
            raise sqlite3.OperationalError("disk I/O error (подделка теста)")
    try:
        ob = O.Outbox(os.path.join(tmp, "tg_outbox.db"))
        ob.beat()
        _, tok = ob.put(CHAT, "ответ агента", 60, now=time.time())
        h.srv.RequestHandlerClass.tg_outbox = Broken(ob.path, create=False)
        got = _push(h, [_feed_row(CHAT, 400, "in", SINCE + 10, "ещё вопрос")], "b1")
        assert got == {"ok": True, "accepted": [[CHAT, 400, "in"]], "malformed": 0}, got
        assert ob.get(tok)["state"] == O.QUEUED
        c = sqlite3.connect(os.path.join(tmp, "tg_queue.db"))
        try:
            assert c.execute("SELECT COUNT(*) FROM wa_inbox WHERE wamid=?",
                             (W.tg_wamid(CHAT, 400, "in"),)).fetchone()[0] == 1
        finally:
            c.close()
    finally:
        h.stop()


def test_w15_readback_failure_after_commit_still_cancels_queued_answer():
    """W15 (TGW15): значимая новая строка клиента уже ЗАКОММИЧЕНА, ответ агента ещё queued, а обратное чтение пачки
    упало ОДИН раз (диск) — вход отвечает 500 «ничего не подтверждено», но строку, вставленную ЭТИМ запросом, судит как
    новую: queued-ряд чата отменён, ПК его не получит (GET outbox пуст при открытой двери), дверь вернёт черновик ждать.
    Штатный повтор пушера — 200 с обычной квитанцией, строка на диске одна, и повтор не отменяет НИЧЕГО: отмена в
    журнале ровно одна, отменённый ряд прежний, новый ряд, поставленный после сбоя, остаётся queued."""
    import logging
    tmp = _tmp()
    h = Hook(tmp)
    real = h.srv.RequestHandlerClass.tg_db
    flaky = {"n": 1}

    class FlakyConn(sqlite3.Connection):
        def execute(self, sql, *a):
            if flaky["n"] > 0 and sql.startswith("SELECT wamid FROM wa_inbox WHERE wamid IN"):
                flaky["n"] -= 1
                raise sqlite3.OperationalError("disk I/O error (подделка теста: обратное чтение)")
            return super().execute(sql, *a)

    class FlakyDB(W.WAQueueDB):
        def _conn(self):
            return sqlite3.connect(self.db_path, check_same_thread=False, timeout=10, factory=FlakyConn)

    seen = []

    class Grab(logging.Handler):
        def emit(self, rec):
            seen.append(rec.getMessage())
    grab = Grab()
    logging.getLogger("wa_webhook").addHandler(grab)
    why = "клиент написал ещё — не отправлено"
    try:
        ob = O.Outbox(os.path.join(tmp, "tg_outbox.db"))
        ob.beat()
        _, tok = ob.put(CHAT, "ответ агента на вопрос 100", 60, now=time.time())     # «Отправить» нажато
        row = _feed_row(CHAT, 101, "in", SINCE + 12, "Уже не надо, нашёл байк у другого")
        h.srv.RequestHandlerClass.tg_db = FlakyDB(real.db_path)
        try:
            st, raw = h.req("POST", W.TG_PUSH_PATH, json.dumps({"batch_id": "w15", "rows": [row]}).encode())
        finally:
            h.srv.RequestHandlerClass.tg_db = real
        assert flaky["n"] == 0, "сбой обратного чтения не случился — тест не задел ветку W15"
        assert (st, json.loads(raw)) == (500, {"ok": False, "error": "push_failed"}), (st, raw)
        assert ob.get(tok)["state"] == O.CANCELLED and ob.get(tok)["cancel_why"] == why, ob.get(tok)
        got = json.loads(h.req("GET", W.TG_OUTBOX_PATH)[1])
        assert got["send"] == "on" and got["items"] == [], got                     # устаревший ответ ПК не получит
        fin = S.TgDoor(ob, wait=20)._final(ob.get(tok))
        assert fin == {"outcome": "not_sent", "reason": why, "wamid": None, "retry": True}, fin
        _, tok2 = ob.put(CHAT, "новый ответ после сбоя", 60, now=time.time())
        again = _push(h, [row], "w15")                                            # штатный повтор пушера ПК
        assert again == {"ok": True, "accepted": [[CHAT, 101, "in"]], "malformed": 0}, again
        assert ob.get(tok2)["state"] == O.QUEUED and ob.get(tok2)["cancel_why"] is None, ob.get(tok2)
        assert ob.get(tok)["state"] == O.CANCELLED and ob.get(tok)["cancel_why"] == why, ob.get(tok)
        assert [m for m in seen if "queued rows cancelled" in m] == \
            ["TG outbox: 1 queued rows cancelled — a new live row came in their chat"], seen
        assert [m for m in seen if m.startswith("TG push: queue write failed, NOTHING accepted")], seen
        c = sqlite3.connect(os.path.join(tmp, "tg_queue.db"))
        try:
            assert c.execute("SELECT COUNT(*) FROM wa_inbox WHERE wamid=?",
                             (W.tg_wamid(CHAT, 101, "in"),)).fetchone()[0] == 1
        finally:
            c.close()
    finally:
        logging.getLogger("wa_webhook").removeHandler(grab)
        h.srv.RequestHandlerClass.tg_db = real
        h.stop()


def test_enqueue_confirmed_names_only_rows_it_inserted():
    """Дверь записи пачки: ответ — все ключи на диске (и повторные), `inserted` — только вставленные ЭТИМ вызовом;
    без `inserted` — прежний ответ; ошибка — в `inserted` ничего."""
    db = W.WAQueueDB(os.path.join(_tmp(), "tg_queue.db"))

    def ev(mid):
        return W.tg_row_event(_feed_row(CHAT, mid, "in", SINCE + mid), SINCE)[1]
    a = set()
    assert db.enqueue_confirmed([ev(1), ev(2)], source=W.TG_SOURCE, inserted=a) == {W.tg_wamid(CHAT, 1, "in"),
                                                                                    W.tg_wamid(CHAT, 2, "in")}
    assert a == {W.tg_wamid(CHAT, 1, "in"), W.tg_wamid(CHAT, 2, "in")}, a
    b = set()
    assert db.enqueue_confirmed([ev(1), ev(2)], source=W.TG_SOURCE, inserted=b) == a and b == set(), b
    c = set()
    assert db.enqueue_confirmed([ev(2), ev(3), ev(3)], source=W.TG_SOURCE, inserted=c) == \
        {W.tg_wamid(CHAT, 2, "in"), W.tg_wamid(CHAT, 3, "in")}
    assert c == {W.tg_wamid(CHAT, 3, "in")}, c
    assert db.enqueue_confirmed([ev(1)], source=W.TG_SOURCE) == {W.tg_wamid(CHAT, 1, "in")}
    bad = dict(ev(9))
    bad["wamid"] = ""
    d = set()
    try:
        db.enqueue_confirmed([ev(8), bad], source=W.TG_SOURCE, inserted=d)
        raise AssertionError("ряд без wamid принят")
    except ValueError:
        pass
    assert d == set(), d


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
