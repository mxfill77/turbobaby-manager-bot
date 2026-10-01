#!/usr/bin/env python3
"""Реакции клиента в темах показа и имя темы (WAREACTNAME0110, 01.10.2026).

СЕТИ НЕТ: Telegram и 360dialog выдуманы (`FakeHTTP`), чужой хост роняет тест. Живой базы нет:
очередь временная, собранная схемой самого wa_webhook. Временные файлы тест НЕ удаляет.

  + реакция клиента легла на нужное сообщение темы (setMessageReaction, id сообщения цели)
  + снятие реакции — реакция бота снята
  + эмодзи вне набора Telegram — короткая строка в теме, реакции нет
  + тема «без имени» переименована после входящего с именем — один раз
  − реакция не даёт карточки и не двигает окно 24 ч
  − повтор тела не ставит реакцию второй раз (ни входом, ни тактом, ни рестартом)
  − реакция на непоказанное сообщение не роняет службу

Мутанты: WA_REACT_SRC=<каталог> ставит копии модулей впереди дерева.
"""

import json
import os
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
if os.environ.get("WA_REACT_SRC"):
    sys.path.insert(0, os.environ["WA_REACT_SRC"])

import wa_kind as K          # noqa: E402
import wa_send as S          # noqa: E402
import wa_tg_mirror as M     # noqa: E402
import wa_webhook as W       # noqa: E402

res = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    res.append(bool(cond))
    return bool(cond)


NOW0 = int(time.time())
A, B = "66800000011", "66800000012"
OUR = "66900000000"


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeHTTP:
    def __init__(self, clock):
        self.clock = clock
        self.tg = []
        self.thread = 700
        self.script = {}

    def __call__(self, method, url, headers, data, timeout):
        assert url.startswith(M.TG_BASE + "/"), "чужой хост"
        meth = url.rsplit("/", 1)[1]
        params = json.loads(data.decode("utf-8")) if not headers.get("Content-Type", "").startswith(
            "multipart") else {"multipart": True}
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


TMP = tempfile.mkdtemp(prefix="wa_react_test_")
_seq = [0]


def world():
    _seq[0] += 1
    d = os.path.join(TMP, "w%d" % _seq[0])
    os.makedirs(d)
    q = W.WAQueueDB(os.path.join(d, "wa_queue.db"))
    env = {"queue_db": q.db_path, "state_db": os.path.join(d, "wa_tg_mirror.db"),
           "media_dir": os.path.join(d, "wa_media"), "d360_key": "k" * 26, "tg_token": "123:fake",
           "tg_chat": "-1001", "show": True, "archive_db": os.path.join(d, "no", "a.db"),
           "archive_media": os.path.join(d, "no", "m"), "archive_manifest": os.path.join(d, "no", "m.jsonl")}
    clk = Clock(NOW0 + 5)
    http = FakeHTTP(clk)
    m = M.Mirror(env, http=http, clock=clk, sleep=clk.sleep, disk_free=lambda p: 10 ** 12)
    m.tick()                                         # первое включение
    return q, env, clk, http, m


def payload(msgs, field="messages", name="", sender=A):
    val = {"messaging_product": "whatsapp", "metadata": {"display_phone_number": OUR}}
    if field == "smb_message_echoes":
        val["message_echoes"] = msgs
    else:
        val["messages"] = msgs
        val["contacts"] = [{"wa_id": sender, "profile": {"name": name}}] if name else []
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": field, "value": val}]}]}


def text_msg(wid, body, sender=A):
    return {"from": sender, "id": wid, "timestamp": str(NOW0), "type": "text", "text": {"body": body}}


def react_msg(wid, target, emoji, sender=A, to=None):
    r = {"message_id": target}
    if emoji is not None:
        r["emoji"] = emoji
    m = {"from": sender, "id": wid, "timestamp": str(NOW0 + 1), "type": "reaction", "reaction": r}
    if to:
        m["to"] = to
    return m


def feed(q, p):
    return q.enqueue_stats(W.normalize_wa_payload(p, OUR))


def thumb_id(http, text):
    """id сообщения темы, которым показан текст (FakeHTTP выдаёт 1000+номер вызова)."""
    for i, (m, p) in enumerate(http.tg):
        if m == "sendMessage" and p.get("text", "").endswith(text):
            return 1000 + i + 1
    return None


# ─────────────────────────────────────────────────────────────────────────────
print("(1) вход: реакция кладёт эмодзи и wamid цели; вид — свой")
q, env, clk, http, m = world()
feed(q, payload([text_msg("wamid.C1", "привет")], name="Анна"))
st = feed(q, payload([react_msg("wamid.R1", "wamid.C1", "👍")]))
row = q._conn().execute("SELECT msg_type, text, react_to, echo FROM wa_inbox WHERE wamid='wamid.R1'").fetchone()
ok(row == ("reaction", "👍", "wamid.C1", 0), "строка реакции: эмодзи в text, цель в react_to: %r" % (row,))
ok(K.kind_of("reaction", 0, 0) == K.KIND_REACTION and K.kind_of("reaction", 1, 0) == K.KIND_REACTION,
   "вид reaction — свой, и у клиента, и с телефона")
st2 = feed(q, payload([react_msg("wamid.R1", "wamid.C1", "👍")]))
ok(st["inserted"] == 1 and st2 == {"inserted": 0, "enriched": 0}, "повтор тела входом — строки второй нет: %r" % st2)

print("\n(2) − реакция не даёт карточки и не двигает окно 24 ч")
items = {it["msg_type"]: it for it in q.pull(now=NOW0 + 10)}
ok(items["reaction"]["disposition"] == K.DISP_DROP and items["reaction"]["kind"] == K.KIND_REACTION,
   "выдача ПК: reaction → drop (карточки нет): %s" % items["reaction"]["disposition"])
ok(K.disposition_of(K.KIND_REACTION) != K.DISP_CARD, "распоряжение вида reaction — не карточка")
q2, *_ = world()
feed(q2, payload([react_msg("wamid.R9", "wamid.X9", "👍", sender=B)], sender=B))
w = S.last_inbound_ts(B, q2.db_path)
ok(int(w.payload or 0) == 0, "номер только с реакцией — окно не открыто (метки нет): %r" % (w.payload,))
feed(q2, payload([dict(text_msg("wamid.B1", "раз", sender=B), timestamp=str(NOW0 - 3600))], sender=B))
feed(q2, payload([dict(react_msg("wamid.R10", "wamid.B1", "👍", sender=B), timestamp=str(NOW0))], sender=B))
w = S.last_inbound_ts(B, q2.db_path)
ok(int(w.payload or 0) == NOW0 - 3600, "реакция после входящего окно не двигает: метка входящего, а не реакции")

print("\n(3) + реакция клиента легла на нужное сообщение; строки нет")
q, env, clk, http, m = world()
feed(q, payload([text_msg("wamid.C1", "первое")], name="Анна"))
feed(q, payload([text_msg("wamid.C2", "второе")], name="Анна"))
m.tick()
target = thumb_id(http, "второе")
k = len(http.tg)
feed(q, payload([react_msg("wamid.R2", "wamid.C2", "❤️")]))
m.tick()
sr = http.calls("setMessageReaction", k)
ok(len(sr) == 1 and sr[0]["message_id"] == target and sr[0]["reaction"] == [{"type": "emoji", "emoji": "❤"}],
   "setMessageReaction на сообщение «второе» (id %s), ❤️ → ❤: %r" % (target, sr))
ok(not http.calls("sendMessage", k), "отдельной строки на реакцию нет")

print("\n(4) − повтор тела, такт и рестарт не ставят реакцию второй раз")
feed(q, payload([react_msg("wamid.R2", "wamid.C2", "❤️")]))
m.tick()
m.tick()
m2 = M.Mirror(env, http=http, clock=clk, sleep=clk.sleep, disk_free=lambda p: 10 ** 12)
m2.tick()
ok(len(http.calls("setMessageReaction", k)) == 1, "реакция поставлена ровно один раз: %d"
   % len(http.calls("setMessageReaction", k)))

print("\n(5) + снятие")
k = len(http.tg)
feed(q, payload([react_msg("wamid.R3", "wamid.C2", "")]))
m2.tick()
sr = http.calls("setMessageReaction", k)
ok(len(sr) == 1 and sr[0]["message_id"] == target and sr[0]["reaction"] == [],
   "снятие — реакция бота снята: %r" % sr)
ok(not http.calls("sendMessage", k), "и без строки")
feed(q, payload([react_msg("wamid.R3b", "wamid.C1", None)]))   # снятие без ключа emoji
row = q._conn().execute("SELECT text, react_to FROM wa_inbox WHERE wamid='wamid.R3b'").fetchone()
ok(row == ("", "wamid.C1"), "снятие без ключа emoji → text '' и цель: %r" % (row,))

print("\n(6) + реакция с телефона — так же; одна реакция бота: последняя, снятие возвращает другую")
k = len(http.tg)
feed(q, payload([react_msg("wamid.R4", "wamid.C2", "👍")]))
feed(q, payload([react_msg("wamid.E1", "wamid.C2", "🔥", sender=OUR, to=A)], field="smb_message_echoes"))
m2.tick()
sr = http.calls("setMessageReaction", k)
ok([x["reaction"] for x in sr] == [[{"type": "emoji", "emoji": "👍"}], [{"type": "emoji", "emoji": "🔥"}]],
   "клиент 👍, затем мы 🔥 с телефона → реакция бота 🔥: %r" % [x["reaction"] for x in sr])
k = len(http.tg)
feed(q, payload([react_msg("wamid.E2", "wamid.C2", "", sender=OUR, to=A)], field="smb_message_echoes"))
m2.tick()
sr = http.calls("setMessageReaction", k)
ok([x["reaction"] for x in sr] == [[{"type": "emoji", "emoji": "👍"}]], "мы сняли → вернулась реакция клиента 👍")

print("\n(7) + эмодзи вне набора Telegram — короткая строка")
k = len(http.tg)
feed(q, payload([react_msg("wamid.R5", "wamid.C1", "🦩")]))
m2.tick()
sm = http.calls("sendMessage", k)
ok(not http.calls("setMessageReaction", k) and len(sm) == 1 and "реакция 🦩 на «первое»" in sm[0]["text"]
   and sm[0]["message_thread_id"] == 701, "вне набора — одна строка в теме: %r" % [x.get("text") for x in sm])
ok(M.tg_emoji("👍🏽") == "👍" and M.tg_emoji("🦩") == "", "оттенок кожи снимается; вне набора → ''")

print("\n(8) − реакция на непоказанное сообщение не роняет службу")
k = len(http.tg)
feed(q, payload([react_msg("wamid.R6", "wamid.NOPE", "👍")]))
try:
    m2.tick()
    crashed = False
except Exception as e:  # noqa: BLE001
    crashed = type(e).__name__
sm = http.calls("sendMessage", k)
ok(crashed is False and len(sm) == 1 and "не из этой темы" in sm[0]["text"],
   "цели нет — строка, такт не упал (%s): %r" % (crashed, [x.get("text") for x in sm]))
k = len(http.tg)
feed(q, payload([text_msg("wamid.C3", "третье")]))
m2.tick()
http.script["setMessageReaction"] = [(400, {"ok": False, "description": "Bad Request: REACTION_INVALID"})]
feed(q, payload([react_msg("wamid.R7", "wamid.C3", "👍")]))
m2.tick()
sm = [x["text"] for x in http.calls("sendMessage", k)]
ok(any("реакция 👍 на «третье»" in t for t in sm), "чат не принял реакцию (400) — строкой, служба идёт")
m2.tick()
ok(len(http.calls("setMessageReaction", k)) == 1, "после 400 реакция не долбится повтором")

print("\n(9) старая строка без react_to — цель и эмодзи из тела строки")
q, env, clk, http, m = world()
feed(q, payload([text_msg("wamid.C1", "привет")], name="Анна"))
m.tick()
conn = q._conn()
raw = json.dumps({"type": "reaction", "id": "wamid.OLD", "reaction": {"emoji": "👍", "message_id": "wamid.C1"}})
conn.execute("INSERT INTO wa_inbox (ts_queued, from_number, name, msg_type, text, ts_msg, echo, history, raw, wamid) "
             "VALUES (?,?,?,?,?,?,?,?,?,?)", (NOW0, A, "", "reaction", None, NOW0, 0, 0, raw, "wamid.OLD"))
conn.commit()
k = len(http.tg)
m.tick()
sr = http.calls("setMessageReaction", k)
ok(len(sr) == 1 and sr[0]["message_id"] == thumb_id(http, "привет"), "реакция старой строки поставлена по raw")

print("\n(10) + тема «без имени» переименована после входящего с именем — один раз")
q, env, clk, http, m = world()
feed(q, payload([{"from": OUR, "to": B, "id": "wamid.E9", "timestamp": str(NOW0), "type": "text",
                  "text": {"body": "мы первыми"}}], field="smb_message_echoes"))
m.tick()
ok(http.calls("createForumTopic")[0]["name"] == "без имени · +" + B, "эхо открыло тему «без имени»")
ok(not http.calls("editForumTopic"), "имени нет — переименования нет")
feed(q, payload([text_msg("wamid.B2", "ответ", sender=B)], name="Борис", sender=B))
clk.t += 61
m.tick()
ed = http.calls("editForumTopic")
ok(len(ed) == 1 and ed[0]["name"] == "Борис · +" + B and ed[0]["message_thread_id"] == 701,
   "входящее с именем → editForumTopic «Борис · +номер»: %r" % ed)
for _ in range(3):
    clk.t += 61
    m.tick()
m3 = M.Mirror(env, http=http, clock=clk, sleep=clk.sleep, disk_free=lambda p: 10 ** 12)
m3.tick()
ok(len(http.calls("editForumTopic")) == 1, "один раз на смену: тактами и рестартом больше не зовётся")
feed(q, payload([text_msg("wamid.B3", "ещё", sender=B)], name="Борис Б.", sender=B))
clk.t += 61
m3.tick()
ed = http.calls("editForumTopic")
ok(len(ed) == 2 and ed[1]["name"] == "Борис Б. · +" + B, "имя сменилось — ещё один вызов")
nm = m3.st.execute("SELECT name FROM topics").fetchone()[0]
ok(nm == "Борис Б. · +" + B, "имя темы записано в состоянии")

print("\n(11) тема, открытая до правки (имя не записано): сверка один раз, 400 «не изменено» — записано")
q, env, clk, http, m = world()
feed(q, payload([text_msg("wamid.A1", "здравствуйте")], name="Анна"))
m.tick()
m.st.execute("UPDATE topics SET name=NULL")
m.st.commit()
http.script["editForumTopic"] = [(400, {"ok": False, "description": "Bad Request: TOPIC_NOT_MODIFIED"})]
clk.t += 61
m.tick()
clk.t += 61
m.tick()
ok(len(http.calls("editForumTopic")) == 1 and m.st.execute("SELECT name FROM topics").fetchone()[0]
   == "Анна · +" + A, "один вызов, 400 → имя записано, повтора нет")

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
if not all(res):
    print("FAIL: %d тест(а/ов) не прошли" % sum(1 for r in res if not r))
    sys.exit(1)
