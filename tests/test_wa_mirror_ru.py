#!/usr/bin/env python3
"""Все виды сообщений в темах «WhatsApp · Turbobaby» — по-русски (WAMIRRRU0210, 02.10.2026).

СЕТИ НЕТ: Telegram выдуман (`FakeHTTP`), чужой хост роняет тест. Живой базы нет: очередь временная,
собранная схемой самого wa_webhook, архив — выдуманный схемы build_archive.py. Временные файлы тест
НЕ удаляет (правило полосы).

  + revoke, цель показана одна — правка ЭТОГО сообщения темы: прежний текст зачёркнут, ниже
    «🗑 удалено с телефона ЧЧ:ММ» (текст — editMessageText, файл — editMessageCaption, хвост предыстории)
  + revoke без показанной цели — одна строка «🗑 удалено сообщение от ЧЧ:ММ» (цель в очереди, в архиве,
    нигде); правку чат не принял (400) — тоже строка
  + unsupported — русским словом: в теме, в файле истории, в строке модели; сторона — клиент
  − ни один вид не даёт латиницу в скобках; неизвестный — «[сообщение неизвестного вида]» и строка журнала
  − повтор тела (такт, рестарт, тот же wamid, второй revoke той же цели) — одна правка

Мутанты: WA_MIRROR_RU_SRC=<каталог> ставит копии модулей впереди дерева.
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
if os.environ.get("WA_MIRROR_RU_SRC"):
    sys.path.insert(0, os.environ["WA_MIRROR_RU_SRC"])

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


TMP = tempfile.mkdtemp(prefix="wa_mirror_ru_test_")
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
    return (ent == [{"type": "strikethrough", "offset": 0, "length": M.utf16_len(old)}]
            and text.startswith(old + "\n"))


# ─────────────────────────────────────────────────────────────────────────────
print("(1) revoke: цель показана одна — правка этого сообщения темы")
q, env, clk, http, m = world()
feed(q, payload([text_msg("wamid.C1", "привет 👋 как дела")], name="Анна"))
clk.t += 5
m.tick()
sent_text = [p["text"] for p in http.calls("sendMessage") if p["text"].endswith("привет 👋 как дела")]
mid_c1 = http.mid_of(lambda mm, p: mm == "sendMessage" and p.get("text", "").endswith("привет 👋 как дела"))
ok(len(sent_text) == 1 and mid_c1, "цель показана отдельным сообщением: id %s" % mid_c1)
n0 = len(http.tg)
feed(q, payload([revoke_msg("wamid.V1", "wamid.C1")], field="smb_message_echoes"))
row = q._conn().execute("SELECT msg_type, echo, raw FROM wa_inbox WHERE wamid='wamid.V1'").fetchone()
ok(row[0] == "revoke" and row[1] == 1 and json.loads(row[2])["revoke"]["original_message_id"] == "wamid.C1",
   "вход: строка revoke эхом, цель — revoke.original_message_id в raw")
clk.t += 5
m.tick()
e = http.calls("editMessageText", n0)
mark = "🗑 удалено с телефона " + M.pk_hm(NOW0 + 60)
ok(len(e) == 1 and e[0]["message_id"] == mid_c1, "editMessageText ровно один, на id цели: %s" % [x.get("message_id") for x in e])
ok(e and e[0]["text"] == sent_text[0] + "\n" + mark,
   "прежний текст оставлен дословно, ниже «🗑 удалено с телефона ЧЧ:ММ»: %r" % (e[0]["text"][-40:] if e else None))
ok(e and strike_ok(e[0]["text"], e[0].get("entities"), sent_text[0]),
   "прежний текст зачёркнут (strikethrough, длина в UTF-16 с эмодзи: %d)" % M.utf16_len(sent_text[0]))
ok(not [p for p in http.calls("sendMessage", n0) if "удал" in p.get("text", "")],
   "отдельной строки об удалении нет")
ok(m._is_shown("msg:wamid.V1") and m._is_shown("rev:wamid.C1"), "ключ строки и «цель помечена» записаны")

print("\n(1б) revoke: цель — файл живой ленты → editMessageCaption")
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
feed(q2, payload([revoke_msg("wamid.V2", "wamid.I1")], field="smb_message_echoes"))
clk2.t += 5
m2.tick()
ec = http2.calls("editMessageCaption", n0)
old_cap = "%s клиент · подпись фото" % M.pk_time(NOW0 + 10)
ok(mid_i1 and len(ec) == 1 and ec[0]["message_id"] == mid_i1 and not http2.calls("editMessageText", n0),
   "файл — editMessageCaption на id файла, editMessageText нет")
ok(ec and ec[0]["caption"] == old_cap + "\n🗑 удалено с телефона " + M.pk_hm(NOW0 + 60)
   and strike_ok(ec[0]["caption"], ec[0].get("caption_entities"), old_cap),
   "подпись прежняя, зачёркнута, ниже пометка: %r" % (ec[0]["caption"][-30:] if ec else None))

print("\n(1в) revoke: цель — хвост предыстории (одна в сообщении) → правка строки хвоста")
q3, env3, clk3, http3, m3 = world()
feed(q3, payload([{"from": A, "id": "wamid.H1", "timestamp": str(NOW0 - 5 * 86400), "type": "text",
                   "text": {"body": "старое из истории"}}], field="messages"))
q3._conn().execute("UPDATE wa_inbox SET history=1 WHERE wamid='wamid.H1'").connection.commit()
feed(q3, payload([text_msg("wamid.T1", "живое")]))
clk3.t += 5
m3.tick()
tail = [p["text"] for p in http3.calls("sendMessage") if p["text"].endswith("старое из истории")]
mid_h1 = http3.mid_of(lambda mm, p: mm == "sendMessage" and p.get("text", "").endswith("старое из истории"))
n0 = len(http3.tg)
feed(q3, payload([revoke_msg("wamid.V3", "wamid.H1")], field="smb_message_echoes"))
clk3.t += 5
m3.tick()
e3 = http3.calls("editMessageText", n0)
ok(len(tail) == 1 and len(e3) == 1 and e3[0]["message_id"] == mid_h1
   and e3[0]["text"] == tail[0] + "\n🗑 удалено с телефона " + M.pk_hm(NOW0 + 60),
   "строка хвоста «ДД.ММ.ГГГГ ЧЧ:ММ клиент: …» восстановлена дословно и помечена")

print("\n(1г) revoke: цель в пачке хвоста (не одна в сообщении) → строка ответом, правки нет")
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
feed(q6, payload([revoke_msg("wamid.V9", "wamid.H5")], field="smb_message_echoes"))
clk6.t += 5
m6.tick()
l9 = [p for p in http6.calls("sendMessage", n0) if "удал" in p["text"]]
ok(mid_batch and not edits(http6, n0) and len(l9) == 1
   and l9[0]["text"].endswith("🗑 удалено сообщение от " + frm(NOW0 - 5 * 86400, NOW0 + 60))
   and (l9[0].get("reply_parameters") or {}).get("message_id") == mid_batch,
   "пачка: правки нет (правка задела бы соседей), одна строка ответом на пачку")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(2) revoke без показанной цели — одна строка")
KARCH = "KARCH000001"
q4, env4, clk4, http4, m4 = world(arch=[(A, NOW0 - 3600, 0, "text", "из архива", None, None, None, KARCH)])
feed(q4, payload([text_msg("wamid.T2", "тема")]))
clk4.t += 5
m4.tick()
n0 = len(http4.tg)
feed(q4, payload([revoke_msg("wamid.V4", "wamid.NOWHERE")], field="smb_message_echoes"))
clk4.t += 5
m4.tick()
lines4 = [p for p in http4.calls("sendMessage", n0) if "удал" in p["text"]]
ok(len(lines4) == 1 and lines4[0]["text"].endswith("мы: 🗑 удалено сообщение — какое, неизвестно")
   and not edits(http4, n0), "цели нет нигде — одна строка «какое, неизвестно», правки нет")
feed(q4, payload([revoke_msg("wamid.V4b", "wamid.NOWHERE", ts=NOW0 + 61)], field="smb_message_echoes"))
clk4.t += 5
m4.tick()
ok(len([p for p in http4.calls("sendMessage", n0) if "удал" in p["text"]]) == 1,
   "второй revoke той же цели после строки — второй строки нет")
n0 = len(http4.tg)
feed(q4, payload([revoke_msg("wamid.V5", wamid_of(A, KARCH))], field="smb_message_echoes"))
clk4.t += 5
m4.tick()
lines5 = [p["text"] for p in http4.calls("sendMessage", n0) if "удал" in p["text"]]
ok(len(lines5) == 1 and lines5[0].endswith("🗑 удалено сообщение от " + frm(NOW0 - 3600, NOW0 + 60))
   and not edits(http4, n0), "цель только в архиве — одна строка «от ЧЧ:ММ» по времени архива: %r" % lines5[-1:])
# цель показана до хранения id (msg_id пуст) — строка, а не правка
feed(q4, payload([text_msg("wamid.C9", "показано до хранения id", ts=NOW0 + 20)]))
clk4.t += 5
m4.tick()
m4.st.execute("UPDATE shown SET msg_id=NULL WHERE key='msg:wamid.C9'")
m4.st.commit()
n0 = len(http4.tg)
feed(q4, payload([revoke_msg("wamid.V6", "wamid.C9")], field="smb_message_echoes"))
clk4.t += 5
m4.tick()
lines6 = [p for p in http4.calls("sendMessage", n0) if "удал" in p["text"]]
ok(len(lines6) == 1 and lines6[0]["text"].endswith("мы: 🗑 удалено сообщение от " + frm(NOW0 + 20, NOW0 + 60))
   and lines6[0]["text"].startswith(M.pk_time(NOW0 + 60) + " ") and not edits(http4, n0),
   "цель показана без id — одна строка «ДД.ММ ЧЧ:ММ мы: 🗑 удалено сообщение от ЧЧ:ММ», правки нет")
# правку чат не принял (400) — строкой, ответом на цель
feed(q4, payload([text_msg("wamid.C8", "его правка не пройдёт", ts=NOW0 + 25)]))
clk4.t += 5
m4.tick()
mid_c8 = http4.mid_of(lambda mm, p: mm == "sendMessage" and p.get("text", "").endswith("его правка не пройдёт"))
http4.script["editMessageText"] = [(400, {"ok": False, "description": "Bad Request: message can't be edited"})]
n0 = len(http4.tg)
feed(q4, payload([revoke_msg("wamid.V7", "wamid.C8")], field="smb_message_echoes"))
clk4.t += 5
m4.tick()
l7 = [p for p in http4.calls("sendMessage", n0) if "удал" in p["text"]]
ok(len(http4.calls("editMessageText", n0)) == 1 and len(l7) == 1
   and l7[0]["text"].endswith("🗑 удалено сообщение от " + frm(NOW0 + 25, NOW0 + 60))
   and (l7[0].get("reply_parameters") or {}).get("message_id") == mid_c8,
   "400 на правку — одна строка ответом на цель")
# обрыв ответа на правку (сеть) — «не повторять», строки нет
feed(q4, payload([text_msg("wamid.C7", "обрыв правки", ts=NOW0 + 26)]))
clk4.t += 5
m4.tick()
http4.script["editMessageText"] = [(None, {})]
n0 = len(http4.tg)
feed(q4, payload([revoke_msg("wamid.V8", "wamid.C7")], field="smb_message_echoes"))
for _ in range(2):
    clk4.t += 5
    m4.tick()
ok(len(http4.calls("editMessageText", n0)) == 1 and not [p for p in http4.calls("sendMessage", n0) if "удал" in p["text"]],
   "без ответа на правку — повтора нет, строки нет (ключ «не уверен»)")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(3) unsupported — русским словом: тема, файл истории, модель")
UW = "[неподдерживаемое сообщение — смотреть в телефоне]"
n0 = len(http.tg)
feed(q, payload([unsupported_msg("wamid.U1")]))
urow = q._conn().execute("SELECT msg_type, echo, history FROM wa_inbox WHERE wamid='wamid.U1'").fetchone()
clk.t += 5
m.tick()
ul = [p["text"] for p in http.calls("sendMessage", n0)]
ok(urow[0] == "unsupported" and len(ul) == 1 and ul[0] == "%s клиент: %s" % (M.pk_time(NOW0 + 30), UW),
   "тема: «ДД.ММ ЧЧ:ММ клиент: %s»: %r" % (UW, ul[-1:]))
# в предыстории (до темы): unsupported, edit, errors, contacts, пустой text — словом в файле и для модели
q5, env5, clk5, http5, m5 = world(arch=[(A, NOW0 - 9000, 0, "code_99", None, None, None, None, "KCODE00001"),
                                        (A, NOW0 - 8000, 1, "code_25", None, None, None, "F.bin", "KCODE00002")])
old = []
for i, (typ, extra) in enumerate([("unsupported", {"unsupported": {"type": "unknown"}}),
                                  ("edit", {"edit": {"original_message_id": "x"}}), ("errors", {"errors": [{"code": 1}]}),
                                  ("contacts", {"contacts": [{}]}), ("revoke", {"revoke": {"original_message_id": "y"}}),
                                  ("text", {"text": {"body": ""}}), ("zz_hist_kind", {})]):
    msg = {"from": A, "id": "wamid.P%d" % i, "timestamp": str(NOW0 - 7000 + i), "type": typ}
    msg.update(extra)
    old.append(msg)
feed(q5, payload(old))
q5._conn().execute("UPDATE wa_inbox SET history=1").connection.commit()
feed(q5, payload([text_msg("wamid.T5", "живое")]))
clk5.t += 5
GRAB.lines.clear()
m5.tick()
pre_logs = list(GRAB.lines)
docs = [t for t in http5.texts() if "history.txt" in t]
hist_txt = docs[0] if docs else ""
ok(UW in hist_txt and "[сообщение изменено]" in hist_txt and "[контакт]" in hist_txt
   and "[сообщение не передано — смотреть в телефоне]" in hist_txt
   and "[сообщение удалено с телефона]" in hist_txt and "[пустое сообщение]" in hist_txt
   and "[сообщение неизвестного вида]" in hist_txt and "[файл — файла нет]" in hist_txt,
   "файл истории: unsupported, edit, errors, contacts, revoke, пустой text, code_N — русским словом")
items, _missing = H.read_history(A, env5["queue_db"], env5["archive_db"], env5["archive_manifest"], "")
view, _n = H.model_view(items)
ok(UW in view and "[сообщение неизвестного вида]" in view and "[файл]" in view and not LATIN.search(view),
   "представление для модели — те же слова, латиницы в скобках нет")
ok(H.who_of({"msg_type": "unsupported", "echo": 0, "history": 0}) == "клиент"
   and H.who_of({"msg_type": "unsupported", "echo": 1, "history": 0}) == "мы"
   and H.who_of({"msg_type": "unsupported", "echo": None, "history": 0}) == "?",
   "сторона неопознанного вида — по echo (клиент/мы), echo не записан — «?»")

# ─────────────────────────────────────────────────────────────────────────────
print("\n(4) ни один вид не даёт латиницу в скобках; неизвестный — словом и строкой журнала")
KINDS = sorted(set(H.KIND_WORD) | set(H.ARCH_OTHER) | set(H.ARCH_MEDIA) | set(H.MEDIA_WORD)
               | {"", "weird_kind", "code_99", "code_23", "poll", "request_welcome", "ephemeral", H.MEDIA_PLACEHOLDER})
bad = []
for k in KINDS:
    row = {"id": 1, "msg_type": k, "text": None, "caption": None, "echo": 0, "history": 1, "wamid": None,
           "ts_msg": NOW0, "ts_queued": NOW0}
    outs = [M.body_of(row), H.item_line(H.queue_item(row)), H.model_line(H.queue_item(row))]
    for mf in (None, "F.bin"):
        it = H.arch_item((NOW0, 0, k, None, None, None, mf, "K1"), {})
        outs += [H.item_line(it), H.model_line(it)]
    bad += [(k, o) for o in outs if LATIN.search(o)]
ok(not bad, "видов %d × 7 дорог (тема, строка истории и модели из очереди и из архива): латиница — %d %s"
   % (len(KINDS), len(bad), bad[:2]))
GRAB.lines.clear()
r1 = {"msg_type": "zz_new_kind", "text": None, "caption": None}
ok(M.body_of(r1) == "[сообщение неизвестного вида]" and M.body_of(r1) == "[сообщение неизвестного вида]",
   "неизвестный вид — «[сообщение неизвестного вида]»")
logged = [ln for ln in GRAB.lines if "zz_new_kind" in ln]
ok(len(logged) == 1 and "неизвестен" in logged[0], "строка журнала с именем вида — одна на вид: %d" % len(logged))
ok(any("code_99" in ln for ln in pre_logs) and any("code_25" in ln for ln in pre_logs)
   and any("zz_hist_kind" in ln for ln in pre_logs),
   "предыстория: неизвестные виды архива (code_N, без файла и с файлом) и очереди — строкой журнала")
GRAB.lines.clear()
M.body_of({"msg_type": "evil kind\n+66800000011 Анна", "text": None, "caption": None})
ok(GRAB.lines and "66800000011" not in GRAB.lines[0] and "Анна" not in GRAB.lines[0] and "\n" not in GRAB.lines[0],
   "в журнале имя вида только [A-Za-z0-9_.-] — ни цифр номера длиннее 40, ни имён, ни переводов строки")
alltexts = http.texts() + http2.texts() + http3.texts() + http4.texts() + http5.texts() + http6.texts()
lat = [t[:60] for t in alltexts if LATIN.search(t)]
ok(not lat, "все тексты, ушедшие в темы во всех мирах (%d): латиницы в скобках нет %s" % (len(alltexts), lat[:1]))

# ─────────────────────────────────────────────────────────────────────────────
print("\n(5) повтор тела — одна правка")
n0 = len(http.tg)
for _ in range(2):
    clk.t += 5
    m.tick()
feed(q, payload([revoke_msg("wamid.V1", "wamid.C1")], field="smb_message_echoes"))      # тот же wamid
clk.t += 5
m.tick()
m_b = M.Mirror(env, http=http, clock=clk, sleep=clk.sleep, disk_free=lambda p: 10 ** 12)  # рестарт
m_b.tick()
feed(q, payload([revoke_msg("wamid.V1b", "wamid.C1", ts=NOW0 + 70)], field="smb_message_echoes"))  # второй revoke
clk.t += 5
m_b.tick()
ok(len([1 for mm, p in http.tg if mm == "editMessageText"]) == 1 and not edits(http, n0)
   and not [p for p in http.calls("sendMessage", n0) if "удал" in p.get("text", "")],
   "такт ×2, тот же wamid, рестарт, второй revoke той же цели — правка одна, строк нет")
ok(q._conn().execute("SELECT COUNT(*) FROM wa_inbox WHERE msg_type='revoke'").fetchone()[0] == 2
   and m_b._is_shown("msg:wamid.V1b"), "второй revoke лёг строкой очереди и помечен показанным без вызова")

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
