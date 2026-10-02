#!/usr/bin/env python3
"""Правка сообщения с телефона — новым текстом (WAPHONEEDIT0210, 02.10.2026).

СЕТИ НЕТ: Telegram выдуман (`FakeHTTP`), чужой хост роняет тест. Живой базы нет: очередь временная,
собранная схемой самого wa_webhook, архив — выдуманный схемы build_archive.py. Временные файлы тест
НЕ удаляет (правило полосы). Каркас — из tests/test_wa_mirror_ru.py.

  + вход: у edit новый текст и wamid цели — в своих колонках (edit_text, edit_to), схема — только ADD COLUMN
  + правка показанной цели — одна правка этого сообщения темы: новый текст, ниже «✏️ изменено с телефона
    ЧЧ:ММ» (текст — editMessageText, файл — editMessageCaption, хвост предыстории)
  + цель в пачке / не показана / 400 — одна строка «✏️ изменено сообщение от ЧЧ:ММ, теперь: …» ответом
  + история (файл, хвост, модель агента): у цели — последний текст с пометкой «(изменено)»
  − повтор (такт, рестарт, тот же wamid, тот же текст под другим wamid) — одна правка
  − правка без нового текста — словом «[сообщение изменено]», как до 02.10

Мутанты: WA_PHONE_EDIT_SRC=<каталог> ставит копии модулей впереди дерева.
"""

import base64
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
if os.environ.get("WA_PHONE_EDIT_SRC"):
    sys.path.insert(0, os.environ["WA_PHONE_EDIT_SRC"])

import wa_history as H       # noqa: E402
import wa_tg_mirror as M     # noqa: E402
import wa_webhook as W       # noqa: E402

logging.getLogger("wa_webhook").setLevel(logging.ERROR)


class Grab(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, rec):
        self.lines.append(rec.getMessage())


GRAB = Grab()
M.log.addHandler(GRAB)
M.log.setLevel(logging.INFO)
M.log.propagate = False

res = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    res.append(bool(cond))
    return bool(cond)


NOW0 = int(time.time())
A = "66800000011"
OUR = "66900000000"
BRANDS = {"Meta", "Telegram", "WhatsApp"}     # имена служб — не слова вида («файл Meta не отдаёт»)


class _Latin:
    """Латиница в квадратных скобках, кроме имён служб: «[revoke]», «[code_99]», «[unsupported]»."""
    def search(self, s):
        return any(set(re.findall(r"[A-Za-z]+", inner)) - BRANDS for inner in re.findall(r"\[([^\]]*)\]", s))


LATIN = _Latin()


def frm(ts, at):
    """«от ЧЧ:ММ» — тот же день по Пхукету, иначе «ДД.ММ ЧЧ:ММ» (правило строки удаления)."""
    return M.pk_hm(ts) if M.pk_date(ts) == M.pk_date(at) else M.pk_time(ts)


def wamid_of(number, key_id):
    """wamid живой формы: base64, внутри номер и key_id строками с длиной за байтом 0x18."""
    raw = (b"\x1c\x18" + bytes([len(number)]) + number.encode() + b"\x15\x02\x00\x12\x18"
           + bytes([len(key_id)]) + key_id.encode() + b"\x00")
    return "wamid." + base64.b64encode(raw).decode()


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeHTTP:
    def __init__(self):
        self.tg = []
        self.thread = 700
        self.script = {}

    def __call__(self, method, url, headers, data, timeout):
        assert url.startswith(M.TG_BASE + "/"), "чужой хост"
        meth = url.rsplit("/", 1)[1]
        if headers.get("Content-Type", "").startswith("multipart"):
            params = {"multipart": True, "body": data}
        else:
            params = json.loads(data.decode("utf-8"))
        self.tg.append((meth, params))
        if self.script.get(meth):
            st, body = self.script[meth].pop(0)
            return st, json.dumps(body).encode()
        result = {"getMe": {"id": 77, "is_bot": True},
                  "getChat": {"id": -1001, "is_forum": True},
                  "getChatMember": {"status": "administrator", "can_manage_topics": True}}.get(meth)
        if meth == "createForumTopic":
            self.thread += 1
            result = {"message_thread_id": self.thread, "name": params["name"]}
        if result is None:
            result = True if meth in ("setMessageReaction", "editForumTopic") else {"message_id": 1000 + len(self.tg)}
        return 200, json.dumps({"ok": True, "result": result}).encode()

    def calls(self, meth, since=0):
        return [p for m, p in self.tg[since:] if m == meth]

    def mid_of(self, pred):
        """id сообщения темы (FakeHTTP выдаёт 1000+номер вызова) первого вызова, где pred(метод, params)."""
        for i, (m, p) in enumerate(self.tg):
            if pred(m, p):
                return 1000 + i + 1
        return None

    def texts(self):
        out = []
        for m, p in self.tg:
            if m in ("sendMessage", "editMessageText"):
                out.append(p.get("text", ""))
            elif m == "editMessageCaption":
                out.append(p.get("caption", ""))
            elif p.get("multipart"):
                out.append(p["body"].decode("utf-8", "replace"))
        return out


TMP = tempfile.mkdtemp(prefix="wa_phone_edit_test_")
_seq = [0]


def world(arch=()):
    _seq[0] += 1
    d = os.path.join(TMP, "w%d" % _seq[0])
    os.makedirs(os.path.join(d, "arch"))
    q = W.WAQueueDB(os.path.join(d, "wa_queue.db"))
    env = {"queue_db": q.db_path, "state_db": os.path.join(d, "wa_tg_mirror.db"),
           "media_dir": os.path.join(d, "wa_media"), "d360_key": "k" * 26, "tg_token": "123:fake",
           "tg_chat": "-1001", "show": True, "archive_db": os.path.join(d, "arch", "wa_archive.db"),
           "archive_media": os.path.join(d, "arch", "m"), "archive_manifest": os.path.join(d, "arch", "m.jsonl")}
    db = sqlite3.connect(env["archive_db"])
    db.executescript("""CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT NOT NULL,
        ts INTEGER NOT NULL, from_me INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT, caption TEXT,
        transcript TEXT, media_file TEXT, key_id TEXT NOT NULL, UNIQUE (number, key_id, from_me));""")
    db.executemany("INSERT INTO messages (number, ts, from_me, kind, text, caption, transcript, media_file, "
                   "key_id) VALUES (?,?,?,?,?,?,?,?,?)", list(arch))
    db.commit()
    db.close()
    open(env["archive_manifest"], "w").close()
    clk = Clock(NOW0 + 5)
    http = FakeHTTP()
    m = M.Mirror(env, http=http, clock=clk, sleep=clk.sleep, disk_free=lambda p: 10 ** 12)
    m.tick()                                         # первое включение
    return q, env, clk, http, m


def payload(msgs, field="messages", name=""):
    val = {"messaging_product": "whatsapp", "metadata": {"display_phone_number": OUR}}
    if field == "smb_message_echoes":
        val["message_echoes"] = msgs
    else:
        val["messages"] = msgs
        val["contacts"] = [{"wa_id": A, "profile": {"name": name}}] if name else []
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": field, "value": val}]}]}


def feed(q, p):
    return q.enqueue_stats(W.normalize_wa_payload(p, OUR))


def text_msg(wid, body, ts=NOW0):
    return {"from": A, "id": wid, "timestamp": str(ts), "type": "text", "text": {"body": body}}


def revoke_msg(wid, target, ts=NOW0 + 60):
    """Удаление с телефона менеджера — эхом (smb_message_echoes), поля как в живом теле."""
    return {"from": OUR, "to": A, "to_user_id": "x", "id": wid, "timestamp": str(ts), "type": "revoke",
            "revoke": {"original_message_id": target}}


def unsupported_msg(wid, ts=NOW0 + 30):
    return {"from": A, "id": wid, "timestamp": str(ts), "type": "unsupported",
            "unsupported": {"type": "unknown", "raw_type": "x"},
            "errors": [{"code": 131060, "title": "t", "message": "m", "error_data": {"details": "d"}}]}


def edits(http, since=0):
    return http.calls("editMessageText", since) + http.calls("editMessageCaption", since)


def strike_ok(text, ent, old):
    """Длина считается здесь же, независимо от службы: единицы UTF-16 (эмодзи вне BMP — две)."""
    return (ent == [{"type": "strikethrough", "offset": 0, "length": len(old.encode("utf-16-le")) // 2}]
            and text.startswith(old + "\n"))



def echo_text(wid, body, ts=NOW0):
    """Сообщение менеджера с телефона — эхом (smb_message_echoes)."""
    return {"from": OUR, "to": A, "id": wid, "timestamp": str(ts), "type": "text", "text": {"body": body}}


def edit_msg(wid, target, body, ts=NOW0 + 60, ours=True, kind="text"):
    """Правка: поля как в живом теле досинхрона (edit.original_message_id, edit.message.text.body);
    подпись медиа — edit.message.<вид>.caption. body=None — нового текста нет."""
    m = {"type": kind}
    if body is not None:
        m[kind] = {"body": body} if kind == "text" else {"caption": body}
    d = {"from": OUR if ours else A, "id": wid, "timestamp": str(ts), "type": "edit",
         "edit": {"original_message_id": target, "message": m}}
    if ours:
        d["to"] = A
    return d


def feed_edit(q, msg):
    return feed(q, payload([msg], field="smb_message_echoes" if msg["from"] == OUR else "messages"))


MARK = "✏️ изменено с телефона "

# ─────────────────────────────────────────────────────────────────────────────
print("(0) вход: новый текст и id цели — в своих колонках; схема — только ADD COLUMN")
d0 = os.path.join(TMP, "old_schema")
os.makedirs(d0)
old_db = os.path.join(d0, "wa_queue.db")
c0 = sqlite3.connect(old_db)
c0.executescript(W._SCHEMA)
c0.execute("INSERT INTO wa_inbox (ts_queued, from_number, msg_type, text, raw, wamid) "
           "VALUES (1, 'n', 'text', 'было', '{}', 'wamid.OLD')")
c0.commit()
before = c0.execute("SELECT * FROM wa_inbox").fetchall()
c0.close()
q0 = W.WAQueueDB(old_db)
cn = q0._conn()
cols0 = [r[1] for r in cn.execute("PRAGMA table_info(wa_inbox)")]
ok("edit_to" in cols0 and "edit_text" in cols0
   and cn.execute("SELECT %s FROM wa_inbox" % ", ".join(cols0[:len(before[0])])).fetchall() == before
   and cn.execute("SELECT edit_to, edit_text FROM wa_inbox").fetchall() == [(None, None)],
   "старая очередь: колонки добавлены ADD COLUMN, прежняя строка байт в байт, новые — NULL")
feed_edit(q0, edit_msg("wamid.E0", "wamid.C0", "новый текст"))
feed_edit(q0, edit_msg("wamid.E0c", "wamid.I0", "новая подпись", kind="image"))
feed_edit(q0, edit_msg("wamid.E0n", "wamid.C0", None))
feed_edit(q0, edit_msg("wamid.E0s", "wamid.C0", "   "))
got = {w: (t, tx, et, ex) for w, t, tx, et, ex in cn.execute(
    "SELECT wamid, msg_type, text, edit_to, edit_text FROM wa_inbox WHERE msg_type='edit'")}
ok(got.get("wamid.E0") == ("edit", None, "wamid.C0", "новый текст"),
   "правка текста: edit_text — новый текст, edit_to — wamid цели, text пуст: %r" % (got.get("wamid.E0"),))
ok(got.get("wamid.E0c") == ("edit", None, "wamid.I0", "новая подпись"),
   "правка подписи медиа: edit_text — новая подпись: %r" % (got.get("wamid.E0c"),))
ok(got.get("wamid.E0n") == ("edit", None, "wamid.C0", None) and got.get("wamid.E0s") == ("edit", None, "wamid.C0", None),
   "без нового текста (нет поля, одни пробелы) — edit_text NULL, цель записана")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(1) + правка показанной цели — одна правка этого сообщения темы")
q, env, clk, http, m = world()
OLD1, NEW1 = "цена 900 бат 👋", "цена 1200 бат ✅"
feed(q, payload([echo_text("wamid.C1", OLD1)], field="smb_message_echoes"))
clk.t += 5
m.tick()
sent1 = [p["text"] for p in http.calls("sendMessage") if p["text"].endswith(OLD1)]
mid_c1 = http.mid_of(lambda mm, p: mm == "sendMessage" and p.get("text", "").endswith(OLD1))
ok(len(sent1) == 1 and mid_c1 and sent1[0].startswith(M.pk_time(NOW0) + " мы: "),
   "цель показана отдельным сообщением: id %s" % mid_c1)
n0 = len(http.tg)
feed_edit(q, edit_msg("wamid.E1", "wamid.C1", NEW1))
clk.t += 5
m.tick()
e = http.calls("editMessageText", n0)
want1 = sent1[0][:-len(OLD1)] + NEW1 + "\n" + MARK + M.pk_hm(NOW0 + 60)
ok(len(e) == 1 and e[0]["message_id"] == mid_c1, "editMessageText ровно один, на id цели: %s"
   % [x.get("message_id") for x in e])
ok(e and e[0]["text"] == want1, "новый текст в том же виде строки, ниже «✏️ изменено с телефона ЧЧ:ММ»: %r"
   % (e[0]["text"][-60:] if e else None))
ok(not http.calls("sendMessage", n0), "отдельной строки нет")
ok(m._is_shown("msg:wamid.E1"), "ключ строки правки записан")

print("\n(1б) + правка подписи файла живой ленты → editMessageCaption")
q2, env2, clk2, http2, m2 = world()
feed(q2, payload([text_msg("wamid.T0", "открыть тему")]))
img = {"from": A, "id": "wamid.I1", "timestamp": str(NOW0 + 10), "type": "image",
       "image": {"id": "MEDIA1", "mime_type": "image/jpeg", "caption": "подпись фото"}}
feed(q2, payload([img]))
fpath = os.path.join(TMP, "img1.jpg")
open(fpath, "wb").write(b"JPG")
irow = q2._conn().execute("SELECT id FROM wa_inbox WHERE wamid='wamid.I1'").fetchone()[0]
m2._media_set("wamid.I1", irow, M.M_OK, 1, path=fpath, size=3, mime="image/jpeg")
clk2.t += 5
m2.tick()
mid_i1 = http2.mid_of(lambda mm, p: mm == "sendDocument" and "подпись фото".encode() in p.get("body", b""))
n0 = len(http2.tg)
feed_edit(q2, edit_msg("wamid.E2", "wamid.I1", "новая подпись", ours=False, kind="image"))
clk2.t += 5
m2.tick()
ec = http2.calls("editMessageCaption", n0)
ok(mid_i1 and len(ec) == 1 and ec[0]["message_id"] == mid_i1 and not http2.calls("editMessageText", n0)
   and ec[0]["caption"] == "%s клиент · новая подпись\n%s%s" % (M.pk_time(NOW0 + 10), MARK, M.pk_hm(NOW0 + 60)),
   "файл — editMessageCaption на id файла: новая подпись, ниже пометка: %r" % (ec[0]["caption"] if ec else None))
ok(not http2.calls("sendMessage", n0), "строки нет")

print("\n(1в) + правка строки хвоста предыстории (одна в сообщении)")
q3, env3, clk3, http3, m3 = world()
feed(q3, payload([{"from": A, "id": "wamid.H1", "timestamp": str(NOW0 - 5 * 86400), "type": "text",
                   "text": {"body": "старое из истории"}}]))
q3._conn().execute("UPDATE wa_inbox SET history=1 WHERE wamid='wamid.H1'").connection.commit()
feed(q3, payload([text_msg("wamid.T1", "живое")]))
clk3.t += 5
m3.tick()
tail = [p["text"] for p in http3.calls("sendMessage") if p["text"].endswith("старое из истории")]
mid_h1 = http3.mid_of(lambda mm, p: mm == "sendMessage" and p.get("text", "").endswith("старое из истории"))
n0 = len(http3.tg)
feed_edit(q3, edit_msg("wamid.E3", "wamid.H1", "новое вместо старого", ours=False))
clk3.t += 5
m3.tick()
e3 = http3.calls("editMessageText", n0)
ok(len(tail) == 1 and len(e3) == 1 and e3[0]["message_id"] == mid_h1
   and e3[0]["text"] == tail[0][:-len("старое из истории")] + "новое вместо старого\n" + MARK + M.pk_hm(NOW0 + 60),
   "строка хвоста «ДД.ММ.ГГГГ ЧЧ:ММ клиент: …» — новым текстом и с пометкой: %r" % (e3[0]["text"] if e3 else None))

# ─────────────────────────────────────────────────────────────────────────────
print("\n(2) + цель в пачке → одна строка ответом на пачку, правки нет")
q6, env6, clk6, http6, m6 = world()
feed(q6, payload([{"from": A, "id": "wamid.H5", "timestamp": str(NOW0 - 5 * 86400), "type": "text",
                   "text": {"body": "первое в пачке"}},
                  {"from": A, "id": "wamid.H6", "timestamp": str(NOW0 - 5 * 86400 + 1), "type": "text",
                   "text": {"body": "второе в пачке"}}]))
q6._conn().execute("UPDATE wa_inbox SET history=1").connection.commit()
feed(q6, payload([text_msg("wamid.T6", "живое")]))
clk6.t += 5
m6.tick()
mid_batch = http6.mid_of(lambda mm, p: mm == "sendMessage" and "первое в пачке" in p.get("text", "")
                         and "второе в пачке" in p.get("text", ""))
n0 = len(http6.tg)
feed_edit(q6, edit_msg("wamid.E6", "wamid.H5", "первое, исправлено", ours=False))
clk6.t += 5
m6.tick()
l6 = http6.calls("sendMessage", n0)
ok(mid_batch and not edits(http6, n0) and len(l6) == 1
   and l6[0]["text"] == "%s клиент: ✏️ изменено сообщение от %s, теперь: первое, исправлено"
   % (M.pk_time(NOW0 + 60), frm(NOW0 - 5 * 86400, NOW0 + 60))
   and (l6[0].get("reply_parameters") or {}).get("message_id") == mid_batch,
   "пачка: правки нет (задела бы соседей), одна строка с новым текстом ответом на пачку: %r"
   % (l6[0]["text"] if l6 else None))
feed_edit(q6, edit_msg("wamid.E6dup", "wamid.H5", "первое, исправлено", ts=NOW0 + 65, ours=False))
clk6.t += 5
m6.tick()
ok(len(http6.calls("sendMessage", n0)) == 1 and not edits(http6, n0) and m6._is_shown("msg:wamid.E6dup"),
   "тот же текст под другим wamid после строки — второй строки нет")

print("\n(2б) цели нет нигде · 400 на правку → одна строка")
q4, env4, clk4, http4, m4 = world()
feed(q4, payload([text_msg("wamid.T2", "тема")]))
clk4.t += 5
m4.tick()
n0 = len(http4.tg)
feed_edit(q4, edit_msg("wamid.E4", "wamid.NOWHERE", "новое"))
clk4.t += 5
m4.tick()
l4 = http4.calls("sendMessage", n0)
ok(len(l4) == 1 and l4[0]["text"] == "%s мы: ✏️ изменено сообщение, теперь: новое" % M.pk_time(NOW0 + 60)
   and "reply_parameters" not in l4[0] and not edits(http4, n0), "цели нет нигде — строка без ответа, правки нет")
mid_t2 = http4.mid_of(lambda mm, p: mm == "sendMessage" and p.get("text", "").endswith(": тема"))
n0 = len(http4.tg)
http4.script["editMessageText"] = [(400, {"ok": False, "description": "Bad Request: message can't be edited"})]
feed_edit(q4, edit_msg("wamid.E4b", "wamid.T2", "тема поправлена", ts=NOW0 + 61, ours=False))
clk4.t += 5
m4.tick()
l4b = http4.calls("sendMessage", n0)
ok(len(http4.calls("editMessageText", n0)) == 1 and len(l4b) == 1
   and l4b[0]["text"].endswith("клиент: ✏️ изменено сообщение от %s, теперь: тема поправлена" % M.pk_hm(NOW0))
   and (l4b[0].get("reply_parameters") or {}).get("message_id") == mid_t2,
   "400 на правку — одна строка ответом на цель: %r" % (l4b[0]["text"] if l4b else None))

# ─────────────────────────────────────────────────────────────────────────────
print("\n(3) + история (файл, хвост, модель агента) видит новый текст")
K_OLD, K_ED, K_PAIR = "KOLD000001", "KED0000001", "KPAIR00001"
q5, env5, clk5, http5, m5 = world(arch=[
    (A, NOW0 - 9 * 86400, 0, "text", "в архиве до правки", None, None, None, K_OLD),
    (A, NOW0 - 8 * 86400, 1, "text", "правка из досинхрона", None, None, None, K_PAIR)])
feed(q5, payload([{"from": A, "id": "wamid.Q1", "timestamp": str(NOW0 - 7 * 86400), "type": "text",
                   "text": {"body": "очередь до правки"}}]))
feed_edit(q5, edit_msg("wamid.Q1e1", "wamid.Q1", "очередь, правка первая", ts=NOW0 - 7 * 86400 + 60, ours=False))
feed_edit(q5, edit_msg("wamid.Q1e2", "wamid.Q1", "очередь, правка последняя", ts=NOW0 - 7 * 86400 + 120, ours=False))
feed_edit(q5, edit_msg(wamid_of(A, "KEDA000001"), wamid_of(A, K_OLD), "архив, новый текст",
                       ts=NOW0 - 6 * 86400, ours=False))
feed_edit(q5, edit_msg(wamid_of(A, K_PAIR), wamid_of(A, "KGONE00001"), "правка из досинхрона",
                       ts=NOW0 - 8 * 86400))
feed_edit(q5, edit_msg("wamid.Q2e", "wamid.GONE", "цели нет, текст есть", ts=NOW0 - 5 * 86400))
feed_edit(q5, edit_msg("wamid.Q3e", "wamid.GONE2", None, ts=NOW0 - 4 * 86400))
q5._conn().execute("UPDATE wa_inbox SET history=1").connection.commit()
items, _missing = H.read_history(A, env5["queue_db"], env5["archive_db"], env5["archive_manifest"], "")
view, _n = H.model_view(items)
lines = view.split("\n")
ok(any(ln.endswith("клиент: очередь, правка последняя (изменено)") for ln in lines)
   and "очередь до правки" not in view and "правка первая" not in view,
   "модель: у цели из очереди — ПОСЛЕДНИЙ текст с пометкой, прежнего и промежуточного нет")
ok(any(ln.endswith("клиент: архив, новый текст (изменено)") for ln in lines) and "в архиве до правки" not in view,
   "модель: у цели из архива (по key_id) — новый текст с пометкой")
ok(sum(1 for ln in lines if "правка из досинхрона" in ln) == 1
   and any(ln.endswith("мы: правка из досинхрона (изменено)") for ln in lines),
   "запись архива, парная правке (цели нет), — одна, с пометкой")
ok(any(ln.endswith("мы: цели нет, текст есть (изменено)") for ln in lines)
   and any(ln.endswith("мы: [сообщение изменено]") for ln in lines),
   "цели нет — правка своей строкой: с текстом — текст и пометка; без текста — словом, как до 02.10")
ok(len(items) == 5, "строк истории 5: цель очереди, цель архива, пара, две правки без цели (правки на целях не "
   "идут строкой): %d" % len(items))
feed(q5, payload([text_msg("wamid.T5", "живое после истории")]))
clk5.t += 5
m5.tick()
hist = [p["body"].decode("utf-8", "replace") for mm, p in http5.tg if mm == "sendDocument"]
tail5 = "\n".join(p["text"] for p in http5.calls("sendMessage"))
ok(hist and "очередь, правка последняя (изменено)" in hist[0] and "очередь до правки" not in hist[0]
   and "архив, новый текст (изменено)" in hist[0], "файл истории темы — новые тексты с пометкой")
ok("очередь, правка последняя (изменено)" in tail5 and "очередь до правки" not in tail5,
   "хвост темы — новый текст с пометкой")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(4) − повтор — одна правка")
n0 = len(http.tg)
clk.t += 5
m.tick()
clk.t += 5
m.tick()
st = feed_edit(q, edit_msg("wamid.E1", "wamid.C1", NEW1))
clk.t += 5
m.tick()
m_b = M.Mirror(env, http=http, clock=clk, sleep=clk.sleep, disk_free=lambda p: 10 ** 12)    # рестарт
clk.t += 5
m_b.tick()
feed_edit(q, edit_msg("wamid.E1dup", "wamid.C1", NEW1, ts=NOW0 + 70))    # тот же текст под другим wamid
clk.t += 5
m_b.tick()
ok(st["inserted"] == 0 and not edits(http, n0) and not http.calls("sendMessage", n0)
   and len(http.calls("editMessageText")) == 1,
   "такт ×2, тот же wamid, рестарт, тот же текст под другим wamid — правка одна, строк нет")
ok(m_b._is_shown("msg:wamid.E1dup"), "повтор помечен показанным без вызова")
feed_edit(q, edit_msg("wamid.E1c", "wamid.C1", "цена 1500 бат", ts=NOW0 + 80))
clk.t += 5
m_b.tick()
e4 = http.calls("editMessageText", n0)
ok(len(e4) == 1 and e4[0]["message_id"] == mid_c1
   and e4[0]["text"] == sent1[0][:-len(OLD1)] + "цена 1500 бат\n" + MARK + M.pk_hm(NOW0 + 80),
   "новый текст той же цели — вторая правка законна: последний текст и время последней правки")
n1 = len(http.tg)
http.script["editMessageText"] = [(None, {})]
feed_edit(q, edit_msg("wamid.E1d", "wamid.C1", "цена 1600 бат", ts=NOW0 + 90))
clk.t += 5
m_b.tick()
clk.t += 5
m_b.tick()
ok(len(http.calls("editMessageText", n1)) == 1 and not http.calls("sendMessage", n1),
   "обрыв ответа на правку — повтора нет, строки нет")

print("\n(4б) удаление после правки зачёркивает НОВЫЙ текст")
qr, envr, clkr, httpr, mr = world()
feed(qr, payload([echo_text("wamid.R1", "до правки")], field="smb_message_echoes"))
clkr.t += 5
mr.tick()
sent_r = [p["text"] for p in httpr.calls("sendMessage") if p["text"].endswith("до правки")]
feed_edit(qr, edit_msg("wamid.R1e", "wamid.R1", "после правки"))
clkr.t += 5
mr.tick()
n0 = len(httpr.tg)
feed(qr, payload([revoke_msg("wamid.R1v", "wamid.R1", ts=NOW0 + 100)], field="smb_message_echoes"))
clkr.t += 5
mr.tick()
er = httpr.calls("editMessageText", n0)
now_r = sent_r[0][:-len("до правки")] + "после правки\n" + MARK + M.pk_hm(NOW0 + 60)
ok(len(er) == 1 and er[0]["text"] == now_r + "\n🗑 удалено с телефона " + M.pk_hm(NOW0 + 100)
   and strike_ok(er[0]["text"], er[0].get("entities"), now_r),
   "зачёркнуто то, что показано сейчас (новый текст и пометка правки): %r" % (er[0]["text"][:60] if er else None))

# ─────────────────────────────────────────────────────────────────────────────
print("\n(5) − правка без нового текста — словом, как до 02.10")
q7, env7, clk7, http7, m7 = world()
feed(q7, payload([echo_text("wamid.C7", "текст")], field="smb_message_echoes"))
clk7.t += 5
m7.tick()
n0 = len(http7.tg)
feed_edit(q7, edit_msg("wamid.E7", "wamid.C7", None))
feed_edit(q7, edit_msg("wamid.E7s", "wamid.C7", "  ", ts=NOW0 + 61))
clk7.t += 5
m7.tick()
l7 = [p["text"] for p in http7.calls("sendMessage", n0)]
ok(not edits(http7, n0) and l7 == ["%s мы: [сообщение изменено]" % M.pk_time(NOW0 + 60),
                                    "%s мы: [сообщение изменено]" % M.pk_time(NOW0 + 61)],
   "нет текста, одни пробелы — правки нет, строка словом «[сообщение изменено]»: %r" % l7)
legacy = {"id": 1, "ts_queued": NOW0, "from_number": A, "name": "", "msg_type": "edit", "text": None,
          "media_id": None, "mime": None, "caption": None, "media_note": None, "ts_msg": NOW0, "echo": 1,
          "history": 1, "wamid": "wamid.L1", "react_to": None}
ok(H.edit_of(legacy) == (None, None) and M.body_of(legacy) == "[сообщение изменено]",
   "строка до правки входа (колонок нет) — словом, без падения")

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
